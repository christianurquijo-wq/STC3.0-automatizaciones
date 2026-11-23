"""Servicio de PDF de Remisiones STC 3.0 (HTML → PDF con Chromium/Playwright).

nov-2026: antes cada solicitud abría y cerraba su propio Chromium. n8n manda las remisiones en paralelo y, en el
runner de GitHub (2 CPU), decenas de Chromium a la vez se caían («Target crashed», «Timeout 30000ms») o tardaban más
de un minuto; a través del túnel eso llegaba a n8n como «aborted». Ahora:
  * un solo Chromium para todo el servicio (se abre al iniciar y se cierra al terminar);
  * cada PDF usa su propia pestaña aislada (contexto nuevo) y se cierra al terminar;
  * como máximo PDF_CONCURRENCIA PDFs a la vez (por defecto 3); los demás esperan su turno en cola;
  * si un PDF falla, se responde 500 con el motivo (en vez de cortar la conexión) y, si Chromium se cayó,
    se vuelve a abrir para la siguiente solicitud.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from playwright.async_api import Browser, async_playwright
from pydantic import BaseModel

CONCURRENCIA = int(os.getenv("PDF_CONCURRENCIA", "3"))
TIMEOUT_MS = int(os.getenv("PDF_TIMEOUT_MS", "60000"))
# Medidas con nombre (A4, Letter…) van como formato; las demás (210mm, 8.5in…) como ancho/alto.
FORMATOS = {"a4", "a3", "a5", "letter", "legal", "tabloid", "ledger"}

_estado: dict = {}


async def _navegador() -> Browser:
    """El Chromium compartido; si se cayó, abre uno nuevo."""
    async with _estado["candado"]:
        b = _estado.get("browser")
        if b is None or not b.is_connected():
            _estado["browser"] = await _estado["pw"].chromium.launch(args=["--disable-dev-shm-usage"])
        return _estado["browser"]


@asynccontextmanager
async def ciclo(app: FastAPI):
    _estado["pw"] = await async_playwright().start()
    _estado["candado"] = asyncio.Lock()
    _estado["turnos"] = asyncio.Semaphore(CONCURRENCIA)
    await _navegador()
    try:
        yield
    finally:
        b = _estado.get("browser")
        if b is not None and b.is_connected():
            await b.close()
        await _estado["pw"].stop()


app = FastAPI(lifespan=ciclo)


class DatosHTML(BaseModel):
    html: str
    width: Optional[str] = "A4"
    height: Optional[str] = "A4"


def _medidas(width: Optional[str], height: Optional[str]) -> dict:
    w, h = (width or "A4").strip(), (height or "A4").strip()
    if w.lower() in FORMATOS:
        return {"format": w}
    return {"width": w, "height": h if h.lower() not in FORMATOS else w}


@app.post("/crear-pdf")
async def crear_pdf(datos: DatosHTML):
    async with _estado["turnos"]:
        for intento in (1, 2):  # si Chromium se cayó a mitad, un segundo intento con uno nuevo
            contexto = None
            try:
                contexto = await (await _navegador()).new_context()
                pagina = await contexto.new_page()
                await pagina.set_content(datos.html, timeout=TIMEOUT_MS)
                pdf = await pagina.pdf(print_background=True, **_medidas(datos.width, datos.height))
                return Response(content=pdf, media_type="application/pdf")
            except Exception as e:  # noqa: BLE001 -- se informa a n8n en lugar de cortar la conexión
                if intento == 2:
                    return JSONResponse(status_code=500, content={"error": f"{type(e).__name__}: {str(e)[:300]}"})
            finally:
                if contexto is not None:
                    try:
                        await contexto.close()
                    except Exception:  # noqa: BLE001
                        pass
