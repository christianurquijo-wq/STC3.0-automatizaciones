"""
Puerto a Python de Agente.gs — llamadas al agente IA (Gemini) usando el SDK
oficial `google-genai` en vez de UrlFetchApp + REST a mano. Misma idea:
el agente lee el PDF directamente y solo puede elegir códigos del catálogo
oficial (ver catalogo.py), nunca inventar texto libre — se lo forzamos con
salida estructurada (response_json_schema) restringida a un enum de códigos
válidos para ese campo.

Autenticación: API Key de Gemini, leída de la variable de entorno
GEMINI_API_KEY (consíguela gratis, sin tarjeta, en https://aistudio.google.com/apikey).

Nivel gratuito: sin tarjeta de crédito, pero con límite de solicitudes por
minuto y por día — por eso cada llamada respeta config.PAUSA_ENTRE_LLAMADAS_SEG
y cada corrida respeta config.MAX_LLAMADAS_AGENTE_POR_CORRIDA. Y, a diferencia
del nivel pagado, los datos enviados en el nivel gratuito pueden ser usados
por Google para mejorar sus productos — misma decisión tomada con Christian
el 2026-08-24 para la versión de Apps Script: se acepta este riesgo para el
piloto de bajo volumen; revisar antes de escalar a producción con todos los
participantes (son documentos con datos personales de un programa público
de la Alcaldía).
"""
import json
import os
import time
from typing import List, Optional

import fichas_documentos
from catalogo import codigos_validos_para_campo


def obtener_cliente_gemini():
    """Crea el cliente de Gemini leyendo la API Key de la variable de entorno GEMINI_API_KEY."""
    from google import genai  # import perezoso: así los tests pueden correr sin el paquete instalado

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError(
            'No hay una API Key de Gemini configurada. Define la variable de entorno '
            'GEMINI_API_KEY (la consigues gratis, sin tarjeta, en https://aistudio.google.com/apikey).'
        )
    return genai.Client(api_key=api_key)


def construir_prompt_sistema() -> str:
    """Instrucciones fijas del agente — el "rol". No cambia entre documentos."""
    return (
        'Eres un verificador documental para el programa "Socios Talento Capital 3.0" '
        '(Kuepa Edutech SAS, Alcaldía de Bogotá / SDDE). Tu tarea es revisar UN documento '
        'PDF a la vez y decidir si tiene algún problema, usando EXCLUSIVAMENTE los códigos '
        'de observación que se te dan en cada solicitud — nunca inventes un código ni un '
        'texto de observación distinto a los que se te ofrecen.\n\n'
        'Reglas importantes:\n'
        '- Si el documento está en regla, no reportes ningún hallazgo (deja la lista vacía). '
        'No es necesario encontrar un problema en cada documento — la mayoría deberían estar bien.\n'
        '- Si no tienes información suficiente para verificar algo con certeza (por ejemplo, no '
        'conoces un dato externo con el que comparar), NO marques ese código. Es preferible dejar '
        'algo sin observar que reportar un hallazgo sin evidencia clara en el propio documento.\n'
        '- "documentoLegible" en false significa que el archivo está ilegible, cortado, corrupto, o '
        'en blanco — en ese caso normalmente corresponde también el código de "documento ilegible" '
        'si está disponible en la lista de códigos que se te da.\n'
        '- El campo "detalle" de cada hallazgo debe ser una frase corta y específica (qué viste, qué '
        'fecha encontraste, qué nombre no coincide, etc.), no una repetición del texto del código.\n'
        '- Estos son documentos de personas reales en un programa de empleabilidad — sé preciso y '
        'evita falsos positivos; ante la duda razonable, no reportes.'
    )


