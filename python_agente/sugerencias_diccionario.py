"""
Nivel 4 del plan de mantenimiento del diccionario: barrido completo de Drive
para detectar nombres de archivo que el sistema todavía no reconoce, y una
única llamada a Gemini que propone a qué campo oficial corresponde cada uno.

Importante: esto NO clasifica documentos por su contenido (no descarga ni lee
ningún PDF) — solo mira nombres de archivo, igual que el diccionario. Por eso
es barato: una sola llamada de texto por corrida de este proceso, sin
importar cuántos miles de archivos tenga Drive. Y nunca escribe nada solo —
la propuesta se revisa y aprueba a mano en Streamlit (pestana_auditoria.py)
antes de guardarse en el Diccionario (ver diccionario.py).
"""
import json
import re
from typing import Dict, List, Optional

from agente_config import CAMPOS_PLATAFORMA
from diccionario import normalizar_alias
from google_clients import listar_archivos, listar_subcarpetas

DESCRIPCIONES_CAMPO = {
    'documentoDeIdentidad': 'Cédula de ciudadanía u otro documento de identidad del participante.',
    'declaracionJuramentada': 'Declaración juramentada de desempleo.',
    'evidenciaDesempleoConsultaAdres': (
        'Evidencia de desempleo: consulta ADRES (población general) o evidencia equivalente '
        'para Jóvenes con Oportunidades (JCO).'
    ),
    'certificadoDeResidencia': 'Certificado o recibo que demuestra el lugar de residencia.',
    'consultaRnecOMigracion': (
        'Consulta RNEC (Registraduría) para colombianos, o documento migratorio (PPT, Permiso '
        'de Ingreso y Permanencia, cédula de extranjería) para población migrante.'
    ),
    'valoracionRiesgoDesempleo': 'Valoración de Riesgo de Desempleo (VRD).',
    'cursoHabilidadTecnica': 'Evidencia o certificado del curso de habilidad técnica / formación.',
    'mitigacionBarreras': 'Encuesta o evidencia de mitigación de barreras de acceso.',
    'autopostulacionJovenesConOportunidades': (
        'Autopostulación al programa — aplica solo a población JCO (Jóvenes con Oportunidades).'
    ),
    'seguimientoRemision': 'Remisión o seguimiento del proceso del participante.',
}

CAMPO_NO_RECONOCIDO = 'NO_RECONOCIDO'
CAMPO_IGNORAR = 'IGNORAR'


def _extraer_nombre_documento(nombre_archivo: str, numero_documento: str) -> str:
    """
    Extrae la parte "humana" del nombre del archivo (quita el número de
    documento del inicio y la extensión), preservando mayúsculas/tildes/
    símbolos tal cual — a diferencia de utilidades.normalizar_nombre(), que
    limpia agresivamente para comparar contra el diccionario. El objetivo acá
    es que una persona (o Gemini) lo pueda leer y reconocer, igual que en el
    glosario que se arma a mano.
    """
    n = re.sub(r'\.pdf$', '', nombre_archivo, flags=re.IGNORECASE)
    n = re.sub(r'^\s*' + re.escape(numero_documento) + r'[\s_-]*', '', n)
    return n.strip() or nombre_archivo


def escanear_glosario_drive(drive_service, carpeta_raiz_id: str) -> List[dict]:
    """
    Barrido COMPLETO de toda la carpeta raíz (mes -> participante -> archivo),
    sin filtrar por "En ruta" — a diferencia de ejecutar_revision(), que es
    una revisión de negocio de un subconjunto de participantes, esto es un
    inventario de todo lo que hay en Drive, para mantener el diccionario.

    Devuelve una lista [{nombre, ruta_primera_aparicion, cantidad}], la misma
    forma que el glosario armado a mano (glosario_documentos.csv), ordenada
    alfabéticamente.
    """
    conteo: Dict[str, dict] = {}

    for carpeta_mes in listar_subcarpetas(drive_service, carpeta_raiz_id):
        for carpeta_participante in listar_subcarpetas(drive_service, carpeta_mes['id']):
            numero_documento = carpeta_participante['name'].strip()
            for archivo in listar_archivos(drive_service, carpeta_participante['id']):
                nombre_doc = _extraer_nombre_documento(archivo['name'], numero_documento)
                if nombre_doc not in conteo:
                    ruta = f"{carpeta_mes['name']}/{numero_documento}/{archivo['name']}"
                    conteo[nombre_doc] = {'nombre': nombre_doc, 'ruta_primera_aparicion': ruta, 'cantidad': 0}
                conteo[nombre_doc]['cantidad'] += 1

    return sorted(conteo.values(), key=lambda x: x['nombre'])


def filtrar_nombres_nuevos(glosario: List[dict], diccionario_actual: Dict[str, dict], ignorar_actual: set) -> List[dict]:
    """Descarta del glosario lo que YA se reconoce hoy (tras normalizar) — solo lo nuevo debe llegar a la IA."""
    nuevos = []
    for item in glosario:
        norm = normalizar_alias(item['nombre'])
        if not norm or norm in diccionario_actual or norm in ignorar_actual:
            continue
        nuevos.append(item)
    return nuevos


