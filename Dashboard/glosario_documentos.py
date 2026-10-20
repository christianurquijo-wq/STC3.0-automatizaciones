# glosario_documentos.py
import re
import csv
import json
import os
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

def _obtener_config(nombre_env: str) -> str:
    try:
        return st.secrets[nombre_env]
    except Exception:
        return os.getenv(nombre_env)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CARPETA_RAIZ_ID = _obtener_config("FOLDERS_PARTICIPANTES")

PATRON_NOMBRE = re.compile(r"^\d+_(.+?)(?:\.[a-zA-Z0-9]+)?$")

def _credenciales_drive():
    with open(".streamlit/service_account.json") as f:
        info = json.load(f)
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def _listar_archivos_recursivo(service, carpeta_id: str, ruta_actual: str, resultados: list):
    query = f"'{carpeta_id}' in parents and trashed = false"
    pagina = None

    while True:
        respuesta = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=pagina,
        ).execute()

        for archivo in respuesta.get("files", []):
            nombre = archivo["name"]
            ruta_completa = f"{ruta_actual}/{nombre}"

            if archivo["mimeType"] == "application/vnd.google-apps.folder":
                _listar_archivos_recursivo(service, archivo["id"], ruta_completa, resultados)
            else:
                resultados.append({"nombre_archivo": nombre, "ruta": ruta_completa})

        pagina = respuesta.get("nextPageToken")
        if not pagina:
            break


def generar_glosario():
    creds = _credenciales_drive()
    service = build("drive", "v3", credentials=creds)

    print("Recorriendo carpetas...")
    resultados = []
    _listar_archivos_recursivo(service, CARPETA_RAIZ_ID, "raíz", resultados)
    print(f"Total de archivos encontrados: {len(resultados)}")

    glosario = {}
    for item in resultados:
        match = PATRON_NOMBRE.match(item["nombre_archivo"])
        if not match:
            continue
        nombre_extraido = match.group(1).strip()

        if nombre_extraido not in glosario:
            glosario[nombre_extraido] = {
                "nombre_documento": nombre_extraido,
                "ruta_primera_aparicion": item["ruta"],
                "cantidad_apariciones": 1,
            }
        else:
            glosario[nombre_extraido]["cantidad_apariciones"] += 1

    lista_final = sorted(glosario.values(), key=lambda x: x["nombre_documento"])

    with open("glosario_documentos.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["nombre_documento", "ruta_primera_aparicion", "cantidad_apariciones"])
        writer.writeheader()
        writer.writerows(lista_final)

    print(f"Glosario generado: {len(lista_final)} nombres únicos -> glosario_documentos.csv")


if __name__ == "__main__":
    generar_glosario()