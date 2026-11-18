import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import bigquery
import dotenv 
from dotenv import load_dotenv
import os

load_dotenv()
load_dotenv(override=True)
SEGUIMIENTO_STC = os.getenv("SHEET_ID_GENERAL")

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET_ID = "EFE_2026"
TABLE_ID   = "STC_3_0_V2_2026"

# oct-2026: busca credenciales.json junto al script o en la raíz del repo, sin
# depender de la carpeta desde donde se ejecute (local, trigger o GitHub Actions).
_BASE = os.path.dirname(os.path.abspath(__file__))
Credentials_File = next(
    (p for p in (os.path.join(_BASE, "credenciales.json"),
                 os.path.join(os.path.dirname(_BASE), "credenciales.json"))
     if os.path.exists(p)),
    "credenciales.json",
)

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(Credentials_File, scopes=scopes)
client_sheets = gspread.authorize(creds)

import csv
import io
import time

import requests
from gspread.exceptions import APIError
from gspread.utils import rowcol_to_a1

ERRORES_PASAJEROS = (429, 500, 502, 503, 504)


def _con_reintentos(funcion, intentos=5, que="Google Sheets"):
    """nov-2026: la hoja es pesada y Google a veces responde 503/500/429 o corta la conexión.
    Se reintenta con espera creciente (20, 40, 80, 160 s) antes de rendirse."""
    for n in range(intentos):
        try:
            return funcion()
        except (APIError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            codigo = getattr(getattr(e, "response", None), "status_code", None)
            if (isinstance(e, APIError) and codigo not in ERRORES_PASAJEROS) or n == intentos - 1:
                raise
            espera = 20 * 2 ** n
            print(f"{que} respondió {codigo or type(e).__name__}; reintento {n + 1}/{intentos - 1} en {espera} s")
            time.sleep(espera)


def _leer_csv(gid: int) -> list[list[str]]:
    """Camino principal: exporta la pestaña como CSV (una sola descarga, la arma el servicio de
    exportación de Google). Con hojas pesadas suele funcionar cuando la API de valores da 503."""
    url = f"https://docs.google.com/spreadsheets/d/{SEGUIMIENTO_STC}/export"
    r = client_sheets.http_client.session.get(url, params={"format": "csv", "gid": gid}, timeout=300)
    if r.status_code in ERRORES_PASAJEROS:
        raise APIError(r)
    r.raise_for_status()
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))


def _leer_por_bloques(hoja, ultima_col: int, filas_bloque: int = 1500) -> list[list[str]]:
    """Respaldo: la API de valores en bloques de filas (respuestas pequeñas, menos 503)."""
    datos, inicio = [], 1
    while inicio <= hoja.row_count:
        fin_bloque = min(inicio + filas_bloque - 1, hoja.row_count)
        rango = f"A{inicio}:{rowcol_to_a1(fin_bloque, ultima_col)}"
        bloque = _con_reintentos(lambda: hoja.get_values(rango))
        datos += bloque
        if len(bloque) < filas_bloque and inicio > 4:
            break  # se acabaron las filas con datos
        inicio = fin_bloque + 1
    return datos


sheet = _con_reintentos(lambda: client_sheets.open_by_key(SEGUIMIENTO_STC))
Hoja_Seguimiento = _con_reintentos(lambda: sheet.worksheet("SEGUIMIENTO GENERAL"))
try:
    Datos = _con_reintentos(lambda: _leer_csv(Hoja_Seguimiento.id), intentos=3, que="Exportación CSV")
    origen = "exportación CSV"
except Exception as e:  # noqa: BLE001 -- si la exportación no está disponible, se intenta por la API
    print(f"La exportación CSV falló ({type(e).__name__}); se lee por bloques con la API de valores.")
    _ultima_col = len(_con_reintentos(lambda: Hoja_Seguimiento.row_values(4))) or Hoja_Seguimiento.col_count
    Datos = _leer_por_bloques(Hoja_Seguimiento, _ultima_col)
    origen = "API por bloques"
# Igual que antes: encabezados en la fila 4; las columnas sin encabezado se descartan más abajo.
_ancho = len(Datos[3])
Datos = [(fila + [""] * _ancho)[:_ancho] for fila in Datos]
print(f"Seguimiento general: {len(Datos) - 4} filas · {_ancho} columnas (vía {origen})")
DF = pd.DataFrame(Datos[4:], columns=Datos[3])
Headers = DF.columns
DF = DF.loc[:, DF.columns != ""]

DF = DF.replace(r'^\s*$', None, regex=True)
DF = DF.where(pd.notnull(DF), None)
DF = DF.dropna(subset=['CC Prospecto'])

Columnas_numericas = ['CANTIDAD DE LOGS','TIEMPO DE LOGUEO','TIEMPO SINCRÓNICO','TOTAL TIEMPO CURSO','Número de horas', '#', 'Tipo de paquete reportado']

DF[Columnas_numericas] = DF[Columnas_numericas].replace(",", ".", regex=True) 
DF[Columnas_numericas] = DF[Columnas_numericas].apply(pd.to_numeric, errors = 'coerce')

Columnas_fecha = [columna for columna in DF.columns if 'fecha' in columna.lower().strip()]
Columnas_fecha.append('Certificado')
DF[Columnas_fecha] = DF[Columnas_fecha].apply(pd.to_datetime, errors='coerce', dayfirst=True)
DF[Columnas_fecha] = DF[Columnas_fecha].apply(lambda x: x.dt.strftime('%Y-%m-%d'))

DF.columns = (DF.columns
              .str.replace(" ","_")
              .str.normalize('NFKD')
              .str.encode('ascii', errors='ignore')
              .str.decode('utf-8')
              .str.lower()
              .str.replace(r"[\r\n]+", "", regex=True)
              .str.replace(r"[^a-z0-9_#_.]", "", regex=True)              
              )

DF = DF.rename(columns={".": "o"})

DF = DF.loc[:, ~DF.columns.duplicated()]

DF['proyecto'] = "Socios Talento Capital 3.0"

print(DF.columns.to_list())


client_bq = bigquery.Client.from_service_account_json(Credentials_File)
table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

from validacion_dataframes import validar_y_comparar
validar_y_comparar(Hoja_Seguimiento.title, DF, client_bq, table_ref)

job = client_bq.load_table_from_dataframe(
    DF,
    table_ref,
    job_config=bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        autodetect=True
    )
)

job.result()
print("Verificado")