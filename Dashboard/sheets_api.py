# sheets_api.py
import os
import time
import httplib2
import plotly.express as px
import streamlit as st
import threading
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()
try:
    _API_KEY = st.secrets["GOOGLE_API_KEY"] 
except Exception:
    _API_KEY = os.getenv("GOOGLE_API_KEY")

_local = threading.local()

def _get_service():
    if not hasattr(_local, "service"):
        http = httplib2.Http(timeout=20)
        _local.service = build("sheets", "v4", developerKey=_API_KEY, http=http)
    return _local.service

def _con_reintentos(func, intentos=3, espera_base=2):
    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            return func()
        except Exception as e:
            ultimo_error = e
            if intento < intentos:
                time.sleep(espera_base * intento)
    raise ultimo_error

@st.cache_data(ttl=86400)
def _get_sheet_title(spreadsheet_id: str, gid: str) -> str:
    service = _get_service()
    meta = _con_reintentos(lambda: service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties"
    ).execute())
    for sheet in meta["sheets"]:
        props = sheet["properties"]
        if str(props["sheetId"]) == str(gid):
            return props["title"]
    raise ValueError(f"No encontré una pestaña con gid={gid} en el archivo {spreadsheet_id}")

def obtener_valores_crudos(spreadsheet_id: str, gid: str) -> list:
    service = _get_service()
    titulo = _get_sheet_title(spreadsheet_id, gid)
    resultado = _con_reintentos(lambda: service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{titulo}'",
        valueRenderOption="FORMATTED_VALUE",
    ).execute())
    return resultado.get("values", [])