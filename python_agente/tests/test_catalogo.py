from catalogo import codigos_validos_para_campo, obtener_observacion


def test_obtener_observacion_del_catalogo_oficial():
    obs = obtener_observacion('documentoDeIdentidad', 'DI-01')
    assert obs['texto'] == 'Documento vencido.'
    assert obs['categoria'] == 'Otro'


def test_obtener_observacion_interna_por_codigo():
    # COM-SINFECHA no está en el catálogo oficial de ningún campo — debe
    # resolverse contra OBSERVACIONES_INTERNAS, no caer al respaldo genérico.
    obs = obtener_observacion('certificadoDeResidencia', 'COM-SINFECHA', 'texto de respaldo', 'categoria de respaldo')
    assert obs['texto'] != 'texto de respaldo'
    assert 'no reconoció ninguna fecha' in obs['texto']


def test_obtener_observacion_cae_a_respaldo_si_no_existe():
    obs = obtener_observacion('documentoDeIdentidad', 'CODIGO-INVENTADO', 'texto de respaldo', 'Otro')
    assert obs == {'codigo': 'CODIGO-INVENTADO', 'texto': 'texto de respaldo', 'categoria': 'Otro'}


def test_codigos_validos_incluye_sin_fecha_solo_en_certificado_residencia():
    codigos_cr = [c['codigo'] for c in codigos_validos_para_campo('certificadoDeResidencia')]
    assert 'COM-SINFECHA' in codigos_cr
    assert 'COM-FECHAAMBIGUA' in codigos_cr

    codigos_di = [c['codigo'] for c in codigos_validos_para_campo('documentoDeIdentidad')]
    assert 'COM-SINFECHA' not in codigos_di
