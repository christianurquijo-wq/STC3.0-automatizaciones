"""
Ejemplo de integración con Streamlit — reemplaza al menú "▶ Ejecutar revisión"
de la Sheet (Menu.gs). Esto NO es la app completa de Christian: es el
snippet mínimo a copiar/adaptar dentro de la app de Streamlit que ya tiene
en su Codespace (agregar el import + el botón donde tenga sentido en su UI).

Antes de correrlo:
  1. pip install -r requirements.txt
  2. Configurar las variables de entorno (ver .env.example) — cuenta de
     servicio + GEMINI_API_KEY + REPORT_SPREADSHEET_ID.
  3. streamlit run app_streamlit_ejemplo.py   (o copiar este bloque a tu app)
"""
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()  # carga .env si existe (no falla si no está instalado python-dotenv o no hay .env)
except ImportError:
    pass

from webhooks import validar_clave
from agente_config import CONFIG
from google_clients import obtener_credenciales, obtener_cliente_sheets, obtener_servicio_drive
import revision

st.set_page_config(page_title='STC 3.0 — Revisión documental', page_icon='📋')
st.title('📋 Revisión documental — Socios Talento Capital 3.0')

st.caption(
    f'Carpeta raíz configurada: `{CONFIG.ROOT_FOLDER_ID}` · '
    f'Filtro "En ruta": {"activado" if CONFIG.USAR_LISTA_EN_RUTA else "desactivado"} · '
    f'Agente IA: {"activado" if CONFIG.USAR_AGENTE_IA else "desactivado"} (modelo {CONFIG.MODELO_GEMINI})'
)

clave_revision = st.text_input('Contraseña de autorización', type='password', key='clave_ejecutar_revision')
if st.button('▶ Ejecutar revisión', type='primary'):
    if not validar_clave(clave_revision):
        st.error('Contraseña incorrecta.')
        st.stop()
    with st.spinner('Revisando documentos… esto puede tardar varios minutos si el agente IA está activado.'):
        try:
            credenciales = obtener_credenciales()
            drive_service = obtener_servicio_drive(credenciales)
            gc = obtener_cliente_sheets(credenciales)
            resultado = revision.ejecutar_revision(CONFIG, drive_service, gc)
        except Exception as e:
            st.error(f'La revisión falló: {e}')
        else:
            st.success(resultado['mensaje'])
            for titulo, mensaje in resultado['avisos']:
                st.warning(f'**{titulo}** — {mensaje}')

            st.metric('Participantes revisados', resultado['contador'])
            st.metric('Hallazgos encontrados', len(resultado['filas_hallazgos']))

            if resultado['filas_resumen']:
                with st.expander('Ver resumen de esta corrida'):
                    st.dataframe(resultado['filas_resumen'])

st.divider()
clave_diagnostico = st.text_input('Contraseña de autorización', type='password', key='clave_diagnostico_agente')
if st.button('🔧 Diagnóstico del agente IA (probar un solo archivo)'):
    if not validar_clave(clave_diagnostico):
        st.error('Contraseña incorrecta.')
        st.stop()
    from diagnostico import buscar_primer_pdf

    with st.spinner('Probando conexión con Drive, Sheets y el agente IA…'):
        conexion_ok = False
        primer_archivo = None
        try:
            credenciales = obtener_credenciales()
            drive_service = obtener_servicio_drive(credenciales)
            gc = obtener_cliente_sheets(credenciales)
            primer_archivo = buscar_primer_pdf(drive_service, CONFIG.ROOT_FOLDER_ID)
            conexion_ok = True
        except Exception as e:
            st.error(f'Falló la conexión con Drive/Sheets: {e}')

        if conexion_ok and not primer_archivo:
            st.warning('Se conectó bien, pero no se encontró ningún archivo dentro de la carpeta raíz para probar.')

        if primer_archivo:
            import agente
            from google_clients import descargar_bytes_archivo

            try:
                client = agente.obtener_cliente_gemini()
                archivo_bytes = descargar_bytes_archivo(drive_service, primer_archivo['id'])
                resultado = agente.probar_lectura_agente(client, CONFIG.MODELO_GEMINI, archivo_bytes)
            except Exception as e:
                st.error(f'Falló la llamada al agente IA: {e}')
            else:
                st.write(f'**Archivo de prueba:** {primer_archivo["name"]}')
                if resultado['error']:
                    st.error(resultado['error'])
                else:
                    st.success(f"OK ({resultado['tokens_usados']} token(s) usados)")
                    st.json(resultado['datos'])

st.divider()
clave_consumo = st.text_input('Contraseña de autorización', type='password', key='clave_estimar_consumo')
if st.button('📊 Estimar consumo mensual'):
    if not validar_clave(clave_consumo):
        st.error('Contraseña incorrecta.')
        st.stop()
    from consumo import estimar_consumo_mensual
    from google_clients import obtener_cliente_sheets, obtener_credenciales, obtener_o_crear_hoja

    gc = obtener_cliente_sheets(obtener_credenciales())
    report_ss = gc.open_by_key(CONFIG.REPORT_SPREADSHEET_ID)
    sh_consumo = obtener_o_crear_hoja(report_ss, CONFIG.NOMBRE_HOJA_CONSUMO)
    st.code(estimar_consumo_mensual(sh_consumo, CONFIG), language=None)
