from google import genai
from google.genai import types
from google.genai import errors
from dotenv import load_dotenv, find_dotenv
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from gspread.utils import rowcol_to_a1
import pydrive2
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
import os
import re
import time
import pandas as pd
import glob
import json

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
drive = loggin_drive()

api_key_genai = os.getenv("api_gemini_respaldo")
agente = genai.Client(api_key=api_key_genai)

Modelo_1 = 'gemini-3.8-flash'
Modelo_2 = 'gemini-3.7-flash'
Modelo_3 = 'gemini-3.6-flash'
Modelo_4 = 'gemini-3.5-flash'
Modelo_5 = 'gemini-2.5-flash'

configuraciones_totales = [Modelo_1, Modelo_2, Modelo_3]

archivos_nube_genai = agente.files.list()
if archivos_nube_genai is not False:
    for archivo in archivos_nube_genai: 
        _ = agente.files.delete(name=archivo.name)
 
referencia_tokens = drive.CreateFile({'id': os.getenv("referencia")})
referencia_tokens.FetchMetadata()
nombre_temporal = "referencia_temporal.png"
referencia_tokens.GetContentFile(nombre_temporal)
referencia_tokens = nombre_temporal

with open("AUDITORIA_PAQIETES/system_instructions.txt", "r", encoding="utf-8") as instructions:
    system_instructions = instructions.read()

with open("AUDITORIA_PAQIETES/prompt_referencia.txt", "r", encoding="utf-8") as prompt_r:
    prompt_referencia = prompt_r.read()

try:
    referencia_file = agente.files.upload(
        file=referencia_tokens
    )
except Exception as error:
    print(f"Error upload: {error}")

tokens_archivo = agente.models.count_tokens(
    model = Modelo_1,
    contents= [system_instructions, referencia_file, prompt_referencia]
    )

with open("AUDITORIA_PAQIETES/peor_respuesta.txt", "r", encoding="utf-8") as respuesta:
    peor_respuesta = respuesta.read()

tokens_maximos_salida = agente.models.count_tokens(
    model = Modelo_1,
    contents = [peor_respuesta]
)

calculo_input = tokens_archivo.total_tokens
calculo_output = tokens_maximos_salida.total_tokens

limite_input = 1000000
limite_output = 8192
buffer_input = 50000
buffer_output = 1000

max_input = (limite_input - buffer_input) // calculo_input
max_output = (limite_output - buffer_output) // calculo_output

tamano_lote_teorico = min(max_input, max_output)
margen_alucinacion = 15
tamano_lote = tamano_lote_teorico - margen_alucinacion

with open("AUDITORIA_PAQIETES/prompt.txt", "r", encoding="utf-8") as content:
    prompt = content.read()

scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]

Credenciales = ServiceAccountCredentials.from_json_keyfile_name(json_plexus, scope)
client = gspread.authorize(Credenciales) 

documento = os.getenv("consolidado_formacion")
sheets = client.open_by_key(documento)
hoja = sheets.worksheet('CERTIFICADOS')

try:
    columna_match_rev = hoja.find("REVISIÓN PAQUETE", in_row=1)
    columna_match_obs = hoja.find("OBSERVACIÓN PAQUETE", in_row=1)

    num_col_rev = columna_match_rev.col
    num_col_obs = columna_match_obs.col

except Exception:
    exit()

datos = hoja.get_all_values()
df = pd.DataFrame(datos[1:], columns=datos[0])
df = df[df['REVISIÓN PAQUETE'] == ""]
df = df[df['PAQUETE - FORMACIÓN'] != ""]
df = df[df['RESPONDABLE REVISIÓN'] == "GEMINI"]

print(f"Hay {len(df)} para auditar")

lotes_totales = [df[i:i + tamano_lote] for i in range(0, len(df), tamano_lote)]
print(f"Se procesarán en {len(lotes_totales)} lotes de máximo {tamano_lote} usuarios por petición")

