# github_actions.py
import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def _obtener_token(token_env: str = "GITHUB_TOKEN"):
    try:
        return st.secrets[token_env]
    except Exception:
        return os.getenv(token_env)


def disparar_workflow(repo: str, workflow_file: str, rama: str = "main", token_env: str = "GITHUB_TOKEN") -> tuple:
    token = _obtener_token(token_env)
    if not token:
        return False, f"Falta configurar {token_env} en las variables de entorno/secrets."

    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    body = {"ref": rama}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        if resp.status_code == 204:
            return True, "Ha iniciado la generación de paquetes..."
        return False, f"GitHub respondió con código {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, f"Error al conectar con GitHub: {e}"

import time as _time

def _headers(token_env: str = "GITHUB_TOKEN"):
    token = _obtener_token(token_env)
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def obtener_ultima_ejecucion(repo: str, workflow_file: str, disparado_despues: float, token_env: str = "GITHUB_TOKEN") -> dict:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/runs"
    try:
        resp = requests.get(url, headers=_headers(token_env), params={"per_page": 5}, timeout=15)
        if resp.status_code != 200:
            return {"encontrada": False, "error": f"Código {resp.status_code}"}
        runs = resp.json().get("workflow_runs", [])
        for run in runs:
            creado = pd_to_timestamp(run["created_at"])
            if creado >= disparado_despues - 10:  # margen de 10s por desfase de reloj
                return {
                    "encontrada": True,
                    "status": run["status"],           # queued / in_progress / completed
                    "conclusion": run["conclusion"],    # success / failure / None
                    "url": run["html_url"],
                }
        return {"encontrada": False}
    except Exception as e:
        return {"encontrada": False, "error": str(e)}


def pd_to_timestamp(fecha_iso: str) -> float:
    import datetime
    dt = datetime.datetime.strptime(fecha_iso, "%Y-%m-%dT%H:%M:%SZ")
    return dt.replace(tzinfo=datetime.timezone.utc).timestamp()