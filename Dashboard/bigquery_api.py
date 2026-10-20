# bigquery_api.py
import json
import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from google.cloud import bigquery

TABLA_GENERAL = "sustained-edge-465417-m3.EFE_2026.STC_3_0_V2_2026"

_client = None

def _get_client():
    global _client
    if _client is None:
        try:
            info = dict(st.secrets["gcp_service_account"])
        except Exception:
            with open(".streamlit/service_account.json") as f:
                info = json.load(f)
        creds = service_account.Credentials.from_service_account_info(info)
        _client = bigquery.Client(credentials=creds, project=info["project_id"])
    return _client


def cargar_general_bigquery() -> pd.DataFrame:
    """Carga la tabla General desde BigQuery, con nombres de columna ya traducidos al formato de Sheets."""
    client = _get_client()
    query = f"SELECT * FROM `{TABLA_GENERAL}`"
    df = client.query(query).to_dataframe()

    mapeo_columnas = {
        "fecha": "Fecha",
        "eventobase": "Evento/Base",
        "cc_prospecto": "CC Prospecto",
        "documento_de_identidad": "Documento de Identidad",
        "id_crm": "ID CRM",
        "nombre_completo": "Nombre completo",
        "correo": "Correo",
        "telefono": "Teléfono",
        "estado_crm": "Estado CRM",
        "verificacion_calidad": "Verificación Calidad",
        "id_sis": "ID SIS",
        "jco": "JCO",
        "reporte": "Reporte",
        "fecha_calidad_orientacion": "Fecha Calidad Orientación",
        "fecha_orientacion": "Fecha Orientación",
        "paquete": "Paquete",
        "remitido": "Remitido",
        "fecha_calidad": "Fecha calidad",
        "fecha_de_terminacion": "Fecha de terminación",
        "es_jco": "¿Es JCO?",
        "estado_de_la_formacion": "Estado de la formación",
        "fecha_clases": "Fecha clases",
        "fecha_finalizacion": "Fecha finalización",
        "bono_enviado": "Bono enviado",
        "momento_del_proceso": "Momento del proceso",
        "momento_del_proceso_back_up": "Momento del proceso (Back UP)",
        "resultado_del_vrd": "Resultado del VRD",
        "hito": "Hito",
        "sin_gestion": "Sin gestión",
        "en_verificacion": "En verificación",
        "verificado": "Verificado",
        "orientado": "Orientado",
        "formado": "Formado",
        "paquete_de_pantallazos": "Paquete de pantallazos",
        "fecha_de_alta": "Fecha de alta",
        "verificador": "Verificador",
        "orientador": "Orientador",
    }

    df = df.rename(columns=mapeo_columnas)
    return df

TABLA_METAS = "sustained-edge-465417-m3.EFE_2026.METAS_STC_3"

def cargar_metas_bigquery() -> pd.DataFrame:
    """Carga la tabla de Metas mensuales desde BigQuery."""
    client = _get_client()
    query = f"SELECT * FROM `{TABLA_METAS}`"
    df = client.query(query).to_dataframe()
    df = df.rename(columns={"Basico": "Básico"}) 
    return df