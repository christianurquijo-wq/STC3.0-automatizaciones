import os
import sys
import time
import re
import gspread
from dotenv import load_dotenv
from PIL import Image
from pydrive2.auth import GoogleAuth   # pydrive (sin 2) ya no se mantiene; mismo API
from pydrive2.drive import GoogleDrive
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# ================= CONFIGURACIÓN Y RUTAS =================
# Obtener la carpeta donde está guardado este script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
EN_SERVIDOR = bool(os.getenv("CI"))  # GitHub Actions define CI=true

# Rutas de archivos de credenciales de Google (bóveda del repo; en Actions llegan por SECRETS_BUNDLE)
BOVEDA = os.path.join(BASE_DIR, "CONFIG_SEGURIDAD")
CLIENT_SECRETS_PATH = os.path.join(BOVEDA, "client_secrets.json")
CREDENTIALS_PATH = os.path.join(BOVEDA, "credentials_module.json")

# URLs y Parametros de la prueba
SHEET_URL = "https://docs.google.com/spreadsheets/d/1J0u5EiA-82N1LTKT-Qt8qdJYI_sbc_hhjH33AWxCvZo/edit?gid=0#gid=0"
SIS_URL = "https://sis.kuepa.com/students"
DRIVE_FOLDER_ID = "1Ai3toqr5bk5y6QXlXgsXID6yoISHbFCu"
# Usuario y clave del SIS: SOLO en el .env (SIS_USUARIO / SIS_CLAVE), nunca en el código.
USER = os.getenv("SIS_USUARIO", "")
PASSWORD = os.getenv("SIS_CLAVE", "")
if not USER or not PASSWORD:
    sys.exit("Faltan SIS_USUARIO y/o SIS_CLAVE en el .env de STC.")
ALIANZA = "Socios Talento Capital SDDE 3.0"
# CHROMEDRIVER_PATH = "C:/ruta/a/chromedriver.exe"  # <- Ajusta tu ruta local a chromedriver.exe
TEMP_FOLDER = os.path.join(BASE_DIR, "pantallazos_temp")

# Crear carpeta temporal si no existe
os.makedirs(TEMP_FOLDER, exist_ok=True)
# =========================================================

print("🔑 Autenticando en Google Drive y Google Sheets...")

# 1. Autenticación Google Drive (PyDrive) con persistencia de sesión
gauth = GoogleAuth()
gauth.LoadClientConfigFile(CLIENT_SECRETS_PATH)
gauth.LoadCredentialsFile(CREDENTIALS_PATH)

if gauth.credentials is None:
    if EN_SERVIDOR:
        sys.exit("Falta CONFIG_SEGURIDAD/credentials_module.json (token de Drive) en el SECRETS_BUNDLE.")
    gauth.LocalWebserverAuth()  # Abre el navegador la primera vez (solo en tu PC)
elif gauth.access_token_expired:
    gauth.Refresh()
else:
    gauth.Authorize()

gauth.SaveCredentialsFile(CREDENTIALS_PATH)
drive = GoogleDrive(gauth)

# 2. Autenticación Google Sheets (gspread)
gc = gspread.authorize(gauth.credentials)
sheet = gc.open_by_url(SHEET_URL).sheet1

print("📋 Leyendo datos de la hoja de cálculo...")
rows = sheet.get_all_values()
participantes = []

for row in rows[1:]:  # Omitir fila de encabezados
    if len(row) >= 15:
        estado = row[14].strip().upper()  # Columna O
        cedula = row[6].strip()           # Columna G
        nombre = row[0].strip()           # Columna A
        
        # Evalúa si la celda contiene "FINALIZADO"
        if "FINALIZADO" in estado and cedula:
            nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", nombre)
            participantes.append({"cedula": cedula, "nombre": nombre_limpio})

print(f"🎯 Participantes a procesar: {len(participantes)}")

# 3. Configurar Chrome Driver
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-notifications")
if EN_SERVIDOR or os.getenv("HEADLESS"):
    # Sin pantalla (GitHub Actions): ventana fija para que los pantallazos salgan completos
    for arg in ("--headless=new", "--window-size=1920,1080", "--no-sandbox", "--disable-dev-shm-usage"):
        options.add_argument(arg)
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 30)

