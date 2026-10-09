"""
Puerto a Python de Menu.gs → diagnosticoAgente_() / buscarPrimerPdf_(). Prueba
la conexión con Drive, con las 3 Sheets externas + la del reporte, y con el
agente IA sobre UN solo archivo real — para aislar rápido si el problema es
la API Key, la cuenta de servicio, un permiso que falta en alguna Sheet, o
cuota del agente, sin gastar presupuesto de una corrida completa.

Uso:
    cd python_agente
    python3 diagnostico.py
"""
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import agente
from agente_config import CONFIG
from google_clients import (
    descargar_bytes_archivo, listar_archivos, listar_subcarpetas,
    obtener_credenciales, obtener_cliente_sheets, obtener_servicio_drive,
)


def buscar_primer_pdf(drive_service, carpeta_raiz_id):
    """Recorre mes -> participante y devuelve el primer archivo {id, name} que encuentre."""
    for carpeta_mes in listar_subcarpetas(drive_service, carpeta_raiz_id):
        for carpeta_participante in listar_subcarpetas(drive_service, carpeta_mes['id']):
            archivos = listar_archivos(drive_service, carpeta_participante['id'])
            if archivos:
                return archivos[0]
    return None


def main():
    print('=== Diagnóstico STC 3.0 (Python) ===\n')

    print('1) Cuenta de servicio…', end=' ')
    try:
        credenciales = obtener_credenciales()
        drive_service = obtener_servicio_drive(credenciales)
        gc = obtener_cliente_sheets(credenciales)
        print('OK')
    except Exception as e:
        print(f'FALLÓ\n   {e}')
        sys.exit(1)

    print('2) Acceso a la carpeta raíz de Drive…', end=' ')
    try:
        primer_archivo = buscar_primer_pdf(drive_service, CONFIG.ROOT_FOLDER_ID)
    except Exception as e:
        print(f'FALLÓ\n   {e}\n   (revisa que Kuepa haya compartido la carpeta raíz con el email de la cuenta de servicio)')
        sys.exit(1)
    if not primer_archivo:
        print('OK, pero no se encontró ningún archivo dentro para probar el agente.')
    else:
        print(f'OK (encontró: "{primer_archivo["name"]}")')

    print('3) Acceso a las Sheets…')
    for etiqueta, sid in [
        ('FCS', CONFIG.FCS_SPREADSHEET_ID),
        ('Seguimiento General', CONFIG.SEGUIMIENTO_SPREADSHEET_ID),
        ('Reporte (REPORT_SPREADSHEET_ID)', CONFIG.REPORT_SPREADSHEET_ID),
    ]:
        print(f'   - {etiqueta}…', end=' ')
        if not sid:
            print('SIN CONFIGURAR (revisa agente_config.py / la variable de entorno REPORT_SPREADSHEET_ID)')
            continue
        try:
            gc.open_by_key(sid)
            print('OK')
        except Exception as e:
            print(f'FALLÓ\n     {e}\n     (revisa que Kuepa haya compartido esta Sheet con el email de la cuenta de servicio)')

    if primer_archivo:
        print('\n4) Llamada de prueba al agente IA (Gemini)…')
        try:
            client = agente.obtener_cliente_gemini()
        except Exception as e:
            print(f'   FALLÓ\n   {e}')
            sys.exit(1)

        archivo_bytes = descargar_bytes_archivo(drive_service, primer_archivo['id'])
        resultado = agente.probar_lectura_agente(client, CONFIG.MODELO_GEMINI, archivo_bytes)

        print(f'   Archivo de prueba: "{primer_archivo["name"]}"')
        print(f'   Modelo: {CONFIG.MODELO_GEMINI}\n')

        if resultado['error']:
            print(f"   Falló: {resultado['error']}")
            print('   (Si menciona la API Key o "API_KEY_INVALID", revisa GEMINI_API_KEY en tu .env.')
            print('    Si menciona cuota/quota, espera un minuto y vuelve a intentar.)')
        else:
            datos = resultado['datos']
            print(f"   OK ({resultado['tokens_usados']} token(s) usados).")
            print(f"   Tipo de documento que detectó: {datos.get('tipoDeDocumentoQueVes') or '(vacío)'}")
            print(f"   Primer texto legible: {datos.get('primeraLineaOEncabezado') or '(vacío)'}")

    print('\n=== Fin del diagnóstico ===')


if __name__ == '__main__':
    main()
