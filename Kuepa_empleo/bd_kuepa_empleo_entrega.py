"""
Base de entrega «AAAAMMDD Anexo No. 4 Base exportable plataforma de empleo Kuepa.csv».

Lee los últimos PROFILE / OFERTAS / LOCALIDADES de la carpeta CARPETA_KUEPA_EMPLEO, arma la base y:
  1. guarda el CSV junto al script (como siempre), y
  2. lo sube a la carpeta de entregas en la unidad compartida (CARPETA_ENTREGA_KUEPA_EMPLEO; por defecto la de
     Socios Talento Capital). Si ese día ya existe un archivo con el mismo nombre, lo reemplaza (no duplica).

Se puede correr desde VS Code o desde el Panel de Operaciones (GitHub Actions: workflow ops_run_script.yml).
En el panel no hay navegador: Drive se usa con la cuenta de servicio (applied-plexus), que debe tener acceso de
«Colaborador» o superior en la unidad compartida de destino y acceso de lectura a la carpeta de insumos.
"""
from dotenv import load_dotenv, find_dotenv
import pandas as pd
import os
from datetime import datetime
import pydrive2
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv(find_dotenv(), override=True)

try:
    ruta_base = os.path.dirname(os.path.abspath(__file__))
except NameError:
    ruta_base = os.getcwd()

if "CONFIG_SEGURIDAD" in os.listdir(ruta_base):
    ruta_global = ruta_base
else:
    ruta_global = os.path.dirname(ruta_base)
    
ruta_boveda = os.path.join(ruta_global, "CONFIG_SEGURIDAD")
json_plexus = os.path.join(ruta_boveda, "applied-plexus-476714-n0-d7c1f0400cc6.json")
json_credentials = os.path.join(ruta_boveda, "credentials_module.json")
json_client = os.path.join(ruta_boveda, "client_secrets.json")

credentials_drive = json_credentials
def loggin_drive():
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile(credentials_drive)
    if gauth.access_token_expired:
        gauth.Refresh() 
        gauth.SaveCredentialsFile(credentials_drive)
    else:
        gauth.Authorize()
    return GoogleDrive(gauth)

scope = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]

Credenciales = ServiceAccountCredentials.from_json_keyfile_name(json_plexus, scope)
client = gspread.authorize(Credenciales)

# Drive con la cuenta de servicio (sirve igual en tu PC y en el panel, sin token de navegador que se venza)
drive_sa = build("drive", "v3", cache_discovery=False,
                 credentials=service_account.Credentials.from_service_account_file(json_plexus, scopes=scope))
carpeta_kuepa_empleo = os.getenv("CARPETA_KUEPA_EMPLEO")
# Carpeta de entregas en la unidad compartida (se puede cambiar en el .env sin tocar el código)
CARPETA_ENTREGA = os.getenv("CARPETA_ENTREGA_KUEPA_EMPLEO") or "1mmz2mFejTjx0KQqukPbG09sHBB42-r6b"


def listar_insumos(carpeta):
    """Archivos de la carpeta de insumos. Primero con la cuenta de servicio; si no ve nada (la carpeta no está
    compartida con ella), con tu acceso de Drive de siempre (credentials_module.json)."""
    archivos, pagina = [], None
    try:
        while True:
            r = drive_sa.files().list(q=f"'{carpeta}' in parents and trashed=false", pageToken=pagina,
                                      fields="nextPageToken, files(id, name, createdTime, modifiedTime)",
                                      supportsAllDrives=True, includeItemsFromAllDrives=True, pageSize=200).execute()
            archivos += [{"Nombre": f["name"], "ID": f["id"], "Hora": f["createdTime"],
                          "Hora_Actualización": f["modifiedTime"]} for f in r.get("files", [])]
            pagina = r.get("nextPageToken")
            if not pagina:
                break
    except Exception as e:
        print(f"Aviso: la cuenta de servicio no pudo listar la carpeta de insumos ({type(e).__name__}).")
    if archivos:
        return archivos
    print("Listando la carpeta de insumos con credentials_module.json…")
    drive = loggin_drive()
    return [{"Nombre": a['title'], "ID": a['id'], "Hora": a['createdDate'], "Hora_Actualización": a['modifiedDate']}
            for a in drive.ListFile({'q': f"'{carpeta}' in parents and trashed=false"}).GetList()]


def subir_a_drive(ruta, carpeta):
    """Sube el CSV a la carpeta (unidad compartida). Si ya hay uno con el mismo nombre, lo reemplaza. Devuelve el enlace."""
    nombre = os.path.basename(ruta)
    nombre_q = nombre.replace("\\", "\\\\").replace("'", "\\'")
    existentes = drive_sa.files().list(q=f"'{carpeta}' in parents and name = '{nombre_q}' and trashed=false",
                                       fields="files(id)", supportsAllDrives=True,
                                       includeItemsFromAllDrives=True).execute().get("files", [])
    media = MediaFileUpload(ruta, mimetype="text/csv", resumable=True)
    if existentes:
        f = drive_sa.files().update(fileId=existentes[0]["id"], media_body=media, fields="id, webViewLink",
                                    supportsAllDrives=True).execute()
    else:
        f = drive_sa.files().create(body={"name": nombre, "parents": [carpeta]}, media_body=media,
                                    fields="id, webViewLink", supportsAllDrives=True).execute()
    return f.get("webViewLink", f"https://drive.google.com/file/d/{f['id']}/view")


