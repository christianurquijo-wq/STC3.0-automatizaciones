"""
ops_logger.py -- Ejecutor con bitácora para el Panel de Operaciones Kuepa.

Qué hace:
  1. Ejecuta un script de Python (subproceso) mostrando su salida en vivo.
  2. Mide inicio, fin y duración; captura las últimas líneas si falla.
  3. Escribe UNA fila en la hoja LOG_EJECUCIONES del Sheet de operaciones.
  4. Si falla, envía una alerta al webhook de n8n (que manda el correo).

Regla de oro: el registro y la alerta NUNCA rompen la ejecución. Si el Sheet
o n8n no responden, se imprime un aviso y el script sigue su curso normal.

Uso por línea de comandos (lo usa el workflow ops_run_script.yml):
    python ops_logger.py --script "Upload_ECO++_2026.py"
    python ops_logger.py --script "Certificados_paquetes/paquetes.py" --cwd script
    python ops_logger.py --script "Auditoria_paquetes/auditoria.py" --cwd root

Uso como librería (lo usa trigger.py para el lote nocturno):
    from ops_logger import ejecutar, alertar_resumen

Variables de entorno (en GitHub van como Secrets del repo):
    OPS_SHEET_ID        ID del Google Sheet de operaciones
    OPS_LOG_SA_JSON     contenido JSON de la cuenta de servicio con permiso de
                        Editor sobre ese Sheet (o OPS_LOG_SA_FILE con la ruta)
    OPS_ALERT_WEBHOOK   URL del webhook de n8n "OPS - Alertas" (opcional)
    OPS_ALERT_TOKEN     token compartido con n8n (header X-OPS-TOKEN)
    OPS_ORIGEN          boton | cron | manual_github | local  (lo pone el workflow)
    OPS_ACTOR           correo de quien presionó el botón en el panel
    OPS_REQUEST_ID      id de la solicitud creada por el panel
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

TZ_BOGOTA = timezone(timedelta(hours=-5))
HOJA_LOG = "LOG_EJECUCIONES"

# El orden de esta lista DEBE coincidir con los encabezados de LOG_EJECUCIONES
# (scripts/ops_setup_sheet.py del dashboard crea la hoja con este mismo orden).
COLUMNAS = [
    "id_ejecucion", "request_id", "fecha_inicio", "fecha_fin", "duracion_seg",
    "plataforma", "repo", "automatizacion_id", "script", "origen",
    "disparado_por", "estado", "codigo_salida", "error", "run_url", "lote",
]

_SCRIPT_VALIDO = re.compile(r"^[\w\-+(). /áéíóúÁÉÍÓÚñÑ]+\.py$")


# --------------------------------------------------------------------------
# Contexto de la ejecución (GitHub Actions o local)
# --------------------------------------------------------------------------
def _ahora() -> datetime:
    return datetime.now(TZ_BOGOTA)


def _repo() -> str:
    return os.getenv("GITHUB_REPOSITORY", "local")


def _repo_corto() -> str:
    return _repo().split("/")[-1]


def _run_url() -> str:
    if os.getenv("GITHUB_RUN_ID"):
        return (f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
                f"{_repo()}/actions/runs/{os.getenv('GITHUB_RUN_ID')}")
    return ""


def _origen() -> str:
    origen = os.getenv("OPS_ORIGEN", "").strip()
    if origen:
        return origen
    evento = os.getenv("GITHUB_EVENT_NAME", "")
    if evento == "schedule":
        return "cron"
    if evento == "workflow_dispatch":
        return "manual_github"
    return "local"


def _actor() -> str:
    return (os.getenv("OPS_ACTOR") or os.getenv("GITHUB_ACTOR") or os.getenv("USERNAME")
            or os.getenv("USER") or "desconocido")


# --------------------------------------------------------------------------
# Escritura en Google Sheets (REST con google-auth; sin depender de gspread)
# --------------------------------------------------------------------------
_sesion = None


def _sesion_sheets():
    global _sesion
    if _sesion is not None:
        return _sesion
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    info_json = os.getenv("OPS_LOG_SA_JSON", "").strip()
    ruta = os.getenv("OPS_LOG_SA_FILE", "").strip()
    if info_json:
        creds = service_account.Credentials.from_service_account_info(json.loads(info_json), scopes=scopes)
    elif ruta and os.path.exists(ruta):
        creds = service_account.Credentials.from_service_account_file(ruta, scopes=scopes)
    else:
        raise RuntimeError("Sin OPS_LOG_SA_JSON ni OPS_LOG_SA_FILE")
    _sesion = AuthorizedSession(creds)
    return _sesion


def registrar(fila: dict) -> None:
    """Agrega una fila a LOG_EJECUCIONES. Nunca lanza excepción."""
    sheet_id = os.getenv("OPS_SHEET_ID", "").strip()
    if not sheet_id:
        print("[ops] OPS_SHEET_ID no configurado: la ejecución no queda en la bitácora.")
        return
    valores = [["" if fila.get(c) is None else fila.get(c) for c in COLUMNAS]]
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
           f"{HOJA_LOG}!A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS")
    for intento in range(3):
        try:
            r = _sesion_sheets().post(url, json={"values": valores}, timeout=30)
            if r.status_code < 300:
                return
            print(f"[ops] Sheets respondió {r.status_code}: {r.text[:200]}")
        except Exception as exc:  # noqa: BLE001 -- el log nunca debe romper la ejecución
            print(f"[ops] No se pudo registrar en la bitácora: {exc}")
        time.sleep(2 * (intento + 1))


# --------------------------------------------------------------------------
# Alertas (webhook de n8n -> correo)
# --------------------------------------------------------------------------
def _post_alerta(payload: dict) -> None:
    url = os.getenv("OPS_ALERT_WEBHOOK", "").strip()
    if not url:
        return
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "X-OPS-TOKEN": os.getenv("OPS_ALERT_TOKEN", "")},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as exc:  # noqa: BLE001
        print(f"[ops] No se pudo enviar la alerta: {exc}")


def alertar_resumen(lote: str, fallidas: list[dict]) -> None:
    """Una sola alerta por lote (no un correo por cada script fallido)."""
    if not fallidas:
        return
    _post_alerta({
        "tipo": "lote",
        "plataforma": "github",
        "repo": _repo(),
        "lote": lote,
        "origen": _origen(),
        "disparado_por": _actor(),
        "fecha": _ahora().isoformat(timespec="seconds"),
        "run_url": _run_url(),
        "total_fallidas": len(fallidas),
        "fallidas": [{"script": f["script"], "estado": f["estado"], "error": f["error"][-600:]}
                     for f in fallidas],
    })


# --------------------------------------------------------------------------
# Ejecución
# --------------------------------------------------------------------------
def _validar_script(script: str, raiz: str) -> str:
    script = script.strip().replace("\\", "/")
    if not _SCRIPT_VALIDO.match(script) or ".." in script.split("/"):
        raise ValueError(f"Nombre de script no permitido: {script!r}")
    ruta = os.path.realpath(os.path.join(raiz, script))
    if not ruta.startswith(os.path.realpath(raiz) + os.sep) or not os.path.isfile(ruta):
        raise FileNotFoundError(f"No existe el script dentro del repo: {script}")
    return ruta


def ejecutar(script: str, *, lote: str = "", cwd: str = "script", timeout_min: float = 60,
             alertar: bool = True, raiz: str | None = None) -> dict:
    """Ejecuta `script` y lo registra. Devuelve la fila escrita (dict)."""
    raiz = raiz or os.path.dirname(os.path.abspath(__file__))
    inicio = _ahora()
    t0 = time.monotonic()
    fila = {
        "id_ejecucion": uuid.uuid4().hex[:12],
        "request_id": os.getenv("OPS_REQUEST_ID", ""),
        "fecha_inicio": inicio.isoformat(timespec="seconds"),
        "plataforma": "github" if os.getenv("GITHUB_ACTIONS") else "local",
        "repo": _repo(),
        "automatizacion_id": f"{_repo_corto()}:{script}",
        "script": script,
        "origen": _origen(),
        "disparado_por": _actor(),
        "run_url": _run_url(),
        "lote": lote,
    }
    cola = collections.deque(maxlen=40)
    codigo, estado = 1, "FALLIDO"
    try:
        ruta = _validar_script(script, raiz)
        directorio = os.path.dirname(ruta) if cwd == "script" else raiz
        entorno = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        # Los scripts no necesitan las credenciales de la bitácora.
        for k in ("OPS_LOG_SA_JSON", "OPS_ALERT_TOKEN"):
            entorno.pop(k, None)
        print(f"\n{'=' * 60}\n▶ {script}  (cwd={os.path.relpath(directorio, raiz)})\n{'=' * 60}", flush=True)
        proc = subprocess.Popen([sys.executable, ruta], cwd=directorio, env=entorno,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        vencido = threading.Event()

        def _matar():
            vencido.set()
            proc.kill()

        reloj = threading.Timer(timeout_min * 60, _matar)
        reloj.start()
        try:
            for linea in proc.stdout:  # salida en vivo (consola de GitHub)
                print(linea, end="", flush=True)
                cola.append(linea.rstrip())
            proc.wait()
        finally:
            reloj.cancel()
        codigo = proc.returncode
        if vencido.is_set():
            estado = "TIMEOUT"
            cola.append(f"[ops] Detenido por superar {timeout_min} min")
        else:
            estado = "EXITOSO" if codigo == 0 else "FALLIDO"
    except Exception as exc:  # noqa: BLE001
        cola.append(f"[ops] {type(exc).__name__}: {exc}")
        estado, codigo = "FALLIDO", -1

    fin = _ahora()
    fila.update({
        "fecha_fin": fin.isoformat(timespec="seconds"),
        "duracion_seg": round(time.monotonic() - t0, 1),
        "estado": estado,
        "codigo_salida": codigo,
        "error": "" if estado == "EXITOSO" else "\n".join(list(cola)[-15:])[-1500:],
    })
    print(f"[ops] {script}: {estado} en {fila['duracion_seg']} s", flush=True)
    registrar(fila)
    if alertar and estado != "EXITOSO":
        _post_alerta({"tipo": "script", **fila})
    return fila


def main() -> None:
    p = argparse.ArgumentParser(description="Ejecuta un script y lo registra en LOG_EJECUCIONES")
    p.add_argument("--script", required=True, help="Ruta relativa a la raíz del repo")
    p.add_argument("--cwd", choices=["script", "root"], default="script",
                   help="Directorio de trabajo: carpeta del script (por defecto) o raíz del repo")
    p.add_argument("--timeout", type=float, default=60, help="Minutos máximos")
    args = p.parse_args()
    fila = ejecutar(args.script, cwd=args.cwd, timeout_min=args.timeout)
    sys.exit(0 if fila["estado"] == "EXITOSO" else 1)


if __name__ == "__main__":
    main()
