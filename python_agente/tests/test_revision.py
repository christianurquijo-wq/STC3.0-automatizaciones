"""
Test de integración de revision.ejecutar_revision() — mismo escenario que
/tmp/harness6.js y /tmp/harness7.js usados para validar la versión de Apps
Script: JUNIO/1111111111 (en ruta, el agente SI reporta un hallazgo real),
JUNIO/2222222222 (NO en ruta -> debe ignorarse), JULIO/3333333333 (en ruta,
el agente NO reporta hallazgos), y 4444444444 en ruta pero sin carpeta en
ningún mes -> debe reportarse como hallazgo COM-SINCARPETA.
"""
from types import SimpleNamespace
from datetime import date, datetime

import agente
import revision


class FakeWorksheet:
    def __init__(self, name):
        self.name = name
        self.rows = []

    def clear(self):
        self.rows = []

    def append_row(self, row):
        self.rows.append(row)

    def append_rows(self, rows, value_input_option=None):
        self.rows.extend(rows)

    def get_all_values(self):
        return self.rows


def _config():
    return SimpleNamespace(
        ROOT_FOLDER_ID='RAIZ', REPORT_SPREADSHEET_ID='REPORTE_ID',
        MAX_PARTICIPANTES_POR_CORRIDA=80,
        NOMBRE_HOJA_RESUMEN='Resumen por participante', NOMBRE_HOJA_HALLAZGOS='Hallazgos', NOMBRE_HOJA_CONSUMO='Consumo',
        USAR_FCS=False, FCS_SPREADSHEET_ID='', FCS_HOJA='',
        USAR_LISTA_EN_RUTA=True, SEGUIMIENTO_SPREADSHEET_ID='', SEGUIMIENTO_HOJA='', HITO_FILTRO='En ruta',
        USAR_AGENTE_IA=True,
        VIGENCIA_DESDE=date(2026, 7, 10), VIGENCIA_HASTA=date(2026, 12, 31),
        MODELO_GEMINI='gemini-3.5-flash-lite', MAX_LLAMADAS_AGENTE_POR_CORRIDA=15,
        PAUSA_ENTRE_LLAMADAS_SEG=0, MAX_TOKENS_POR_CORRIDA=200_000, ALERTA_TOKENS_MES=3_000_000,
        ESTIMADOR_PARTICIPANTES_MES=1500, ESTIMADOR_DOCS_POR_PARTICIPANTE=9, CUPO_REFERENCIA_RPD_GRATUITO=1500,
    )


class FakeGC:
    """gc.open_by_key(...) solo necesita devolver *algo* — obtener_o_crear_hoja está mockeado
    y no le presta atención a lo que devuelva, así que basta con un objeto cualquiera."""

    def open_by_key(self, spreadsheet_id):
        return SimpleNamespace(id=spreadsheet_id)


def _preparar_fakes(monkeypatch):
    subcarpetas = {
        'RAIZ': [{'id': 'junio', 'name': 'JUNIO'}, {'id': 'julio', 'name': 'JULIO'}],
        'junio': [{'id': 'p1', 'name': '1111111111'}, {'id': 'p2', 'name': '2222222222'}],
        'julio': [{'id': 'p3', 'name': '3333333333'}],
    }
    archivos = {
        'p1': [{'id': 'f1', 'name': '1111111111_CC.pdf'}],
        'p2': [{'id': 'f2', 'name': '2222222222_CC.pdf'}],
        'p3': [{'id': 'f3', 'name': '3333333333_CC.pdf'}],
    }

    monkeypatch.setattr(revision, 'listar_subcarpetas', lambda drive, carpeta_id: subcarpetas.get(carpeta_id, []))
    monkeypatch.setattr(revision, 'listar_archivos', lambda drive, carpeta_id: archivos.get(carpeta_id, []))
    monkeypatch.setattr(revision, 'descargar_bytes_archivo', lambda drive, file_id: b'X')

    fake_sheets = {}

    def fake_obtener_o_crear_hoja(ss, nombre):
        return fake_sheets.setdefault(nombre, FakeWorksheet(nombre))

    monkeypatch.setattr(revision, 'obtener_o_crear_hoja', fake_obtener_o_crear_hoja)
    monkeypatch.setattr(revision, 'cargar_fcs', lambda gc, config, avisos=None: {})
    monkeypatch.setattr(revision, 'cargar_cedulas_en_ruta', lambda gc, config, avisos=None: {'1111111111', '3333333333', '4444444444'})

    from agente_config import DICCIONARIO, IGNORAR
    monkeypatch.setattr(revision.diccionario, 'cargar_diccionario', lambda ss, avisos=None: (dict(DICCIONARIO), set(IGNORAR)))

    llamadas = {'n': 0}

    def fake_evaluar_documento_con_agente(client, archivo_bytes, nombre_archivo, campo, numero_documento, datos_fcs, presupuesto_agente, config, sleep_fn, poblacion=None):
        presupuesto_agente['restantes'] -= 1
        llamadas['n'] += 1
        presupuesto_agente['tokens_usados'] += 100
        if llamadas['n'] == 1:  # participante 1111111111: el agente SI reporta un hallazgo real del catálogo
            return {'hallazgos_crudos': [{'codigo': 'DI-01', 'detalle': 'Nombre no coincide con el FCS'}],
                    'documento_legible': True, 'tokens_usados': 100, 'error': None, 'saltado': False}
        return {'hallazgos_crudos': [], 'documento_legible': True, 'tokens_usados': 100, 'error': None, 'saltado': False}

    monkeypatch.setattr(agente, 'evaluar_documento_con_agente', fake_evaluar_documento_con_agente)

    return fake_sheets


