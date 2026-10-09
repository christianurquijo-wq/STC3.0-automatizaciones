from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv, find_dotenv
from pypdf import PdfWriter
from PIL import Image
import gspread
import os
import time
import pdfkit
import pandas as pd

import pickle
import selenium
from selenium import webdriver
from selenium.webdriver import Chrome
from selenium.webdriver.common.by import By
from selenium.webdriver.common import options
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait

driver = webdriver.Chrome()
wait = WebDriverWait(driver, 10)

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

ruta_wkhtmltopdf = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
try:
    config_pdfkit = pdfkit.configuration(wkhtmltopdf=ruta_wkhtmltopdf)
except Exception as e:
    print(f"Error cargando wkhtmltopdf: {e}")
    exit()

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

scope = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]

credenciales = ServiceAccountCredentials.from_json_keyfile_name(json_plexus, scope)
client = gspread.authorize(credenciales) 
documento = client.open_by_key("EVIDENCIAS_AUTOPOSTULACION")
hoja = documento.worksheet("")

datos = hoja.get_all_values()
folder = os.getenv("")

df = pd.DataFrame(hoja[1:], columns=datos[0])
link_inicial = os.getenv("url")
user = os.getenv("user_empleo")
password = os.getenv("password_empleo")

cookies_file = 'cookies.pkl'
if not os.path.exists(cookies_file):
    driver.get(link_inicial)
    loggin_user = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "")
        )
    ).send_keys(user)

    loggin_password = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "")
        )
    ).send_keys(password)

with open("cookies.pkl", "rb") as functional_file:
    cookies = pickle.load(functional_file)
for cookie in cookies:
    driver.add_cookie(cookie)

driver.refresh()   

for indice, fila in df.iterrows():
    
    documento = fila['usuario']
    nombre = fila['usuario']
    profile_id = fila['usuario']

    link_per_user = f"{link_inicial}/curriculum/{profile_id}"
    driver.get(link_per_user)
    driver.save_screenshot("informacion_personal_temporal.png")

    try:
        autopostulacion = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "")
                )
            )

        autopostulacion.click()
        driver.save_screenshot("informacion_autopostulacion_temporal.png")

        imagen_1 = Image.open("informacion_personal_temporal.png")
        imagen_2 = Image.open("informacion_autopostulacion_temporal.png")

        imagen1_rgb = imagen_1.convert('RGB')
        imagen2_rgb = imagen_2.convert('RGB')

        consolidado = imagen1_rgb.save(
            f'{documento}_EVIDENCIA AUTOPOSTULACIÓN.pdf',
            save_all=True,
            append_images=[imagen2_rgb]
            )

        temp = f'{documento}_EVIDENCIA AUTOPOSTULACIÓN.pdf'
        drive_file = drive.CreateFile({
            'title': f'{documento}_EVIDENCIA AUTOPOSTULACIÓN.pdf',
            'parents': [{'id': folder}]
        })
        drive_file.SetContentFile(temp)
        drive_file.Upload()

        link_pdf_drive = drive_file['alternateLink']
        hoja.update()
        
    except Exception as error:
        print("JCO sin autopostulación")
        if os.path.exists("informacion_personal_temporal.png"):
            os.remove("informacion_personal_temporal.png")

        continue


    

    






