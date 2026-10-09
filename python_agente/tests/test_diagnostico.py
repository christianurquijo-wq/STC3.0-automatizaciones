from diagnostico import buscar_primer_pdf


def test_buscar_primer_pdf_recorre_mes_y_participante(monkeypatch):
    import diagnostico

    subcarpetas = {
        'RAIZ': [{'id': 'junio', 'name': 'JUNIO'}, {'id': 'julio', 'name': 'JULIO'}],
        'junio': [{'id': 'p1', 'name': '1111111111'}],
        'julio': [{'id': 'p2', 'name': '2222222222'}],
    }
    archivos = {'p1': [], 'p2': [{'id': 'f1', 'name': '2222222222_CC.pdf'}]}

    monkeypatch.setattr(diagnostico, 'listar_subcarpetas', lambda drive, cid: subcarpetas.get(cid, []))
    monkeypatch.setattr(diagnostico, 'listar_archivos', lambda drive, cid: archivos.get(cid, []))

    encontrado = buscar_primer_pdf(drive_service=object(), carpeta_raiz_id='RAIZ')
    assert encontrado == {'id': 'f1', 'name': '2222222222_CC.pdf'}


def test_buscar_primer_pdf_devuelve_none_si_no_hay_archivos(monkeypatch):
    import diagnostico

    monkeypatch.setattr(diagnostico, 'listar_subcarpetas', lambda drive, cid: [] if cid != 'RAIZ' else [{'id': 'junio', 'name': 'JUNIO'}])
    monkeypatch.setattr(diagnostico, 'listar_archivos', lambda drive, cid: [])

    assert buscar_primer_pdf(drive_service=object(), carpeta_raiz_id='RAIZ') is None
