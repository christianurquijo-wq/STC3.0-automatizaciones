"""
CONFIGURACIÓN — ajustar aquí antes de ejecutar.
Puerto a Python de Config.gs. Los mismos campos, mismos valores por defecto,
más 3 campos nuevos que en Apps Script no hacían falta (ROOT no tenía "hoja
activa": aquí hay que decir explícitamente en qué Sheet vive el reporte, y
dónde está la llave de la cuenta de servicio de Google).

IMPORTANTE: la API Key de Gemini y la llave de la cuenta de servicio NUNCA van
en este archivo ni se suben a GitHub — se leen de variables de entorno
(ver .env.example). Este archivo solo tiene IDs de Sheets/carpetas, que no son
secretos (para leerlos igual hace falta tener acceso compartido).
"""
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List


@dataclass
class Config:
    # ID de la carpeta raíz "15. Gestion Documental." (mismo valor que en Config.gs).
    ROOT_FOLDER_ID: str = '1Sl9wx_InpdiM-Wn0d5Cul_ljZTGorxDs'

    # NUEVO respecto a Config.gs: en Apps Script el reporte vivía en la Sheet
    # contenedora del script ("hoja activa"); en Python hay que decir
    # explícitamente en qué Sheet se escriben Resumen/Hallazgos/Consumo.
    # Sácalo de la URL de esa misma Sheet que ya usas hoy con el menú.
    REPORT_SPREADSHEET_ID: str = os.environ.get('REPORT_SPREADSHEET_ID', '')

    MAX_PARTICIPANTES_POR_CORRIDA: int = 80

    NOMBRE_HOJA_RESUMEN: str = 'Resumen por participante'
    NOMBRE_HOJA_HALLAZGOS: str = 'Hallazgos'
    NOMBRE_HOJA_CONSUMO: str = 'Consumo'

    # --- Cruce con el FCS (opcional) ---
    USAR_FCS: bool = True
    FCS_SPREADSHEET_ID: str = '15pgRouShB-tUNbdtGYs-ziYeuDeqV0tl21Hb9lkDXto'
    FCS_HOJA: str = 'CONSOLIDADO'

    # --- Lista de participantes a revisar ("Seguimiento General") ---
    USAR_LISTA_EN_RUTA: bool = True
    SEGUIMIENTO_SPREADSHEET_ID: str = '14BK3P6HigQOnNW6vAMc7RF5ioETKop4GUWxlZIPfmm0'
    SEGUIMIENTO_HOJA: str = 'SEGUIMIENTO GENERAL'
    HITO_FILTRO: str = 'En ruta'

    # --- Revisión de contenido con agente IA ---
    USAR_AGENTE_IA: bool = True

    VIGENCIA_DESDE: date = field(default_factory=lambda: date(2026, 7, 10))
    VIGENCIA_HASTA: date = field(default_factory=lambda: date(2026, 12, 31))

    # --- Agente IA (Gemini API / Google AI Studio, ahora vía SDK google-genai) ---
    MODELO_GEMINI: str = 'gemini-3.5-flash-lite'
    MAX_LLAMADAS_AGENTE_POR_CORRIDA: int = 15
    PAUSA_ENTRE_LLAMADAS_SEG: float = 4.5
    MAX_TOKENS_POR_CORRIDA: int = 200_000
    ALERTA_TOKENS_MES: int = 3_000_000

    # --- Supuestos para el estimador de consumo mensual ---
    ESTIMADOR_PARTICIPANTES_MES: int = 1500
    ESTIMADOR_DOCS_POR_PARTICIPANTE: int = 9
    CUPO_REFERENCIA_RPD_GRATUITO: int = 1500


# Los 10 campos que acepta la Plataforma Socios Talento Capital.
CAMPOS_PLATAFORMA: List[str] = [
    'documentoDeIdentidad',
    'declaracionJuramentada',
    'evidenciaDesempleoConsultaAdres',
    'certificadoDeResidencia',
    'consultaRnecOMigracion',
    'valoracionRiesgoDesempleo',
    'cursoHabilidadTecnica',
    'mitigacionBarreras',
    'autopostulacionJovenesConOportunidades',
    'seguimientoRemision',
]

# Diccionario de siglas → campo oficial de la plataforma (idéntico a Config.gs).
DICCIONARIO: Dict[str, dict] = {
    'CC':                   {'campo': 'documentoDeIdentidad'},
    'DJ':                   {'campo': 'declaracionJuramentada'},
    'ADRES':                {'campo': 'evidenciaDesempleoConsultaAdres', 'poblacion': 'GENERAL'},
    'ACJ':                  {'campo': 'evidenciaDesempleoConsultaAdres', 'poblacion': 'JCO'},
    'IR':                   {'campo': 'certificadoDeResidencia'},
    'RNEC':                 {'campo': 'consultaRnecOMigracion'},
    'VRD':                  {'campo': 'valoracionRiesgoDesempleo'},
    'CONSOLIDADOFORMACION': {'campo': 'cursoHabilidadTecnica'},
    'FORMACION':            {'campo': 'cursoHabilidadTecnica'},
    'MITIGACION':           {'campo': 'mitigacionBarreras'},
    'ENCUESTA':             {'campo': 'mitigacionBarreras'},
    'A':                    {'campo': 'autopostulacionJovenesConOportunidades'},
    'REMISION':              {'campo': 'seguimientoRemision'},
}

# Siglas que se ignoran a propósito.
IGNORAR: List[str] = ['HV', 'HVKUEPA', 'CLV']

# Tabla de responsables por categoría — arranca vacía, igual que en Config.gs.
AREA_SUGERIDA_POR_CATEGORIA: Dict[str, str] = {
    'Elegibilidad (causa raíz)': '',
    'Vigencia': '',
    'Coherencia con FCS': '',
    'Calidad de imagen': '',
    'Documento equivocado': '',
    'Documento faltante': '',
    'Formato no autorizado': '',
    'Contenido del curso': '',
    'Población / paquete': '',
    'No aplica': '',
    'Sin clasificar': '',
    'Otro': '',
}

CONFIG = Config()
