"""
Modo debug — revisa TODOS los documentos clasificados de UNA cédula puntual
y devuelve el detalle completo de cada llamada al agente IA: el prompt
exacto que se le mandó (incluyendo qué datos del FCS y qué rango de vigencia
usó) y la respuesta cruda completa, incluso cuando el documento está en
regla (que hoy no queda registrado en ningún lado — el Sheet de Hallazgos
solo guarda lo que SÍ encontró mal). Es la herramienta para calibrar por qué
el agente marca, o no marca, una novedad en un documento concreto.

No escribe nada en el Sheet de reporte — es de solo lectura/diagnóstico.
SÍ hace llamadas reales a Gemini (gasta tokens de verdad), así que se usa
manualmente para calibrar, no como parte de la corrida normal.
"""
import time
from typing import List, Optional

import agente
import fichas_documentos
from catalogo import codigos_validos_para_campo
from google_clients import descargar_bytes_archivo, listar_archivos, listar_subcarpetas
from utilidades import normalizar_documento, normalizar_nombre


def buscar_carpeta_participante(drive_service, carpeta_raiz_id: str, numero_documento: str) -> Optional[dict]:
    """Recorre mes -> participante buscando la carpeta de una cédula puntual (comparando ya normalizada,
    para que no importe si el usuario la escribe con puntos o espacios). Devuelve {id, name, nombre_mes} o None."""
    doc_buscado = normalizar_documento(numero_documento)
    if not doc_buscado:
        return None
    for carpeta_mes in listar_subcarpetas(drive_service, carpeta_raiz_id):
        for carpeta_participante in listar_subcarpetas(drive_service, carpeta_mes['id']):
            if normalizar_documento(carpeta_participante['name']) == doc_buscado:
                return {'id': carpeta_participante['id'], 'name': carpeta_participante['name'], 'nombre_mes': carpeta_mes['name']}
    return None


def depurar_documento(
    client, archivo_bytes: bytes, nombre_archivo: str, campo: str,
    numero_documento: str, datos_fcs: Optional[dict], config,
    poblacion: Optional[str] = None,
) -> dict:
    """
    Igual que agente.evaluar_documento_con_agente(), pero sin presupuesto de
    corrida ni pausa de rate-limit, y devolviendo TODO lo que se usó para
    decidir — el prompt exacto y la respuesta cruda sin filtrar — para poder
    ver exactamente qué comparó el agente y por qué.

    poblacion se calcula UNA sola vez para todo el participante (ver
    depurar_participante) con fichas_documentos.resolver_poblacion(), para
    que use exactamente el mismo criterio que revision.py.
    """
    codigos_validos = codigos_validos_para_campo(campo)
    schema = agente.construir_esquema_respuesta(codigos_validos)
    prompt_sistema = agente.construir_prompt_sistema()
    prompt_documento = agente.construir_prompt_documento(campo, numero_documento, datos_fcs, nombre_archivo, config, poblacion)

    resultado = agente.llamar_agente(client, config.MODELO_GEMINI, archivo_bytes, prompt_sistema, prompt_documento, schema)

    return {
        'nombre_archivo': nombre_archivo,
        'campo': campo,
        'prompt_sistema': prompt_sistema,
        'prompt_documento': prompt_documento,
        'codigos_disponibles': [c['codigo'] for c in codigos_validos],
        'datos_crudos': resultado['datos'],
        'tokens_usados': resultado['tokens_usados'],
        'error': resultado['error'],
    }


def depurar_participante(
    client, drive_service, config, diccionario_actual: dict, ignorar_actual: set,
    carpeta_participante: dict, numero_documento: str, datos_fcs: Optional[dict],
    sleep_fn=time.sleep,
) -> List[dict]:
    """Clasifica los archivos de la carpeta de un participante (misma lógica que revision.py) y
    llama al agente en modo debug sobre cada uno clasificado (los sin-clasificar/ignorados se saltan,
    igual que en la corrida normal, porque el agente nunca los revisa tampoco ahí).

    Dos pasadas: primero se clasifican TODOS los archivos (para poder resolver la población del
    participante una sola vez, con el mismo criterio que revision.py — ver
    fichas_documentos.resolver_poblacion), y solo después se llama al agente sobre cada uno, ya
    con la población correcta para elegir la ficha/variante (ej. ADRES vs ACJ)."""
    archivos = listar_archivos(drive_service, carpeta_participante['id'])
    clasificados = []  # lista de (archivo, entrada) para los archivos que sí se van a revisar
    for archivo in archivos:
        norm = normalizar_nombre(archivo['name'], numero_documento)
        if norm in ignorar_actual:
            continue
        entrada = diccionario_actual.get(norm)
        if not entrada:
            continue
        clasificados.append((archivo, entrada))

    poblacion = fichas_documentos.resolver_poblacion([entrada for _, entrada in clasificados], datos_fcs)

    resultados = []
    for i, (archivo, entrada) in enumerate(clasificados):
        archivo_bytes = descargar_bytes_archivo(drive_service, archivo['id'])
        resultados.append(depurar_documento(
            client, archivo_bytes, archivo['name'], entrada['campo'], numero_documento, datos_fcs, config, poblacion,
        ))

        if i < len(clasificados) - 1:
            sleep_fn(config.PAUSA_ENTRE_LLAMADAS_SEG)  # respeta el límite de solicitudes por minuto del nivel gratuito

    return resultados
