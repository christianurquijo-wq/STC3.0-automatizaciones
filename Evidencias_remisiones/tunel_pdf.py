"""
Túnel del servicio de PDF de Remisiones (STC 3.0) -- arranque automático (oct-2026).

Hace en un solo paso lo que antes eran 3 manuales:
  1. Levanta el servicio de PDF (FastAPI, Evidencias_remisiones/main.py) en el puerto 8000.
  2. Abre el túnel de Cloudflare (quick tunnel) y captura su URL *.trycloudflare.com.
  3. Actualiza esa URL en n8n, en los nodos HTTP del flujo de Remisiones que llaman a /crear-pdf
     (por la API de n8n; guarda un respaldo del flujo antes de cambiarlo).
Luego vigila: si el servicio o el túnel se caen, los reinicia y vuelve a actualizar n8n.

Uso (venv de STC):
    C:\\venvs\\stc\\Scripts\\python.exe Evidencias_remisiones\\tunel_pdf.py
Para que arranque solo al iniciar sesión en Windows, ver programar_tunel_pdf.ps1.

Configuración: N8N_API_URL y N8N_API_KEY del .env de STC (o, si no están, del de EFE).
Opcional: N8N_FLUJO_PDF (ID del flujo; por defecto Remisiones NMnUtMvRNl9ikgZ9) y PDF_PUERTO.
Registro y respaldos del flujo: STC/logs/ (excluida de git; nunca escribe la key).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

AQUI = Path(__file__).resolve().parent
STC = AQUI.parent
LOGS = STC / "logs"  # carpeta ya excluida de git
LOGS.mkdir(exist_ok=True)
LOG = LOGS / "tunel_pdf.log"
PATRON_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
               "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
               "executionOrder", "callerPolicy", "callerIds", "timeSavedPerExecution"}
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # en Windows no abre consolas extra


def log(msg: str) -> None:
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S} · {msg}"
    print(linea, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def _env(clave: str) -> str:
    if os.getenv(clave):
        return os.getenv(clave, "").strip()
    for archivo in (STC / ".env", STC.parent / "EFE" / ".env"):
        if archivo.exists():
            for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
                if "=" in linea and not linea.lstrip().startswith("#"):
                    k, v = linea.split("=", 1)
                    if k.strip() == clave:
                        return v.split(" #")[0].strip().strip('"').strip("'")
    return ""


API = _env("N8N_API_URL").rstrip("/")
KEY = _env("N8N_API_KEY")
FLUJO = _env("N8N_FLUJO_PDF") or "NMnUtMvRNl9ikgZ9"
PUERTO = int(_env("PDF_PUERTO") or 8000)
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}


# ------------------------------------------------------------------ procesos
def _drenar(proc: subprocess.Popen, prefijo: str, al_leer=None) -> None:
    """Lee la salida del proceso (si no se lee, el proceso se bloquea) y la manda al log."""
    for linea in proc.stdout:
        linea = linea.rstrip()
        if al_leer:
            al_leer(linea)
        if any(p in linea for p in ("ERR", "error", "Error", "trycloudflare", "running on", "Uvicorn")):
            log(f"{prefijo} {linea[:300]}")


def iniciar_servicio() -> subprocess.Popen:
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--app-dir", str(AQUI),
           "--host", "127.0.0.1", "--port", str(PUERTO)]
    proc = subprocess.Popen(cmd, cwd=str(AQUI), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", creationflags=SIN_VENTANA)
    threading.Thread(target=_drenar, args=(proc, "[pdf]"), daemon=True).start()
    for _ in range(60):  # hasta 30 s
        try:
            if requests.get(f"http://127.0.0.1:{PUERTO}/docs", timeout=2).ok:
                log(f"Servicio de PDF arriba en el puerto {PUERTO}")
                return proc
        except requests.RequestException:
            pass
        if proc.poll() is not None:
            raise RuntimeError("El servicio de PDF se cerró al arrancar (revisa el log).")
        time.sleep(0.5)
    raise RuntimeError("El servicio de PDF no respondió en 30 s.")


def _cloudflared() -> str:
    for c in (shutil.which("cloudflared"),
              r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
              r"C:\Program Files\cloudflared\cloudflared.exe",
              str(Path.home() / "AppData/Local/Microsoft/WinGet/Links/cloudflared.exe")):
        if c and Path(c).exists():
            return c
    raise RuntimeError("No encontré cloudflared. Instálalo con: winget install Cloudflare.cloudflared")


def iniciar_tunel() -> tuple[subprocess.Popen, str]:
    hallada: dict[str, str] = {}
    listo = threading.Event()

    def buscar(linea: str) -> None:
        m = PATRON_URL.search(linea)
        if m and not listo.is_set():
            hallada["url"] = m.group(0)
            listo.set()

    # --protocol http2: usa TCP 443. El protocolo por defecto (QUIC/UDP) se corta en muchas redes
    # ("failed to accept QUIC stream: timeout") y n8n deja de poder llegar al servicio.
    proc = subprocess.Popen([_cloudflared(), "tunnel", "--no-autoupdate", "--protocol", "http2",
                             "--url", f"http://127.0.0.1:{PUERTO}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", creationflags=SIN_VENTANA)
    threading.Thread(target=_drenar, args=(proc, "[túnel]", buscar), daemon=True).start()
    if not listo.wait(60):
        proc.kill()
        raise RuntimeError("Cloudflare no entregó la URL del túnel en 60 s.")
    url = hallada["url"]
    # La URL nueva tarda en existir en el DNS público. Si se le pasa a n8n antes, n8n falla con
    # "The connection cannot be established… incorrect host". Se confirma con el DNS público de
    # Cloudflare (no con el de este PC, que puede guardar en caché el "no existe") y luego que responda.
    if not _resuelve(url, espera_max=180):
        proc.kill()
        raise RuntimeError(f"El DNS público no resolvió {url} en 3 min.")
    responde = any(_responde(url) or time.sleep(3) for _ in range(20))
    log(f"Túnel abierto: {url}" + ("" if responde else " (este PC aún no lo alcanza; el DNS público ya sí)"))
    return proc, url


def _resuelve(url: str, espera_max: int) -> bool:
    """True cuando el DNS público ya conoce la URL. Si la red no deja consultar el DNS de
    Cloudflare, se conforma con que la URL responda desde este PC."""
    host = url.split("//", 1)[1]
    fin, doh_ok = time.time() + espera_max, False
    while time.time() < fin:
        try:
            r = requests.get("https://cloudflare-dns.com/dns-query", params={"name": host, "type": "A"},
                             headers={"accept": "application/dns-json"}, timeout=10)
            doh_ok = doh_ok or r.ok
            if r.ok and r.json().get("Answer"):
                return True
        except (requests.RequestException, ValueError):
            if _responde(url):
                return True
        time.sleep(5)
    return not doh_ok  # sin DNS público disponible: se sigue (con aviso en el log)


def _responde(url: str) -> bool:
    try:
        return requests.get(f"{url}/docs", timeout=10).ok
    except requests.RequestException:
        return False


# ------------------------------------------------------------------ n8n
def actualizar_n8n(url_tunel: str) -> None:
    if not (API and KEY):
        log("⚠ Sin N8N_API_URL / N8N_API_KEY: actualiza a mano la URL en el nodo de n8n: "
            f"{url_tunel}/crear-pdf")
        return
    r = requests.get(f"{API}/workflows/{FLUJO}", headers=H, timeout=60)
    r.raise_for_status()
    wf = r.json()
    cambios = []
    for n in wf["nodes"]:
        p = n.get("parameters", {})
        if n["type"].endswith(".httpRequest") and "/crear-pdf" in str(p.get("url", "")):
            nueva = f"{url_tunel}/crear-pdf"
            if p["url"] != nueva:
                cambios.append(f"«{n['name']}»")
                p["url"] = nueva
    if not cambios:
        log("n8n ya tenía la URL vigente; no se cambió nada.")
        return
    respaldo = LOGS / f"respaldo_flujo_pdf_{datetime.now():%Y%m%d_%H%M%S}.json"
    respaldo.write_text(json.dumps(wf, ensure_ascii=False), encoding="utf-8")
    cuerpo = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
              "settings": {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}}
    r = requests.put(f"{API}/workflows/{FLUJO}", headers={**H, "Content-Type": "application/json"},
                     data=json.dumps(cuerpo), timeout=60)
    if not r.ok:
        log(f"✖ n8n rechazó el cambio (HTTP {r.status_code}): {r.text[:200]}. "
            f"Pon a mano {url_tunel}/crear-pdf en {', '.join(cambios)}")
        return
    if wf.get("active") and not r.json().get("active"):
        requests.post(f"{API}/workflows/{FLUJO}/activate", headers=H, timeout=60)
    log(f"✔ n8n actualizado ({wf['name']}): {', '.join(cambios)} → {url_tunel}/crear-pdf")
    # Respaldos viejos: se conservan los 5 más recientes.
    for viejo in sorted(LOGS.glob("respaldo_flujo_pdf_*.json"))[:-5]:
        viejo.unlink(missing_ok=True)


# ------------------------------------------------------------------ ciclo principal
def main() -> None:
    log("=== Inicio del túnel de PDF ===")
    servicio = tunel = None
    url, fallos = "", 0
    try:
        while True:
            if servicio is None or servicio.poll() is not None:
                if servicio is not None:
                    log("⚠ El servicio de PDF se cayó; reiniciando…")
                servicio = iniciar_servicio()
            if tunel is not None and tunel.poll() is None:
                # El proceso puede seguir vivo con el túnel muerto: se prueba la URL pública.
                fallos = 0 if _responde(url) else fallos + 1
                if fallos >= 3:  # ~3 min sin respuesta
                    log("⚠ El túnel no responde hace 3 min; abriendo uno nuevo…")
                    tunel.kill()
            if tunel is None or tunel.poll() is not None:
                if tunel is not None:
                    log("⚠ El túnel se cerró; abriendo uno nuevo…")
                tunel, url = iniciar_tunel()
                fallos = 0
                actualizar_n8n(url)
            time.sleep(60)
    except KeyboardInterrupt:
        log("Detenido por el usuario (Ctrl+C).")
    except Exception as exc:  # noqa: BLE001 -- dejar rastro en el log y reintentar desde el programador
        log(f"✖ Error: {exc}")
        raise
    finally:
        for p in (tunel, servicio):
            if p and p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
