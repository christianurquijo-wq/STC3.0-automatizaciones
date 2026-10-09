from utilidades import normalizar_documento, normalizar_nombre, quitar_acentos


def test_normalizar_nombre_quita_extension_prefijo_y_simbolos():
    assert normalizar_nombre('1010039609 REMISION.pdf', '1010039609') == 'REMISION'
    assert normalizar_nombre('1010039609_DJ.pdf', '1010039609') == 'DJ'
    assert normalizar_nombre('1010039609_CC.PDF', '1010039609') == 'CC'
    assert normalizar_nombre('1010039609-REMISION+.pdf', '1010039609') == 'REMISION'


def test_normalizar_nombre_le_quita_tildes_antes_de_comparar():
    # Bug real encontrado con datos de producción: el regex de limpieza borraba
    # la vocal tildada en vez de normalizarla, así que "Remisión" nunca calzaba
    # con la entrada "REMISION" del diccionario.
    assert normalizar_nombre('1010039609_Remisión.pdf', '1010039609') == 'REMISION'
    assert normalizar_nombre('1010039609_AUTOPOSTULACIÓN.pdf', '1010039609') == 'AUTOPOSTULACION'
    assert normalizar_nombre('1010039609_MIGRACIÓN.pdf', '1010039609') == 'MIGRACION'


def test_normalizar_documento_deja_solo_digitos():
    assert normalizar_documento('1.010.039.609') == '1010039609'
    assert normalizar_documento(1010039609) == '1010039609'
    assert normalizar_documento(None) == ''
    assert normalizar_documento('') == ''


def test_quitar_acentos():
    assert quitar_acentos('EN RUTA') == 'EN RUTA'
    assert quitar_acentos('José Andrés') == 'Jose Andres'
    assert quitar_acentos('NÚMERO DE DOCUMENTO') == 'NUMERO DE DOCUMENTO'