def test_ejecutar_revision_filtra_por_en_ruta_y_marca_estado_por_campo(monkeypatch):
    fake_sheets = _preparar_fakes(monkeypatch)
    config = _config()

    resultado = revision.ejecutar_revision(
        config, drive_service=object(), gc=FakeGC(), client_gemini='fake-client',
        ahora=datetime(2026, 8, 24, 21, 0, 0),
    )

    encabezado = fake_sheets['Resumen por participante'].rows[0]
    filas = fake_sheets['Resumen por participante'].rows[1:]
    idx_doc_id = encabezado.index('documentoDeIdentidad')
    idx_dj = encabezado.index('declaracionJuramentada')

    def fila(cedula):
        return next(f for f in filas if f[1] == cedula)

    # 1111111111: el agente SI reportó un hallazgo sobre su documento de identidad -> "Con novedad"
    assert fila('1111111111')[idx_doc_id] == 'Con novedad'
    assert fila('1111111111')[idx_dj] == 'No encontrado'  # nunca hubo archivo para ese campo

    # 3333333333: archivo presente, sin hallazgos -> "Verificado"
    assert fila('3333333333')[idx_doc_id] == 'Verificado'

    # 4444444444: "En ruta" pero sin carpeta en ningún mes -> fila con todo "No encontrado"
    assert fila('4444444444')[idx_doc_id] == 'No encontrado'
    assert fila('4444444444')[idx_dj] == 'No encontrado'

    # 2222222222 (NO en ruta) no debe aparecer en absoluto
    assert not any(f[1] == '2222222222' for f in filas)

    hallazgos = fake_sheets['Hallazgos'].rows[1:]
    assert any(h[4] == 'DI-01' and h[2] == '1111111111' for h in hallazgos)
    assert any(h[4] == 'COM-SINCARPETA' and h[2] == '4444444444' for h in hallazgos)

    assert resultado['contador'] == 2  # solo 1111111111 y 3333333333 tenían carpeta real
    assert resultado['cedulas_en_ruta'] == {'1111111111', '3333333333', '4444444444'}

    consumo_rows = fake_sheets['Consumo'].rows[1:]
    tipos = {r[1]: r[2] for r in consumo_rows}
    assert tipos['AGENTE_LLAMADAS'] == 2
    assert tipos['AGENTE_TOKENS'] == 200


def test_ejecutar_revision_sin_filtro_en_ruta_procesa_todo(monkeypatch):
    fake_sheets = _preparar_fakes(monkeypatch)
    config = _config()
    config.USAR_LISTA_EN_RUTA = False

    revision.ejecutar_revision(config, drive_service=object(), gc=FakeGC(), client_gemini='fake-client', ahora=datetime(2026, 8, 24, 21, 0, 0))

    filas = fake_sheets['Resumen por participante'].rows[1:]
    cedulas = {f[1] for f in filas}
    # Sin filtro, 2222222222 SI debe aparecer, y no debe inventarse una fila "sin carpeta" para 4444444444.
    assert cedulas == {'1111111111', '2222222222', '3333333333'}