def construir_prompt_documento(
    campo: str, numero_documento: str, datos_fcs: Optional[dict], nombre_archivo: str, config,
    poblacion: Optional[str] = None,
) -> str:
    """
    Prompt específico de un documento: lo único que cambia entre llamadas.
    Desde 2026-08-26 incluye la ficha de verificación de fichas_documentos.py
    (qué ES el documento y qué se debe cruzar puntualmente) en vez de dejar
    que el agente infiera todo del nombre del campo — antes el mismo párrafo
    genérico se usaba para los 10 tipos de documento por igual.
    """
    ficha = fichas_documentos.obtener_ficha(campo, poblacion)

    contexto = (
        f'Campo de la plataforma al que corresponde este documento: "{campo}".\n'
        f'Nombre del archivo tal como está en Drive: "{nombre_archivo}".\n'
        'Número de documento de identidad del participante (debe coincidir con lo que '
        f'diga el PDF, cuando el documento incluya ese dato): {numero_documento}.\n'
        'Rango de vigencia del convenio (para observaciones de tipo "vigencia"): desde '
        f'{config.VIGENCIA_DESDE.strftime("%d/%m/%Y")} hasta {config.VIGENCIA_HASTA.strftime("%d/%m/%Y")}.\n'
    )

    if ficha.get('descripcion'):
        contexto += f'\nQué es este documento: {ficha["descripcion"]}\n'
    if ficha.get('que_revisar'):
        contexto += f'Qué debes revisar puntualmente en este documento: {ficha["que_revisar"]}\n'

    if datos_fcs:
        jco = datos_fcs.get('jco')
        poblacion_texto = 'Jóvenes con Oportunidades (JCO)' if jco == 'SI' else ('general' if jco == 'NO' else 'no informada')
        nombre_completo = (datos_fcs.get('nombre_completo') or '').strip()
        contexto += (
            '\nDatos adicionales confirmados en el FCS (Consolidado) para este participante: '
            f'paquete de servicio = "{datos_fcs.get("paquete") or "no informado"}", '
            f'población = "{poblacion_texto}"'
        )
        if nombre_completo:
            contexto += f', nombre completo = "{nombre_completo}"'
            contexto += (
                '.\nCuando la ficha de arriba pida cruzar el nombre del participante, compáralo '
                f'contra este nombre completo del FCS ("{nombre_completo}") — pequeñas diferencias '
                'de tildes, orden de apellidos, o mayúsculas/minúsculas NO son un hallazgo; repórtalo '
                'solo si el nombre en el documento es claramente distinto.\n'
            )
        else:
            contexto += '.\nNo hay nombre completo disponible en el FCS para este participante — no marques hallazgos de nombre por esa razón.\n'
    else:
        contexto += (
            '\nNo hay datos del FCS disponibles para cruzar en esta corrida — no marques '
            'observaciones de "Coherencia con FCS" que dependan de un dato que no tienes.\n'
        )

    contexto += '\nRevisa el PDF adjunto y decide qué códigos de la lista permitida aplican (puede ser ninguno).'
    return contexto


def construir_esquema_respuesta(codigos_validos: List[dict]) -> dict:
    """JSON Schema restringido a los códigos válidos para el campo — se pasa como response_json_schema."""
    return {
        'type': 'object',
        'properties': {
            'documentoLegible': {
                'type': 'boolean',
                'description': 'false si el archivo está ilegible, corrupto, en blanco, o no se puede evaluar su contenido.',
            },
            'hallazgos': {
                'type': 'array',
                'description': 'Lista de observaciones que aplican. Vacía si el documento está en regla.',
                'items': {
                    'type': 'object',
                    'properties': {
                        'codigo': {
                            'type': 'string',
                            'enum': [c['codigo'] for c in codigos_validos],
                            'description': 'Debe ser exactamente uno de los códigos permitidos que se te dieron.',
                        },
                        'detalle': {
                            'type': 'string',
                            'description': 'Explicación corta y específica de por qué aplica este código en este documento.',
                        },
                    },
                    'required': ['codigo', 'detalle'],
                },
            },
        },
        'required': ['documentoLegible', 'hallazgos'],
    }


def llamar_agente(client, modelo: str, archivo_bytes: bytes, prompt_sistema: str, prompt_documento: str, schema: dict) -> dict:
    """
    Llamada de bajo nivel a Gemini — no conoce el catálogo ni el presupuesto de
    la corrida, eso lo maneja evaluar_documento_con_agente. Devuelve
    {datos, tokens_usados, error}.
    """
    from google.genai import types  # import perezoso, mismo motivo que en obtener_cliente_gemini

    try:
        respuesta = client.models.generate_content(
            model=modelo,
            contents=[
                types.Part.from_bytes(data=archivo_bytes, mime_type='application/pdf'),
                prompt_documento,
            ],
            config=types.GenerateContentConfig(
                system_instruction=prompt_sistema,
                temperature=0,
                response_mime_type='application/json',
                response_json_schema=schema,
            ),
        )
    except Exception as e:
        return {'datos': None, 'tokens_usados': 0, 'error': f'Gemini: {e}'}

    tokens_usados = 0
    if getattr(respuesta, 'usage_metadata', None) is not None:
        tokens_usados = getattr(respuesta.usage_metadata, 'total_token_count', 0) or 0

    texto = getattr(respuesta, 'text', None)
    if not texto:
        candidatos = getattr(respuesta, 'candidates', None) or []
        razon = f' (finish_reason: {candidatos[0].finish_reason})' if candidatos and getattr(candidatos[0], 'finish_reason', None) else ''
        return {'datos': None, 'tokens_usados': tokens_usados, 'error': f'Gemini: respuesta sin contenido{razon}'}

    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        return {'datos': None, 'tokens_usados': tokens_usados, 'error': f'Gemini: la respuesta no fue JSON válido — {e}'}

    return {'datos': datos, 'tokens_usados': tokens_usados, 'error': None}


