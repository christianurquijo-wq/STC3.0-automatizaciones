import fichas_documentos as fd


def test_obtener_ficha_devuelve_variante_general_por_defecto():
    ficha = fd.obtener_ficha('evidenciaDesempleoConsultaAdres')
    assert 'ADRES' in ficha['descripcion']
    assert 'cotizante activo' in ficha['que_revisar'].lower()
    assert ficha['aplica'] == fd.APLICA_TODOS_EXCEPTO_JCO


def test_obtener_ficha_devuelve_variante_jco_cuando_se_pide():
    ficha = fd.obtener_ficha('evidenciaDesempleoConsultaAdres', poblacion='JCO')
    assert 'ACJ' in ficha['descripcion']
    # La variante JCO existe justamente para instruir al agente a NO aplicar el criterio de
    # "cotizante activo" (ese es exclusivo de la consulta ADRES general) — por eso la frase
    # aparece, pero en su forma negada ("NO apliques...").
    assert 'no apliques' in ficha['que_revisar'].lower()


def test_obtener_ficha_campo_sin_variantes_devuelve_la_ficha_tal_cual():
    ficha = fd.obtener_ficha('documentoDeIdentidad')
    assert ficha['aplica'] == fd.APLICA_TODOS
    assert 'CC' in ficha['descripcion']


def test_obtener_ficha_campo_desconocido_devuelve_ficha_vacia_aplica_todos():
    ficha = fd.obtener_ficha('campoQueNoExiste')
    assert ficha == {'aplica': fd.APLICA_TODOS, 'descripcion': '', 'que_revisar': ''}


def test_aplica_todos_siempre_true():
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_TODOS, 'JCO', 'BASICO') is True
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_TODOS, None, None) is True


def test_aplica_todos_excepto_jco():
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_TODOS_EXCEPTO_JCO, 'GENERAL', 'BASICO') is True
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_TODOS_EXCEPTO_JCO, 'JCO', 'ESPECIALIZADO') is False


def test_aplica_solo_jco():
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_SOLO_JCO, 'JCO', None) is True
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_SOLO_JCO, 'GENERAL', None) is False


def test_aplica_todos_excepto_basico():
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_TODOS_EXCEPTO_BASICO, 'GENERAL', 'BÁSICO') is False
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_TODOS_EXCEPTO_BASICO, 'GENERAL', 'BASICO') is False
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_TODOS_EXCEPTO_BASICO, 'GENERAL', 'ESPECIALIZADO') is True


def test_aplica_solo_especializado_no_jco():
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_SOLO_ESPECIALIZADO_NO_JCO, 'GENERAL', 'ESPECIALIZADO') is True
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_SOLO_ESPECIALIZADO_NO_JCO, 'JCO', 'ESPECIALIZADO') is False
    assert fd.aplica_para_poblacion_y_paquete(fd.APLICA_SOLO_ESPECIALIZADO_NO_JCO, 'GENERAL', 'BASICO') is False


def test_resolver_poblacion_prioriza_lo_que_revela_el_nombre_del_archivo():
    entradas = [{'campo': 'documentoDeIdentidad'}, {'campo': 'evidenciaDesempleoConsultaAdres', 'poblacion': 'JCO'}]
    assert fd.resolver_poblacion(entradas, datos_fcs={'jco': 'NO'}) == 'JCO'


def test_resolver_poblacion_cae_al_fcs_si_nada_lo_revela():
    entradas = [{'campo': 'documentoDeIdentidad'}]
    assert fd.resolver_poblacion(entradas, datos_fcs={'jco': 'SI'}) == 'JCO'
    assert fd.resolver_poblacion(entradas, datos_fcs={'jco': 'NO'}) == 'GENERAL'


def test_resolver_poblacion_no_determinada_sin_ninguna_pista():
    assert fd.resolver_poblacion([], datos_fcs=None) == 'NO DETERMINADA'
    assert fd.resolver_poblacion([{'campo': 'x'}], datos_fcs={}) == 'NO DETERMINADA'
