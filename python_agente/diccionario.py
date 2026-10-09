"""
Diccionario de siglas -> campo oficial, con persistencia en una pestaña del
Sheet de reporte ("Diccionario") en vez de vivir fijo en agente_config.py —
así se puede actualizar sin tocar código ni hacer un deploy: se edita a mano
directamente en el Sheet, o se aprueban sugerencias del agente IA desde
Streamlit (ver sugerencias_diccionario.py) y quedan escritas ahí.

Estructura de la pestaña "Diccionario" (se crea sola, vacía, la primera vez
que corre una revisión o se usa la sugerencia de IA):

    Alias (normalizado) | Campo | Población | Origen | Fecha

"Campo" debe ser uno de los CAMPOS_PLATAFORMA, o el literal "IGNORAR" para
las siglas que a propósito no deben clasificarse (equivalente al IGNORAR
de agente_config.py, ej. HV/HVKUEPA/CLV).

Si la pestaña está vacía, o no se puede leer por cualquier motivo, se cae de
vuelta a los valores fijos de agente_config.py (DICCIONARIO/IGNORAR) — un
problema con el Sheet nunca debe tumbar una corrida de revisión.
"""
from datetime import date
from typing import Dict, List, Optional, Tuple

from agente_config import CAMPOS_PLATAFORMA, DICCIONARIO as DICCIONARIO_RESPALDO, IGNORAR as IGNORAR_RESPALDO
from google_clients import obtener_o_crear_hoja
from utilidades import normalizar_nombre

NOMBRE_HOJA_DICCIONARIO = 'Diccionario'
CAMPO_IGNORAR = 'IGNORAR'
ENCABEZADO = ['Alias (normalizado)', 'Campo', 'Población', 'Origen', 'Fecha']


def normalizar_alias(texto: str) -> str:
    """Misma normalización que se le aplica a los nombres de archivo reales (mayúsculas, sin tildes,
    sin símbolos) — así un alias guardado en el Sheet calza con lo que revision.py calcula en cada corrida."""
    return normalizar_nombre(texto, '')


def cargar_diccionario(spreadsheet, avisos: Optional[List[Tuple[str, str]]] = None) -> Tuple[Dict[str, dict], set]:
    """
    Lee la pestaña 'Diccionario' del Sheet de reporte y devuelve (diccionario,
    ignorar) con la misma forma que los de agente_config.py. Si la pestaña no
    existe, la crea y la siembra con lo que hoy vive fijo en agente_config.py
    (para no perder nada al migrar) y devuelve ese mismo respaldo para esta
    corrida. Si algo falla, agrega un aviso y usa el respaldo fijo — nunca
    lanza una excepción hacia quien llama.
    """
    avisos = avisos if avisos is not None else []
    try:
        hoja = obtener_o_crear_hoja(spreadsheet, NOMBRE_HOJA_DICCIONARIO)
        valores = hoja.get_all_values()

        if len(valores) < 2:
            _sembrar(hoja)
            avisos.append((
                'Aviso',
                'La pestaña "Diccionario" estaba vacía — se sembró con los valores por defecto '
                'de agente_config.py. Esta corrida usó ese mismo respaldo.',
            ))
            return dict(DICCIONARIO_RESPALDO), set(IGNORAR_RESPALDO)

        diccionario_cargado: Dict[str, dict] = {}
        ignorar_cargado: set = set()
        for fila in valores[1:]:
            if not fila or not fila[0].strip():
                continue
            alias = fila[0].strip().upper()
            campo = fila[1].strip() if len(fila) > 1 else ''
            poblacion = fila[2].strip() if len(fila) > 2 else ''

            if campo == CAMPO_IGNORAR:
                ignorar_cargado.add(alias)
            elif campo in CAMPOS_PLATAFORMA:
                entrada = {'campo': campo}
                if poblacion:
                    entrada['poblacion'] = poblacion
                diccionario_cargado[alias] = entrada
            # Campo vacío o inválido (dato corrupto en el Sheet) -> se ignora esa fila en silencio,
            # no debe tumbar la corrida completa por un error de tipeo de una sola celda.

        if not diccionario_cargado and not ignorar_cargado:
            avisos.append((
                'Aviso',
                'La pestaña "Diccionario" no tenía filas válidas — se usó el respaldo fijo de agente_config.py.',
            ))
            return dict(DICCIONARIO_RESPALDO), set(IGNORAR_RESPALDO)

        return diccionario_cargado, ignorar_cargado

    except Exception as e:
        avisos.append((
            'Aviso',
            f'No se pudo leer la pestaña "Diccionario" ({e}). Se usó el respaldo fijo de agente_config.py.',
        ))
        return dict(DICCIONARIO_RESPALDO), set(IGNORAR_RESPALDO)


def _sembrar(hoja) -> None:
    """Llena la pestaña recién creada con lo que hoy vive fijo en agente_config.py, para no perder nada al migrar."""
    filas = [ENCABEZADO]
    for alias, entrada in DICCIONARIO_RESPALDO.items():
        filas.append([alias, entrada['campo'], entrada.get('poblacion', ''), 'Semilla inicial (agente_config.py)', date.today().isoformat()])
    for alias in IGNORAR_RESPALDO:
        filas.append([alias, CAMPO_IGNORAR, '', 'Semilla inicial (agente_config.py)', date.today().isoformat()])
    hoja.clear()
    hoja.append_rows(filas, value_input_option='RAW')


def agregar_entradas(spreadsheet, entradas: List[dict]) -> None:
    """
    entradas: [{alias, campo, poblacion, origen}]. Agrega filas nuevas a la
    pestaña 'Diccionario' — se usa al aprobar sugerencias del agente IA desde
    Streamlit, o para agregar un alias manualmente desde código/tests.
    El alias se normaliza antes de guardarse, para que calce con lo que
    revision.py calcula sobre los nombres de archivo reales.
    """
    if not entradas:
        return
    hoja = obtener_o_crear_hoja(spreadsheet, NOMBRE_HOJA_DICCIONARIO)
    if not hoja.get_all_values():
        hoja.append_row(ENCABEZADO)

    hoy = date.today().isoformat()
    filas = [
        [normalizar_alias(e['alias']), e['campo'], e.get('poblacion', ''), e.get('origen', 'Aprobado manualmente'), hoy]
        for e in entradas
    ]
    hoja.append_rows(filas, value_input_option='RAW')