metadata_total = listar_insumos(carpeta_kuepa_empleo)
if not metadata_total:
    raise SystemExit("No encontré archivos en la carpeta de insumos (CARPETA_KUEPA_EMPLEO). Revisa el .env y que "
                     "la carpeta esté compartida con la cuenta de servicio.")

metadata_df = pd.DataFrame(metadata_total)
metadata_df['Categoría'] = metadata_df['Nombre'].str.extract(r'(PROFILE|OFERTAS|LOCALIDADES)')
metadata_df['Hora'] = pd.to_datetime(metadata_df['Hora'])
metadata_df = metadata_df.sort_values(by='Hora', ascending=False).copy()
metadata_df = metadata_df.drop_duplicates(subset=['Categoría'], keep='first')

metadata_df = metadata_df.dropna(subset=['Categoría'])  # otros archivos de la carpeta no cuentan
faltan = {"PROFILE", "OFERTAS", "LOCALIDADES"} - set(metadata_df['Categoría'].dropna())
if faltan:
    raise SystemExit(f"Faltan insumos en la carpeta CARPETA_KUEPA_EMPLEO: {', '.join(sorted(faltan))}. "
                     "Sube los archivos del día (sus nombres deben contener PROFILE, OFERTAS y LOCALIDADES).")
print("Insumos usados (los más recientes de cada tipo):")
for _, f in metadata_df.iterrows():
    print(f"  - {f['Categoría']}: {f['Nombre']} (creado {f['Hora']:%Y-%m-%d %H:%M} UTC)")

for indice, fila in metadata_df.iterrows():
    id = fila['ID']
    documento = fila['Categoría'] 
    if 'LOCALIDADES' in documento:
        localidades = fila['ID']
    elif 'OFERTAS' in documento:
        ofertas = fila['ID']
    elif 'PROFILE' in documento:
        profile = fila['ID']

data_localidades = client.open_by_key(localidades).worksheet("Hoja 1").get_all_values()
data_ofertas = client.open_by_key(ofertas).worksheet("Hoja 1").get_all_values()
data_kuepa_empleo = client.open_by_key(profile).worksheet("Hoja 1").get_all_values()

df = pd.DataFrame(data_kuepa_empleo[1:], columns=data_kuepa_empleo[0])
df_ofertas = pd.DataFrame(data_ofertas[1:], columns=data_ofertas[0])
df_ofertas = df_ofertas.drop_duplicates(subset=['job_offer_id', 'profile_id'], keep='last')
df_localidades = pd.DataFrame(data_localidades[1:], columns=data_localidades[0])

df = df[df['curriculum_id'] != ""]
df = df[df["curriculum_id"].notna()]
df = df[df["curriculum_id"].notnull()]
df = df[df['id_curriculum'] != ""]
df = df[df["id_curriculum"].notna()]
df = df[df["id_curriculum"].notnull()]

df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
df = df.dropna(subset=['created_at'])

df['doc_number'] = df['doc_number'].astype(str).str.strip()
df_localidades['PROFILE_DOC_NUMBER'] = df_localidades['PROFILE_DOC_NUMBER'].astype(str).str.strip()

df = pd.merge(
    left = df, right= df_ofertas,
    how = 'left',
    left_on = 'profile_id', right_on='profile_id')
df = pd.merge(
    left=df, right=df_localidades,
    how = 'left',
    left_on='doc_number', right_on='PROFILE_DOC_NUMBER' 
)

df['created_at_x'] = pd.to_datetime(df['created_at_x'], errors='coerce')
excepciones = [
    'profile_id', 'occupational_interest', 'job_offer_id', 'job_offer_name', 
    'company_id', 'company_name', 'nit', 'sector_name', 'professional', 'created_at_x'
]
cols_a_actualizar = [columna for columna in df.columns if columna not in excepciones]
df_reciente = df.sort_values(by='created_at_x', ascending=False)
df_reciente = df_reciente.drop_duplicates(subset=['profile_id'], keep='first')
df_reciente = df_reciente[['profile_id'] + cols_a_actualizar]
df = df.drop(columns=cols_a_actualizar)
df = pd.merge(df, df_reciente, on='profile_id', how='left')

df = df[df['created_at_x'].dt.year >= 2026]

columnas_finales = ['doc_type','doc_number','first_name','last_name','birthdate','sex','phone','mobile_phone',
                    'address_street','location_in_bogota_answer_label','neighborhood','email','id_curriculum','curriculum_id','date',
                    'offerer','professional','reason','observation','remission_concept','created_at_x','occupational_interest',
                    'profile_id','job_offer_id','job_offer_name','company_id','company_name','nit','sector_name']

df.columns = df.columns.str.lower().str.strip()

df = df[columnas_finales]
df = df.rename(columns={'location_in_bogota_answer_label': 'localidad',
                        'created_at_x': 'created_at',
                        'profile_id_x': 'profile_id'})
df['Marc colocacion'] = None
df['curriculum_id'] = '100%'

df = df.sort_values(by='doc_number')
df = df.drop_duplicates(subset='doc_number')

fecha_hoy = datetime.today()
fecha_formateada = fecha_hoy.strftime('%Y%m%d')
nombre_archivo = f"{fecha_formateada} Anexo No. 4 Base exportable plataforma de empleo Kuepa.csv"

ruta_csv = os.path.join(ruta_base, nombre_archivo)
df.to_csv(ruta_csv, index=False)
print(f"CSV generado: {nombre_archivo} ({len(df)} registros).")

enlace = subir_a_drive(ruta_csv, CARPETA_ENTREGA)
print(f"Subido a Drive: {enlace}")