for numero_lote, lote_df in enumerate(lotes_totales):
    print(f"Auditando Lote {numero_lote + 1} de {len(lotes_totales)}")

    contenidos_prompt = [prompt]
    archivos_subidos_gemini = []
    archivos_locales = []

    for indice, fila in lote_df.iterrows():
        archivo = fila['PANTALLAZO']
        archivo = re.search(r'/d/([a-zA-Z0-9_-]+)', archivo)
        if not archivo:
            print(f"Error extracción ID de {fila['DOCUMENTO']}")
            continue
        archivo = archivo.group(1)

        try:
            file_drive = drive.CreateFile({'id': archivo})
            nombre_local =f"temp_{fila['DOCUMENTO']}.png"
            file_drive.GetContentFile(nombre_local)
            archivos_locales.append(nombre_local)

            archivo_gemini = agente.files.upload(file=nombre_local)
            archivos_subidos_gemini.append(archivo_gemini)

            texto_diccionario = f"""
            --- CASO ---
            {{
              "nombre_estudiante": "{fila['NOMBRE']}",
              "documento": "{fila['DOCUMENTO']}",
              "curso": "{fila['CURSO']}",
              "fecha_finalizacion": "{fila['FECHA FINALIZACIÓN']}"
            }}
            """
            contenidos_prompt.append(archivo_gemini)
            contenidos_prompt.append(texto_diccionario)

        except Exception as error:
            print(f"Error en la descarga/subida del documento {fila['DOCUMENTO']}: {error}")

    temporales_subidos = glob.glob("*.png")
    for temporal in temporales_subidos:
        os.remove(temporal)

    if len(archivos_subidos_gemini) > 0:

        max_intentos_503 = 20 - 1

        print(f"Procesando {len(archivos_subidos_gemini)} casos")
        for modelo in configuraciones_totales:
            modelo_exitoso = False

            for intento in range(max_intentos_503):
                print(f"Auditando paquetes del {numero_lote + 1} lote, con el modelo {modelo}. Intento {intento + 1}  de {max_intentos_503 + 1}")
                try:
                    respuesta = agente.models.generate_content(
                        model=modelo,
                        contents = contenidos_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instructions,
                            temperature=0.0,
                            response_mime_type="application/json"
                        )

                    )

                    resultado_auditoria_ia = json.loads(respuesta.text)
                    if isinstance(resultado_auditoria_ia, dict):
                        resultado_auditoria_ia = [resultado_auditoria_ia]

                    for resultado in resultado_auditoria_ia:

                        doc = str(resultado.get('documento'))
                        estado = resultado.get('Estado')
                        observacion = resultado.get('Observacion')

                        indices_laterales = df.index[df['DOCUMENTO'] == doc].tolist()
                        fila = indices_laterales[0] + 2
                        rango_estado = rowcol_to_a1(fila, num_col_rev)
                        rango_observacion = rowcol_to_a1(fila, num_col_obs)

                        _ = hoja.update(range_name=rango_estado, values=[[estado]])
                        _ = hoja.update(range_name=rango_observacion, values=[[observacion]])
                        
                    modelo_exitoso = True
                    break

                except errors.APIError as error:
                    print(f"Error durante la generación o escritura:")

                    if "503" in str(error):
                        if intento < max_intentos_503:
                            print(f"Servicio sobrecargado (503). Reintento en 10s")
                            time.sleep(10)
                        else:
                            print(f"intentos agotados para {modelo}, paso al siguiente")
                            break

                    elif "429" in str(error):
                        print(f"Error por límite de cuota para el modelo {modelo}. Paso al siguiente")
                        break

                    else:
                        print(f"Error fuera de las tipificaciones clásicas {error}")
                        break

            if modelo_exitoso:
                break

    print("Eliminando archivos de la nube")
    for archivo_nube in archivos_subidos_gemini:
           
           _ = agente.files.delete(name=archivo_nube.name)
    print("Totalidad de archivos eliminados")

print("Auditoría Finalizada")

print(resultado_auditoria_ia)