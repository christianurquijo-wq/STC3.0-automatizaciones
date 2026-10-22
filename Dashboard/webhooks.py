# webhooks.py
import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def _obtener_clave_acciones():
    try:
        return st.secrets["CLAVE_ACCIONES"]
    except Exception:
        return os.getenv("CLAVE_ACCIONES")

def validar_clave(clave_ingresada: str) -> bool:
    clave_real = _obtener_clave_acciones()
    if not clave_real:
        return False
    return clave_ingresada == clave_real

def _obtener_secreto(nombre_env: str):
    try:
        return st.secrets[nombre_env]
    except Exception:
        return os.getenv(nombre_env)

def disparar_webhook(url_env: str, header_nombre_env: str = None, header_valor_env: str = None) -> tuple:
    url = _obtener_secreto(url_env)
    if not url:
        return False, f"Falta configurar {url_env} en las variables de entorno/secrets."

    headers = {}
    if header_nombre_env and header_valor_env:
        nombre_header = _obtener_secreto(header_nombre_env)
        valor_header = _obtener_secreto(header_valor_env)
        if nombre_header and valor_header:
            headers[nombre_header] = valor_header

    try:
        resp = requests.post(url, headers=headers, timeout=15)
        if resp.status_code in (200, 201, 202, 204):
            return True, "Flujo disparado correctamente."
        return False, f"El webhook respondió con código {resp.status_code}."
    except Exception as e:
        return False, f"Error al conectar con el webhook: {e}"

WEBHOOKS_REGISTRADOS = [
    {
        "id": "remisiones",
        "etiqueta": "📤 Enviar remisiones (n8n)",
        "url_env": "WEBHOOK_REMISIONES_URL",
        "header_nombre_env": "WEBHOOK_REMISIONES_HEADER_NOMBRE",
        "header_valor_env": "WEBHOOK_REMISIONES_HEADER_VALOR",
        "confirmar": True,
        "mensaje_confirmacion": "¿Confirmas disparar el flujo de remisiones? Esta acción activa el proceso real en n8n.",
    },
    {
        "id": "reporte_crm",
        "etiqueta": "📊 Actualizar Reporte CRM (n8n)",
        "url_env": "WEBHOOK_REPORTE_CRM_URL",
        "header_nombre_env": "WEBHOOK_REMISIONES_HEADER_NOMBRE",
        "header_valor_env": "WEBHOOK_REMISIONES_HEADER_VALOR",
        "confirmar": True,
        "mensaje_confirmacion": "¿Confirmas disparar el flujo de Reporte CRM?",
    },
]
# oct-2026: se retiraron los botones "Actualizar STC" y "Linkear pantallazos y crear
# paquetes". Disparaban workflows en repos de SGC140 (Sebastián) con sus tokens
# (GITHUB_TOKEN / GITHUB_TOKEN2). La lista vacía hace que app.py no pinte botones.
GITHUB_ACTIONS_REGISTRADOS = []
