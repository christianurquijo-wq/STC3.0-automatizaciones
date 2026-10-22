"""
ops_logger.py -- Ejecutor con bitácora para el Panel de Operaciones Kuepa.

Qué hace:
  1. Ejecuta un script de Python (subproceso) mostrando su salida en vivo.
  2. Mide inicio, fin y duración; captura las últimas líneas si falla.
  3. Escribe UNA fila en la hoja LOG_EJECUCIONES del Sheet de operaciones.
  4. Si falla, envía un correo de alerta: por Gmail (SMTP) directo desde Python,
     o por el webhook de n8n si OPS_ALERT_WEBHOOK está configurado.

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
    OPS_ALERT_WEBHOOK   URL del webhook de n8n "OPS - Alertas" (opcional; si está,
                        tiene prioridad sobre Gmail)
    OPS_ALERT_TOKEN     token compartido con n8n (header X-OPS-TOKEN)

Alertas por Gmail (oct-2026; sin n8n). Se leen del entorno o del .env de la raíz
del repo (el .env viaja en SECRETS_BUNDLE, así que no hay que crear secrets):
    GMAIL_USER          cuenta que envía (ej. automatizaciones@kuepa.com)
    GMAIL_APP_PASSWORD  contraseña de aplicación de esa cuenta (no la normal)
    OPS_ALERT_EMAIL     destinatario(s), separados por coma. Por defecto GMAIL_USER.

Probar el correo desde tu PC:  python ops_logger.py --probar-alerta
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
import smtplib
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from email.message import EmailMessage
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
# Alertas: Gmail directo (por defecto) o webhook de n8n (si está configurado)
# --------------------------------------------------------------------------
_CLAVES_CORREO = ("GMAIL_USER", "GMAIL_APP_PASSWORD", "OPS_ALERT_EMAIL")


def _config_correo() -> dict:
    """Lee las claves de correo del entorno y, si faltan, del .env de la raíz.
    No vuelca el .env completo al entorno: solo estas 3 claves y solo aquí."""
    cfg = {k: os.getenv(k, "").strip() for k in _CLAVES_CORREO}
    ruta_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not all(cfg.values()) and os.path.exists(ruta_env):
        with open(ruta_env, encoding="utf-8-sig") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                clave = clave.strip().removeprefix("export ").strip()
                if clave in cfg and not cfg[clave]:
                    cfg[clave] = valor.split(" #")[0].strip().strip('"').strip("'")
    cfg["OPS_ALERT_EMAIL"] = cfg["OPS_ALERT_EMAIL"] or cfg["GMAIL_USER"]
    return cfg


def _texto_alerta(payload: dict) -> tuple[str, str]:
    """Arma asunto y cuerpo en texto plano a partir del payload de la alerta."""
    repo = payload.get("repo", "")
    url = payload.get("run_url", "")
    if payload.get("tipo") == "lote":
        n = payload.get("total_fallidas", 0)
        asunto = f"[OPS] Lote {payload.get('lote', '')}: {n} script(s) fallaron · {repo.split('/')[-1]}"
        partes = [f"Lote: {payload.get('lote', '')}", f"Repo: {repo}",
                  f"Origen: {payload.get('origen', '')} · disparado por {payload.get('disparado_por', '')}",
                  f"Fecha: {payload.get('fecha', '')}", f"Ejecución: {url or '(local)'}", "",
                  f"Fallaron {n} script(s):"]
        for f in payload.get("fallidas", []):
            partes += ["", f"■ {f.get('script', '')} — {f.get('estado', '')}", str(f.get("error", "")).strip()]
    else:
        asunto = f"[OPS] {payload.get('estado', 'FALLIDO')}: {payload.get('script', '')} · {repo.split('/')[-1]}"
        partes = [f"Script: {payload.get('script', '')}", f"Estado: {payload.get('estado', '')} "
                  f"(código {payload.get('codigo_salida', '')}, {payload.get('duracion_seg', '')} s)",
                  f"Repo: {repo}",
                  f"Origen: {payload.get('origen', '')} · disparado por {payload.get('disparado_por', '')}",
                  f"Inicio: {payload.get('fecha_inicio', '')}", f"Ejecución: {url or '(local)'}", "",
                  "Últimas líneas:", str(payload.get("error", "")).strip()]
    partes += ["", "—", "Detalle e historial: Dashboard → Operaciones → Análisis de ejecuciones.",
               "Qué hacer según el error: Dashboard → Manual de automatizaciones → Si algo falla."]
    return asunto, "\n".join(partes)


def _enviar_correo(asunto: str, cuerpo: str) -> bool:
    cfg = _config_correo()
    if not (cfg["GMAIL_USER"] and cfg["GMAIL_APP_PASSWORD"]):
        print("[ops] Sin GMAIL_USER / GMAIL_APP_PASSWORD: no se envía la alerta por correo.")
        return False
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = f"Operaciones Kuepa <{cfg['GMAIL_USER']}>"
    msg["To"] = cfg["OPS_ALERT_EMAIL"]
    msg.set_content(cuerpo)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(cfg["GMAIL_USER"], cfg["GMAIL_APP_PASSWORD"].replace(" ", ""))
            smtp.send_message(msg)
        print(f"[ops] Alerta enviada por correo a {cfg['OPS_ALERT_EMAIL']}")
        return True
    except Exception as exc:  # noqa: BLE001 -- la alerta nunca rompe la ejecución
        print(f"[ops] No se pudo enviar la alerta por correo: {type(exc).__name__}: {exc}")
        return False


def _post_alerta(payload: dict) -> None:
    url = os.getenv("OPS_ALERT_WEBHOOK", "").strip()
    if not url:
        _enviar_correo(*_texto_alerta(payload))
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
        print(f"[ops] No se pudo enviar la alerta a n8n ({exc}); intento por correo.")
        _enviar_correo(*_texto_alerta(payload))


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
    p.add_argument("--script", help="Ruta relativa a la raíz del repo")
    p.add_argument("--cwd", choices=["script", "root"], default="script",
                   help="Directorio de trabajo: carpeta del script (por defecto) o raíz del repo")
    p.add_argument("--timeout", type=float, default=60, help="Minutos máximos")
    p.add_argument("--probar-alerta", action="store_true",
                   help="Envía un correo de prueba con la configuración actual y termina")
    args = p.parse_args()
    if args.probar_alerta:
        ok = _enviar_correo("[OPS] Prueba de alerta",
                            "Si te llegó este correo, las alertas de fallos están funcionando.\n"
                            f"Repo: {_repo()} · enviado por {_actor()} · {_ahora():%Y-%m-%d %H:%M}")
        sys.exit(0 if ok else 1)
    if not args.script:
        p.error("falta --script")
    fila = ejecutar(args.script, cwd=args.cwd, timeout_min=args.timeout)
    sys.exit(0 if fila["estado"] == "EXITOSO" else 1)


if __name__ == "__main__":
    main()