def _construir_prompt(nombres_nuevos: List[dict], diccionario_actual: Dict[str, dict]) -> str:
    campos_texto = '\n'.join(f'  - {campo}: {desc}' for campo, desc in DESCRIPCIONES_CAMPO.items())

    ejemplos = '\n'.join(
        f'  - "{alias}" -> campo="{entrada["campo"]}"' + (f', población="{entrada["poblacion"]}"' if entrada.get('poblacion') else '')
        for alias, entrada in list(diccionario_actual.items())[:20]
    )

    nombres_texto = '\n'.join(f'  - "{n["nombre"]}" (visto {n["cantidad"]} veces en Drive)' for n in nombres_nuevos)

    return (
        'Estos son los 10 campos oficiales de la Plataforma Socios Talento Capital 3.0 '
        '(programa de empleabilidad, Alcaldía de Bogotá / SDDE), con su significado:\n'
        f'{campos_texto}\n\n'
        'Ejemplos ya confirmados de siglas/alias de nombre de archivo que el sistema YA '
        'reconoce hoy (para que entiendas el estilo de nombres que usa el equipo):\n'
        f'{ejemplos}\n\n'
        'Estos son nombres de archivo REALES encontrados en Google Drive que el sistema '
        'todavía NO reconoce (después de quitarles el número de cédula, la extensión, tildes '
        'y símbolos) — son variantes de escritura, errores de tipeo, o documentos '
        'genuinamente nuevos:\n'
        f'{nombres_texto}\n\n'
        f'Para cada nombre, propone a cuál de los 10 campos oficiales corresponde, o '
        f'"{CAMPO_IGNORAR}" si es una sigla que a propósito no debe clasificarse (como HV, hoja '
        f'de vida, que ya se ignora hoy), o "{CAMPO_NO_RECONOCIDO}" si genuinamente no tienes '
        'información suficiente para decidir con el nombre solo. Si el campo sugerido es '
        '"evidenciaDesempleoConsultaAdres", indica también la población si el nombre lo deja '
        'claro (GENERAL o JCO); si no, deja población vacía. No inventes: ante la duda, usa '
        f'confianza "BAJA" o responde "{CAMPO_NO_RECONOCIDO}" en vez de adivinar.'
    )


def _construir_esquema() -> dict:
    return {
        'type': 'object',
        'properties': {
            'sugerencias': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'alias': {'type': 'string', 'description': 'El nombre de archivo exactamente como se dio, sin modificar.'},
                        'campo_sugerido': {
                            'type': 'string',
                            'enum': CAMPOS_PLATAFORMA + [CAMPO_IGNORAR, CAMPO_NO_RECONOCIDO],
                        },
                        'poblacion_sugerida': {'type': 'string', 'enum': ['', 'GENERAL', 'JCO']},
                        'confianza': {'type': 'string', 'enum': ['ALTA', 'MEDIA', 'BAJA']},
                        'justificacion': {'type': 'string', 'description': 'Explicación breve, una frase.'},
                    },
                    'required': ['alias', 'campo_sugerido', 'poblacion_sugerida', 'confianza', 'justificacion'],
                },
            },
        },
        'required': ['sugerencias'],
    }


def sugerir_mapeo_ia(client, nombres_nuevos: List[dict], diccionario_actual: Dict[str, dict], config) -> dict:
    """
    Una sola llamada de texto a Gemini (sin PDFs) que propone un mapeo para
    los nombres nuevos. Devuelve {sugerencias, tokens_usados, error} — nunca
    se aplica sola, la pantalla de Streamlit la muestra para revisar/editar/
    aprobar antes de escribirla en el Diccionario.
    """
    from google.genai import types  # import perezoso, mismo motivo que en agente.py

    if not nombres_nuevos:
        return {'sugerencias': [], 'tokens_usados': 0, 'error': None}

    prompt = _construir_prompt(nombres_nuevos, diccionario_actual)
    schema = _construir_esquema()

    try:
        respuesta = client.models.generate_content(
            model=config.MODELO_GEMINI,
            contents=[prompt],
            config=types.GenerateContentConfig(
                system_instruction=(
                    'Eres un asistente que ayuda a clasificar nombres de archivo de documentos de '
                    'un programa de empleabilidad, comparándolos contra un diccionario de siglas ya '
                    'conocido. No inventes campos que no estén en la lista dada.'
                ),
                temperature=0,
                response_mime_type='application/json',
                response_json_schema=schema,
            ),
        )
    except Exception as e:
        return {'sugerencias': [], 'tokens_usados': 0, 'error': f'Gemini: {e}'}

    tokens_usados = 0
    if getattr(respuesta, 'usage_metadata', None) is not None:
        tokens_usados = getattr(respuesta.usage_metadata, 'total_token_count', 0) or 0

    texto = getattr(respuesta, 'text', None)
    if not texto:
        return {'sugerencias': [], 'tokens_usados': tokens_usados, 'error': 'Gemini: respuesta sin contenido'}

    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        return {'sugerencias': [], 'tokens_usados': tokens_usados, 'error': f'Gemini: la respuesta no fue JSON válido — {e}'}

    return {'sugerencias': datos.get('sugerencias', []), 'tokens_usados': tokens_usados, 'error': None}
