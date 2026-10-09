"""Puerto a Python de Seguimiento.gs — lista de participantes a revisar ("Seguimiento General")."""
from typing import List, Optional, Set, Tuple

from utilidades import normalizar_documento, quitar_acentos

SEGUIMIENTO_ENCABEZADOS = {
    'cedula': 'CC PROSPECTO',
    'hito': 'HITO',
}


def cargar_cedulas_en_ruta(gc, config, avisos: Optional[List[Tuple[str, str]]] = None) -> Set[str]:
    """
    Lee la hoja de Seguimiento General y devuelve un set con los números de
    documento (normalizados, solo dígitos) que tienen Hito = config.HITO_FILTRO.
    Si algo falla, agrega un aviso a `avisos` y devuelve un set vacío — con
    USAR_LISTA_EN_RUTA=True eso significa que la corrida no procesa a nadie
    (mejor eso que procesar de más por un error silencioso).
    """
    avisos = avisos if avisos is not None else []
    cedulas: Set[str] = set()

    try:
        ss = gc.open_by_key(config.SEGUIMIENTO_SPREADSHEET_ID)
        try:
            hoja = ss.worksheet(config.SEGUIMIENTO_HOJA)
        except Exception:
            avisos.append((
                'Aviso',
                f'No se encontró la pestaña "{config.SEGUIMIENTO_HOJA}" en Seguimiento General. '
                'No se procesará ningún participante esta corrida (revisar config.SEGUIMIENTO_HOJA).',
            ))
            return cedulas

        datos = hoja.get_all_values()

        fila_encabezado = -1
        col_index = {'cedula': -1, 'hito': -1}
        for f in range(min(20, len(datos))):
            idx = _mapear_encabezados(datos[f])
            if idx['cedula'] != -1 and idx['hito'] != -1:
                fila_encabezado = f
                col_index = idx
                break

        if fila_encabezado == -1:
            avisos.append((
                'Aviso',
                'No se encontraron las columnas "CC Prospecto" y "Hito" en las primeras filas de '
                'Seguimiento General. No se procesará ningún participante esta corrida — revisar '
                'los encabezados de esa hoja.',
            ))
            return cedulas

        hito_buscado = quitar_acentos(config.HITO_FILTRO.strip().upper())
        for f in range(fila_encabezado + 1, len(datos)):
            fila = datos[f]
            hito = quitar_acentos(str(_valor(fila, col_index['hito']) or '').strip().upper())
            if hito != hito_buscado:
                continue
            cedula = normalizar_documento(_valor(fila, col_index['cedula']))
            if cedula:
                cedulas.add(cedula)
    except Exception as e:
        avisos.append(('Aviso', f'No se pudo leer Seguimiento General ({e}). No se procesará ningún participante esta corrida.'))

    return cedulas


def _valor(fila, indice: int):
    if indice == -1 or indice >= len(fila):
        return ''
    return fila[indice]


def _mapear_encabezados(fila) -> dict:
    resultado = {'cedula': -1, 'hito': -1}
    for c, celda in enumerate(fila):
        texto = quitar_acentos(str(celda or '').strip().upper())
        if texto == SEGUIMIENTO_ENCABEZADOS['cedula']:
            resultado['cedula'] = c
        if texto == SEGUIMIENTO_ENCABEZADOS['hito']:
            resultado['hito'] = c
    return resultado
