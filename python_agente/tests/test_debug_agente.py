from datetime import date
from types import SimpleNamespace

import agente
import debug_agente


def test_buscar_carpeta_participante_encuentra_por_cedula_normalizada(monkeypatch):
    subcarpetas = {
        'RAIZ': [{'id': 'agosto', 'name': 'AGOSTO'}],
        'agosto': [{'id': 'p1', 'name': '1.010.039.609'}],
    }
    monkeypatch.setattr(debug_agente, 'listar_subcarpetas', lambda drive, cid: subcarpetas.get(cid, []))

    carpeta = debug_agente.buscar_carpeta_participante(drive_service=object(), carpeta_raiz_id='RAIZ', numero_documento='1010039609')

    assert carpeta == {'id': 'p1', 'name': '1.010.039.609', 'nombre_mes': 'AGOSTO'}


def test_buscar_carpeta_participante_devuelve_none_si_no_existe(monkeypatch):
    monkeypatch.setattr(debug_agente, 'listar_subcarpetas', lambda drive, cid: [])
    assert debug_agente.buscar_carpeta_participante(drive_service=object(), carpeta_raiz_id='RAIZ', numero_documento='1010039609') is None


def _config():
    return SimpleNamespace(
        MODELO_GEMINI='gemini-3.5-flash-lite',
        VIGENCIA_DESDE=date(2026, 7, 10), VIGENCIA_HASTA=date(2026, 12, 31),
        PAUSA_ENTRE_LLAMADAS_SEG=0,
    )


def test_depurar_documento_arma_el_detalle_completo(monkeypatch):
    monkeypatch.setattr(agente, 'llamar_agente', lambda client, modelo, archivo_bytes, prompt_sistema, prompt_documento, schema: {
        'datos': {'documentoLegible': True, 'hallazgos': []}, 'tokens_usados': 123, 'error': None,
    })

    resultado = debug_agente.depurar_documento(
        client='fake-client', archivo_bytes=b'X', nombre_archivo='1010039609_CC.pdf',
        campo='documentoDeIdentidad', numero_documento='1010039609', datos_fcs=None, config=_config(),
    )

    assert resultado['nombre_archivo'] == '1010039609_CC.pdf'
    assert resultado['campo'] == 'documentoDeIdentidad'
    assert resultado['datos_crudos'] == {'documentoLegible': True, 'hallazgos': []}
    assert resultado['tokens_usados'] == 123
    assert resultado['error'] is None
    assert 'documentoDeIdentidad' in resultado['prompt_documento']


def test_depurar_participante_solo_llama_al_agente_sobre_archivos_clasificados(monkeypatch):
    archivos = [
        {'id': 'f1', 'name': '1010039609_CC.pdf'},
        {'id': 'f2', 'name': '1010039609_HV.pdf'},  # en IGNORAR -> no debe llamar al agente
        {'id': 'f3', 'name': '1010039609_ALGOQUENOEXISTE.pdf'},  # sin clasificar -> tampoco
    ]
    monkeypatch.setattr(debug_agente, 'listar_archivos', lambda drive, cid: archivos)
    monkeypatch.setattr(debug_agente, 'descargar_bytes_archivo', lambda drive, fid: b'X')

    llamadas = []
    monkeypatch.setattr(debug_agente, 'depurar_documento', lambda client, ab, na, campo, nd, fcs, cfg, poblacion=None: llamadas.append(na) or {'nombre_archivo': na})

    resultados = debug_agente.depurar_participante(
        client='fake-client', drive_service=object(), config=_config(),
        diccionario_actual={'CC': {'campo': 'documentoDeIdentidad'}}, ignorar_actual={'HV'},
        carpeta_participante={'id': 'p1', 'name': '1010039609'}, numero_documento='1010039609', datos_fcs=None,
    )

    assert llamadas == ['1010039609_CC.pdf']
    assert len(resultados) == 1