def evaluar_documento_con_agente(
    client,
    archivo_bytes: bytes,
    nombre_archivo: str,
    campo: str,
    numero_documento: str,
    datos_fcs: Optional[dict],
    presupuesto_agente: dict,
    config,
    sleep_fn=time.sleep,
    poblacion: Optional[str] = None,
) -> dict:
    """
    Evalúa un documento clasificado (bytes + campo) con el agente IA. Respeta
    el presupuesto de llamadas/tokens de la corrida y la pausa entre llamadas
    (rate limit del nivel gratuito). Devuelve hallazgos en formato "crudo"
    ({codigo, detalle}) — quien llama (revision.py) los resuelve contra el
    catálogo con obtener_observacion() para armar la fila completa.

    presupuesto_agente es un dict mutable compartido por toda la corrida:
    {restantes, restantes_inicial, saltados, tokens_usados, detenido_por_tokens}.

    poblacion ('GENERAL' | 'JCO' | 'NO DETERMINADA' | None) se usa para elegir
    la variante correcta de la ficha de verificación (ver fichas_documentos.py).
    """
    sin_llamadas = presupuesto_agente['restantes'] <= 0
    sin_tokens = presupuesto_agente['tokens_usados'] >= config.MAX_TOKENS_POR_CORRIDA
    if sin_llamadas or sin_tokens:
        presupuesto_agente['saltados'] += 1
        if sin_tokens and not sin_llamadas:
            presupuesto_agente['detenido_por_tokens'] = True
        return {'hallazgos_crudos': [], 'documento_legible': None, 'tokens_usados': 0, 'error': None, 'saltado': True}

    presupuesto_agente['restantes'] -= 1

    codigos_validos = codigos_validos_para_campo(campo)
    schema = construir_esquema_respuesta(codigos_validos)
    prompt_sistema = construir_prompt_sistema()
    prompt_documento = construir_prompt_documento(campo, numero_documento, datos_fcs, nombre_archivo, config, poblacion)

    resultado = llamar_agente(client, config.MODELO_GEMINI, archivo_bytes, prompt_sistema, prompt_documento, schema)

    presupuesto_agente['tokens_usados'] += resultado.get('tokens_usados') or 0
    sleep_fn(config.PAUSA_ENTRE_LLAMADAS_SEG)  # respeta el límite de solicitudes por minuto

    if resultado['error'] or not resultado['datos']:
        return {
            'hallazgos_crudos': [], 'documento_legible': None,
            'tokens_usados': resultado['tokens_usados'], 'error': resultado['error'] or 'Sin datos', 'saltado': False,
        }

    hallazgos = resultado['datos'].get('hallazgos') if isinstance(resultado['datos'].get('hallazgos'), list) else []
    return {
        'hallazgos_crudos': hallazgos,
        'documento_legible': resultado['datos'].get('documentoLegible') is not False,
        'tokens_usados': resultado['tokens_usados'],
        'error': None,
        'saltado': False,
    }


def probar_lectura_agente(client, modelo: str, archivo_bytes: bytes) -> dict:
    """Prueba mínima de conectividad — confirma que la API Key funciona y el modelo puede leer un PDF real."""
    schema = {
        'type': 'object',
        'properties': {
            'tipoDeDocumentoQueVes': {'type': 'string', 'description': 'Descripción breve de qué tipo de documento parece ser.'},
            'primeraLineaOEncabezado': {'type': 'string', 'description': 'El primer texto legible que veas en el documento.'},
        },
        'required': ['tipoDeDocumentoQueVes', 'primeraLineaOEncabezado'],
    }
    prompt_sistema = 'Eres un asistente que describe brevemente el contenido de un PDF, solo para una prueba de conexión.'
    prompt_documento = 'Describe brevemente qué tipo de documento es este PDF y cuál es el primer texto legible que aparece.'
    return llamar_agente(client, modelo, archivo_bytes, prompt_sistema, prompt_documento, schema)