subidos, fallidos = 0, []
try:
    print("🌐 Iniciando sesión en SIS Kuepa...")
    driver.get(SIS_URL)

    # 1. Seleccionar/Escribir la Alianza
    # Intenta buscar por ID 'alianza' o por el placeholder/label
    try:
        alianza_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Alianza') or @name='alliance' or @id='alliance']")))
        alianza_input.clear()
        alianza_input.send_keys("Socios Talento Capital SDDE 3.0")
    except Exception:
        # Si la Alianza es un desplegable/select o se encuentra por etiqueta:
        try:
            alianza_input = driver.find_element(By.XPATH, "//label[contains(text(), 'Alianza')]/following-sibling::input")
            alianza_input.clear()
            alianza_input.send_keys("Socios Talento Capital SDDE 3.0")
        except Exception as e_alianza:
            print(f"⚠️ Nota sobre Alianza: {e_alianza}")

    # 2. Escribir usuario (Correo)
    email_input = wait.until(EC.presence_of_element_located((By.NAME, "email")))
    email_input.clear()
    email_input.send_keys(USER)

    # 3. Escribir contraseña
    pass_input = driver.find_element(By.NAME, "password")
    pass_input.clear()
    pass_input.send_keys(PASSWORD)

    # 4. Clic en "Ingresar"
    driver.find_element(By.XPATH, "//button[contains(text(), 'Ingresar') or @type='submit']").click()
    time.sleep(3)

    # Pestaña base para no perder la sesión
    main_window = driver.current_window_handle

    # 4. Procesar cada participante
    for i, part in enumerate(participantes, 1):
        print(f"\n[{i}/{len(participantes)}] Procesando: {part['nombre']} ({part['cedula']})")
        
        try:
            # Asegurarse de volver a la ventana principal del SIS
            driver.switch_to.window(main_window)
            driver.get(SIS_URL)
            
            # Buscar cédula
            search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Buscar por documento']")))
            search_box.clear()
            search_box.send_keys(part['cedula'])
            time.sleep(2)
            
            # Clic en "Ir al LMS"
            lms_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Ir al LMS')]")))
            lms_button.click()
            time.sleep(3)
            
            # Cambiar a la pestaña del LMS
            driver.switch_to.window(driver.window_handles[-1])
            
            # Clic en el botón o enlace "SIS" dentro del LMS
            sis_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'SIS')]")))
            sis_link.click()
            time.sleep(3)
            
            # Cambiar a la pestaña nueva generada
            driver.switch_to.window(driver.window_handles[-1])
            
            # Entrar a "Notas y asistencia"
            notas_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Notas y asistencia')]")))
            notas_link.click()
            time.sleep(3)
            
            # Aplicar filtro utilizando la clase Select de Selenium
            try:
                dropdown = Select(wait.until(EC.presence_of_element_located((By.XPATH, "//select[@id='filtro-notas']"))))
                try:
                    dropdown.select_by_index(0)
                except Exception:
                    dropdown.select_by_index(1)
            except Exception as e_filtro:
                print(f"   ⚠️ No se pudo seleccionar la opción del filtro: {e_filtro}")
            
            time.sleep(3)
            
            # Definir rutas temporales para imágenes y PDFs
            screenshot_path = os.path.join(TEMP_FOLDER, f"{part['cedula']}_{part['nombre']}.png")
            pdf_path = os.path.join(TEMP_FOLDER, f"{part['cedula']}_{part['nombre']}.pdf")
            
            # Tomar captura de pantalla
            driver.save_screenshot(screenshot_path)
            
            # Convertir la imagen a PDF con Pillow
            img = Image.open(screenshot_path)
            if img.mode == "RGBA":
                img = img.convert("RGB")
            img.save(pdf_path, "PDF", resolution=100.0)
            
            # Subir a Google Drive
            file_drive = drive.CreateFile({
                'title': f"Nota_{part['nombre']}_{part['cedula']}.pdf",
                'parents': [{'id': DRIVE_FOLDER_ID}]
            })
            file_drive.SetContentFile(pdf_path)
            file_drive.Upload()
            
            # Eliminar archivos locales creados
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            
            print(f"   ✓ Subido a Drive correctamente.")
            subidos += 1
            
        except Exception as e:
            print(f"   ✗ Error en el proceso de {part['nombre']}: {str(e)}")
            fallidos.append(part['cedula'])
            
        finally:
            # Cerrar las pestañas secundarias generadas y mantener la sesión
            for handle in driver.window_handles:
                if handle != main_window:
                    driver.switch_to.window(handle)
                    driver.close()
            driver.switch_to.window(main_window)

finally:
    driver.quit()

print(f"\nResumen: {subidos} subidos, {len(fallidos)} con error.")
if fallidos:
    print("Cédulas con error: " + ", ".join(fallidos))
if participantes and subidos == 0:
    # Nada salió: casi siempre es login del SIS o cambio en la página. Se marca como fallo en el panel.
    sys.exit("Ningún participante se pudo procesar. Revisa SIS_USUARIO/SIS_CLAVE o si cambió la página del SIS.")
print("✅ Proceso finalizado. Revisa tu carpeta en Google Drive.")
