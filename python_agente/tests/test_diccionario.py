import gspread

import diccionario
from agente_config import DICCIONARIO as DICCIONARIO_RESPALDO, IGNORAR as IGNORAR_RESPALDO


class FakeWorksheet:
    def __init__(self, name, rows=None):
        self.name = name
        self.rows = rows or []

    def clear(self):
        self.rows = []

    def append_row(self, row):
        self.rows.append(row)

    def append_rows(self, rows, value_input_option=None):
        self.rows.extend(rows)

    def get_all_values(self):
        return self.rows


class FakeSpreadsheet:
    def __init__(self, hojas=None):
        self._hojas = hojas or {}

    def worksheet(self, nombre):
        if nombre not in self._hojas:
            raise gspread.WorksheetNotFound(nombre)
        return self._hojas[nombre]

    def add_worksheet(self, title, rows, cols):
        hoja = FakeWorksheet(title)
        self._hojas[title] = hoja
        return hoja


def test_cargar_diccionario_lee_filas_validas_de_la_hoja():
    filas = [
        diccionario.ENCABEZADO,
        ['CC', 'documentoDeIdentidad', '', 'Manual', '2026-01-01'],
        ['ACJ', 'evidenciaDesempleoConsultaAdres', 'JCO', 'Manual', '2026-01-01'],
        ['HV', 'IGNORAR', '', 'Manual', '2026-01-01'],
        ['', '', '', '', ''],  # fila vacía -> se ignora
        ['CAMPOROTO', 'noExiste', '', 'Manual', '2026-01-01'],  # campo inválido -> se ignora
    ]
    ss = FakeSpreadsheet({'Diccionario': FakeWorksheet('Diccionario', filas)})

    dicc, ignorar = diccionario.cargar_diccionario(ss)

    assert dicc['CC'] == {'campo': 'documentoDeIdentidad'}
    assert dicc['ACJ'] == {'campo': 'evidenciaDesempleoConsultaAdres', 'poblacion': 'JCO'}
    assert 'CAMPOROTO' not in dicc
    assert ignorar == {'HV'}


def test_cargar_diccionario_hoja_vacia_la_siembra_con_el_respaldo_de_agente_config():
    ss = FakeSpreadsheet({})  # la pestaña "Diccionario" no existe todavía
    avisos = []

    dicc, ignorar = diccionario.cargar_diccionario(ss, avisos)

    # Esta corrida usa el respaldo fijo de agente_config.py...
    assert dicc == DICCIONARIO_RESPALDO
    assert ignorar == set(IGNORAR_RESPALDO)
    assert len(avisos) == 1

    # ...y además la hoja quedó sembrada para la próxima vez.
    hoja = ss.worksheet('Diccionario')
    assert len(hoja.get_all_values()) == 1 + len(DICCIONARIO_RESPALDO) + len(IGNORAR_RESPALDO)


def test_agregar_entradas_normaliza_el_alias_antes_de_escribir():
    hoja = FakeWorksheet('Diccionario', [diccionario.ENCABEZADO])
    ss = FakeSpreadsheet({'Diccionario': hoja})

    diccionario.agregar_entradas(ss, [
        {'alias': 'Autopostulación', 'campo': 'autopostulacionJovenesConOportunidades', 'origen': 'Aprobado por IA'},
    ])

    fila_nueva = hoja.get_all_values()[-1]
    assert fila_nueva[0] == 'AUTOPOSTULACION'  # normalizado: mayúsculas, sin tilde, sin símbolos
    assert fila_nueva[1] == 'autopostulacionJovenesConOportunidades'
    assert fila_nueva[3] == 'Aprobado por IA'
