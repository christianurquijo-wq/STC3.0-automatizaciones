import sugerencias_diccionario as sug


def test_escanear_glosario_drive_agrupa_y_cuenta_por_nombre(monkeypatch):
    subcarpetas = {
        'RAIZ': [{'id': 'agosto', 'name': 'AGOSTO'}],
        'agosto': [{'id': 'p1', 'name': '1000183279'}, {'id': 'p2', 'name': '1000603339'}],
    }
    archivos = {
        'p1': [{'id': 'f1', 'name': '1000183279_A.pdf'}, {'id': 'f2', 'name': '1000183279_CC.pdf'}],
        'p2': [{'id': 'f3', 'name': '1000603339_A.pdf'}],
    }
    monkeypatch.setattr(sug, 'listar_subcarpetas', lambda drive, cid: subcarpetas.get(cid, []))
    monkeypatch.setattr(sug, 'listar_archivos', lambda drive, cid: archivos.get(cid, []))

    glosario = sug.escanear_glosario_drive(drive_service=object(), carpeta_raiz_id='RAIZ')

    por_nombre = {item['nombre']: item['cantidad'] for item in glosario}
    assert por_nombre == {'A': 2, 'CC': 1}


def test_extraer_nombre_documento_quita_cedula_y_extension():
    assert sug._extraer_nombre_documento('1010039609_Remisión.pdf', '1010039609') == 'Remisión'
    assert sug._extraer_nombre_documento('1010039609 REMISION.PDF', '1010039609') == 'REMISION'


def test_filtrar_nombres_nuevos_descarta_lo_ya_reconocido():
    glosario = [
        {'nombre': 'CC', 'ruta_primera_aparicion': 'x', 'cantidad': 10},
        {'nombre': 'HV', 'ruta_primera_aparicion': 'x', 'cantidad': 5},
        {'nombre': 'Autopostulación', 'ruta_primera_aparicion': 'x', 'cantidad': 3},
    ]
    diccionario_actual = {'CC': {'campo': 'documentoDeIdentidad'}}
    ignorar_actual = {'HV'}

    nuevos = sug.filtrar_nombres_nuevos(glosario, diccionario_actual, ignorar_actual)

    assert [n['nombre'] for n in nuevos] == ['Autopostulación']


def test_sugerir_mapeo_ia_sin_nombres_nuevos_no_llama_al_modelo():
    resultado = sug.sugerir_mapeo_ia(client=None, nombres_nuevos=[], diccionario_actual={}, config=None)
    assert resultado == {'sugerencias': [], 'tokens_usados': 0, 'error': None}
