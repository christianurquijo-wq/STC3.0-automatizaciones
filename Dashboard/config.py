# config.py
import os
import time
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

def _obtener_config(nombre_env: str) -> str:
    try:
        return st.secrets[nombre_env]
    except Exception:
        return os.getenv(nombre_env)

FUENTES = {
    "general": {
        "id": _obtener_config("SHEET_ID_GENERAL"),
        "gid": "0",
        "ancla": "CC Prospecto",
    },
    "formacion": {
        "id": _obtener_config("SHEET_ID_FORMACION"),
        "gid": "225050212",
        "ancla": "Cedula",
    },
    "orientacion_consolidado": {
        "id": _obtener_config("SHEET_ID_CONSOLIDADO_FCS"),
        "gid": "978755551",
        "ancla": "NÚMERO DE DOCUMENTO",
    },
    "remisiones": {
        "id": _obtener_config("SHEET_ID_REMISIONES"),
        "gid": "0",
        "ancla": "NÚMERO DE DOCUMENTO",
    },
    "verificacion": {
        "id": _obtener_config("SHEET_ID_VERIFICACION"),
        "gid": "1240996279",
        "ancla": "Número Documento",
    },
    "encuesta_basico_jco": {
        "id": _obtener_config("SHEET_ID_MITIGACION_ENCUESTA"),
        "gid": "851734049",
        "ancla": "CEDULA",
    },
    "encuesta_especializado": {
        "id": _obtener_config("SHEET_ID_MITIGACION_ENCUESTA"),
        "gid": "1685171350",
        "ancla": "CEDULA",
    },
    "parametros": {
        "id": _obtener_config("SHEET_ID_GENERAL"),
        "gid": "1516261654",
        "ancla": "Mes",
    },
    "matriz_documental": {
        "id": _obtener_config("SHEET_ID_MATRIZ_DOCUMENTAL"),
        "gid": "1167929471",
        "ancla": "CÉDULA",
    },
    "subsanaciones": {
        "id": _obtener_config("SHEET_ID_CONSOLIDADO_FCS"),
        "gid": "1376346035",
        "ancla": "Documento",
    },
        "formacion_consolidado": {
        "id": _obtener_config("SHEET_ID_FORMACION"),
        "gid": "0",
        "ancla": "No. DOCUMENTO",
    },
}

def url_csv(nombre_fuente: str) -> str:
    f = FUENTES[nombre_fuente]
    return f"https://docs.google.com/spreadsheets/d/{f['id']}/export?format=csv&gid={f['gid']}&_={int(time.time())}"