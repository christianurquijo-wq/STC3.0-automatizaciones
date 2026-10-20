# sheets_write.py
import json
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _credenciales_servicio():
    try:
        info = dict(st.secrets["gcp_service_account"])
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    except Exception:
        with open(".streamlit/service_account.json") as f:
            info = json.load(f)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def _service_escritura():
    creds = _credenciales_servicio()
    return build("sheets", "v4", credentials=creds)


def _columna_a_letra(indice_0based: int) -> str:
    letra = ""
    n = indice_0based + 1
    while n > 0:
        n, resto = divmod(n - 1, 26)
        letra = chr(65 + resto) + letra
    return letra


def marcar_documento_cargado(spreadsheet_id: str, sheet_title: str, fila_sheet: int, columna_indice: int, valor: bool) -> tuple:
    try:
        service = _service_escritura()
        letra = _columna_a_letra(columna_indice)
        rango = f"'{sheet_title}'!{letra}{fila_sheet}"
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=rango,
            valueInputOption="RAW", body={"values": [[valor]]},
        ).execute()
        estado_texto = "marcado" if valor else "desmarcado"
        return True, f"Documento {estado_texto} correctamente."
    except Exception as e:
        return False, f"Error al escribir: {e}"