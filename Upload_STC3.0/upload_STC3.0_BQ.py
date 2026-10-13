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

sheet = client_sheets.open_by_key(SEGUIMIENTO_STC)
Hoja_Seguimiento = sheet.worksheet("SEGUIMIENTO GENERAL")
Datos = Hoja_Seguimiento.get_all_values()
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