"""
Remisiones STC 3.0 BAJO DEMANDA (oct-2026): el servicio de PDF y el túnel existen solo mientras
corre el flujo de n8n, y no dependen del PC de nadie.

Lo dispara el botón «STC 3.0 · Remisiones (correos + PDF)» del Panel de control, que corre este
script en GitHub Actions (ops_run_script.yml, como cualquier otra automatización de STC):
  1. Levanta el servicio de PDF (Evidencias_remisiones/main.py, Playwright) en el runner.
  2. Abre un túnel de Cloudflare (quick tunnel) y espera a que su URL exista en el DNS público.
  3. Pone esa URL en los nodos «Convertidor a PDF…» del flujo de n8n (tunel_pdf.actualizar_n8n).
  4. Dispara el flujo por su webhook y espera a que la ejecución termine (consulta la API de n8n).
  5. Cierra el túnel y el servicio. Termina en verde si el flujo terminó bien; si no, en rojo con el
     paso que falló (el panel lo explica con el catálogo de errores).

Antes el túnel corría en el PC de Christian todo el tiempo (tunel_pdf.py + tarea programada) y, si
el PC se suspendía, n8n fallaba con «The connection cannot be established… incorrect host».
tunel_pdf.py se conserva para pruebas locales.

Configuración (STC/.env, viaja en SECRETS_BUNDLE): N8N_API_URL, N8N_API_KEY,
WEBHOOK_REMISIONES_URL, WEBHOOK_REMISIONES_HEADER_NOMBRE, WEBHOOK_REMISIONES_HEADER_VALOR.
Opcional: REMISIONES_TIMEOUT_MIN (por defecto 100; el timeout_min del CATALOGO debe ser mayor).
Nota: si alguien ejecuta el flujo directamente en n8n (sin este script), no habrá túnel y los
PDF fallarán: el flujo se debe correr desde el panel.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
import time
from pathlib import Path

import requests

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import tunel_pdf as t  # noqa: E402  (mismas funciones del túnel local: servicio, túnel, actualizar n8n)

FINALES = {"success", "error", "crashed", "canceled"}
URL_CLOUDFLARED = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"


def asegurar_cloudflared() -> None:
    """En el runner de GitHub (Linux) no viene instalado: se descarga el binario oficial."""
    if shutil.which("cloudflared") or platform.system() != "Linux":
        return
    destino = Path(os.getenv("RUNNER_TEMP", "/tmp")) / "cloudflared"
    if not destino.exists():
        t.log("Descargando cloudflared…")
        r = requests.get(URL_CLOUDFLARED, timeout=120)
        r.raise_for_status()
        destino.write_bytes(r.content)
        destino.chmod(destino.stat().st_mode | stat.S_IEXEC)
    os.environ["PATH"] = f"{destino.parent}{os.pathsep}{os.environ.get('PATH', '')}"


def ultima_ejecucion() -> int:
    r = requests.get(f"{t.API}/executions", headers=t.H, params={"workflowId": t.FLUJO, "limit": 1}, timeout=60)
    r.raise_for_status()
    datos = r.json().get("data", [])
    return int(datos[0]["id"]) if datos else 0


def disparar_webhook() -> None:
    url = t._env("WEBHOOK_REMISIONES_URL")
    nombre, valor = t._env("WEBHOOK_REMISIONES_HEADER_NOMBRE"), t._env("WEBHOOK_REMISIONES_HEADER_VALOR")
    if not url:
        raise RuntimeError("Falta la URL del webhook (WEBHOOK_REMISIONES_URL en STC/.env).")
    try:
        r = requests.post(url, headers={nombre: valor} if nombre else {},
                          json={"origen": "remisiones_bajo_demanda", "request_id": os.getenv("OPS_REQUEST_ID", "")},
                          timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"n8n {r.status_code}: {r.text[:300]}")
    except requests.ReadTimeout:
        pass  # el webhook puede responder al final del flujo: la ejecución sigue en n8n
    t.log("Flujo de Remisiones disparado en n8n.")


def esperar(base: int, minutos: int) -> dict:
    """Espera a que aparezca la ejecución nueva (id > base) y termine."""
    fin = time.time() + minutos * 60
    ejecucion = None
    while time.time() < fin:
        r = requests.get(f"{t.API}/executions", headers=t.H,
                         params={"workflowId": t.FLUJO, "limit": 5}, timeout=60)
        if r.ok:
            nuevas = [e for e in r.json().get("data", []) if int(e["id"]) > base]
            if nuevas:
                ejecucion = min(nuevas, key=lambda e: int(e["id"]))
                if str(ejecucion.get("status")) in FINALES or ejecucion.get("finished"):
                    return ejecucion
        time.sleep(20)
    raise RuntimeError(f"TIMEOUT: el flujo no terminó en {minutos} min"
                       + (f" (ejecución {ejecucion['id']} sigue en n8n)" if ejecucion else ""))


def error_de(eid: str, estado: str) -> str:
    try:
        r = requests.get(f"{t.API}/executions/{eid}", headers=t.H, params={"includeData": "true"}, timeout=60)
        res = ((r.json().get("data") or {}).get("resultData") or {}) if r.ok else {}
    except requests.RequestException:
        res = {}
    err = res.get("error") or {}
    nodo = err.get("node", {}).get("name") if isinstance(err.get("node"), dict) else err.get("node")
    msg = err.get("message") or err.get("description") or f"n8n status: {estado}"
    return (f"Nodo «{nodo}»: " if nodo else "") + str(msg)[:800]


def main() -> None:
    if not (t.API and t.KEY):
        sys.exit("Faltan N8N_API_URL / N8N_API_KEY en STC/.env.")
    minutos = int(t._env("REMISIONES_TIMEOUT_MIN") or 100)
    servicio = tunel = None
    try:
        asegurar_cloudflared()
        servicio = t.iniciar_servicio()
        tunel, url = t.iniciar_tunel()
        t.actualizar_n8n(url)
        base = ultima_ejecucion()
        disparar_webhook()
        e = esperar(base, minutos)
        estado = str(e.get("status"))
        if estado != "success":
            sys.exit(error_de(str(e["id"]), estado))
        t.log(f"✔ Remisiones terminó bien (ejecución {e['id']} de n8n).")
    finally:
        for p in (tunel, servicio):
            if p and p.poll() is None:
                p.terminate()
        t.log("Túnel y servicio de PDF cerrados.")


if __name__ == "__main__":
    main()
