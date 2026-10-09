from types import SimpleNamespace

from fcs import cargar_fcs
from seguimiento import cargar_cedulas_en_ruta


class FakeWorksheet:
    def __init__(self, rows):
        self._rows = rows

    def get_all_values(self):
        return self._rows


class FakeSpreadsheet:
    def __init__(self, hojas):
        self._hojas = hojas

    def worksheet(self, nombre):
        if nombre not in self._hojas:
            raise Exception(f'hoja no encontrada: {nombre}')
        return self._hojas[nombre]


class FakeGC:
    def __init__(self, spreadsheets):
        self._spreadsheets = spreadsheets

    def open_by_key(self, sid):
        return self._spreadsheets[sid]


def _config(**overrides):
    base = dict(
        USAR_FCS=True, FCS_SPREADSHEET_ID='FCS_ID', FCS_HOJA='CONSOLIDADO',
        SEGUIMIENTO_SPREADSHEET_ID='SEG_ID', SEGUIMIENTO_HOJA='SEGUIMIENTO GENERAL', HITO_FILTRO='En ruta',
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_cargar_fcs_encuentra_encabezado_aunque_no_este_en_primera_fila():
    filas = [
        ['STC 3.0 — Consolidado', '', ''],  # fila de título, no es el encabezado real
        ['NUMERO DE DOCUMENTO', 'TIPO DE PAQUETE DE SERVICIO', 'EN RUTA DEL PROGRAMA JOVENES CON OPORTUNIDADES'],
        ['1010039609', 'Básico', 'SI'],
        ['1020304050', 'Especializado', 'NO'],
    ]
    gc = FakeGC({'FCS_ID': FakeSpreadsheet({'CONSOLIDADO': FakeWorksheet(filas)})})
    mapa = cargar_fcs(gc, _config())
    # Sin columnas de nombre en este FCS, nombre_completo queda vacío pero la clave existe siempre.
    assert mapa['1010039609'] == {'paquete': 'BÁSICO', 'jco': 'SI', 'nombre_completo': ''}
    assert mapa['1020304050'] == {'paquete': 'ESPECIALIZADO', 'jco': 'NO', 'nombre_completo': ''}


def test_cargar_fcs_arma_nombre_completo_con_encabezados_reales_multilinea():
    # Encabezados literales confirmados por Christian el 2026-08-26 — vienen con salto de línea
    # dentro de la celda, por eso el match debe ser "empieza con" y no igualdad exacta.
    filas = [
        [
            'NUMERO DE DOCUMENTO', 'TIPO DE PAQUETE DE SERVICIO', 'EN RUTA DEL PROGRAMA JOVENES CON OPORTUNIDADES',
            'NOMBRES \n(NOMBRE 1 Y 2)', 'APELLIDOS \n(APELLIDOS 1 Y 2)', 'APELLIDO 2',
        ],
        ['1010039609', 'Básico', 'SI', 'Juan Carlos', 'Pérez', 'Gómez'],
    ]
    gc = FakeGC({'FCS_ID': FakeSpreadsheet({'CONSOLIDADO': FakeWorksheet(filas)})})
    mapa = cargar_fcs(gc, _config())
    assert mapa['1010039609'] == {
        'paquete': 'BÁSICO', 'jco': 'SI', 'nombre_completo': 'Juan Carlos Pérez Gómez',
    }


def test_cargar_fcs_pestana_faltante_devuelve_mapa_vacio_con_aviso():
    gc = FakeGC({'FCS_ID': FakeSpreadsheet({})})
    avisos = []
    mapa = cargar_fcs(gc, _config(), avisos)
    assert mapa == {}
    assert len(avisos) == 1
    assert 'CONSOLIDADO' in avisos[0][1]


def test_cargar_cedulas_en_ruta_filtra_por_hito_sin_distinguir_mayusculas_ni_espacios():
    filas = [
        ['CC Prospecto', 'Hito', 'Otro'],
        ['1111111111', 'En ruta', 'x'],
        ['2222222222', 'Graduado', 'x'],
        ['3333333333', ' en RUTA ', 'x'],
    ]
    gc = FakeGC({'SEG_ID': FakeSpreadsheet({'SEGUIMIENTO GENERAL': FakeWorksheet(filas)})})
    cedulas = cargar_cedulas_en_ruta(gc, _config())
    assert cedulas == {'1111111111', '3333333333'}


def test_cargar_cedulas_en_ruta_sin_columnas_devuelve_vacio_con_aviso():
    filas = [['Nombre', 'Apellido']]
    gc = FakeGC({'SEG_ID': FakeSpreadsheet({'SEGUIMIENTO GENERAL': FakeWorksheet(filas)})})
    avisos = []
    cedulas = cargar_cedulas_en_ruta(gc, _config(), avisos)
    assert cedulas == set()
    assert len(avisos) == 1
