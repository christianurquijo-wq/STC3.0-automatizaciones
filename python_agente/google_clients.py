"""
Reemplaza lo que en Apps Script hacían automáticamente DriveApp/SpreadsheetApp
(la autorización venía gratis por correr dentro del contenedor de Google).
Aquí en Python hace falta una CUENTA DE SERVICIO de Google Cloud, compartida
explícitamente con acceso a la carpeta raíz de Drive y a las Sheets — ver el
README de este proyecto ("Setup: cuenta de servicio") para los pasos exactos.

Variables de entorno esperadas (ver .env.example):
  GOOGLE_SERVICE_ACCOUNT_FILE   ruta a un archivo JSON de credenciales, o
  GOOGLE_SERVICE_ACCOUNT_JSON   el contenido JSON de esas credenciales como texto
                                 (útil para Streamlit Cloud / Secrets, donde no
                                 siempre hay un archivo en disco).
"""
import io
import json
import os
from typing import List, Optional

import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

MIME_FOLDER = 'application/vnd.google-apps.folder'


def obtener_credenciales():
    ruta = os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE')
    contenido = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')

    if ruta:
        return service_account.Credentials.from_service_account_file(ruta, scopes=SCOPES)
    if contenido:
        info = json.loads(contenido)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    raise RuntimeError(
        'No hay credenciales de la cuenta de servicio configuradas. Define '
        'GOOGLE_SERVICE_ACCOUNT_FILE (ruta a un .json) o GOOGLE_SERVICE_ACCOUNT_JSON '
        '(el contenido de ese .json como variable de entorno / secret). Ver README.md, '
        'sección "Setup: cuenta de servicio".'
    )


def obtener_servicio_drive(credenciales=None):
    credenciales = credenciales or obtener_credenciales()
    return build('drive', 'v3', credentials=credenciales, cache_discovery=False)


def obtener_cliente_sheets(credenciales=None) -> gspread.Client:
    credenciales = credenciales or obtener_credenciales()
    return gspread.authorize(credenciales)


def listar_subcarpetas(drive_service, carpeta_id: str) -> List[dict]:
    """Equivalente a folder.getFolders(): subcarpetas directas, [{id, name}], con paginación."""
    return _listar_hijos(drive_service, carpeta_id, f"mimeType = '{MIME_FOLDER}'")


def listar_archivos(drive_service, carpeta_id: str) -> List[dict]:
    """Equivalente a folder.getFiles(): archivos directos (no carpetas), [{id, name}], con paginación."""
    return _listar_hijos(drive_service, carpeta_id, f"mimeType != '{MIME_FOLDER}'")


def _listar_hijos(drive_service, carpeta_id: str, condicion_mime: str) -> List[dict]:
    resultado = []
    token = None
    query = f"'{carpeta_id}' in parents and {condicion_mime} and trashed = false"
    while True:
        resp = drive_service.files().list(
            q=query,
            fields='nextPageToken, files(id, name)',
            pageSize=1000,
            pageToken=token,
        ).execute()
        resultado.extend(resp.get('files', []))
        token = resp.get('nextPageToken')
        if not token:
            break
    return resultado


def descargar_bytes_archivo(drive_service, file_id: str) -> bytes:
    """Equivalente a archivo.getBlob().getBytes()."""
    request = drive_service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    listo = False
    while not listo:
        _, listo = downloader.next_chunk()
    return buffer.getvalue()


def obtener_o_crear_hoja(spreadsheet: gspread.Spreadsheet, nombre: str) -> gspread.Worksheet:
    """Equivalente a obtenerOCrearHoja_(ss, nombre) de Utilidades.gs."""
    try:
        return spreadsheet.worksheet(nombre)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=nombre, rows=1000, cols=26)
