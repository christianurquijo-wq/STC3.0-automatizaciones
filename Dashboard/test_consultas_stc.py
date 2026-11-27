"""pytest -q Dashboard/test_consultas_stc.py · asistente de datos del dashboard STC (datos sintéticos)."""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import consultas_stc as Q  # noqa: E402
import demo_stc  # noqa: E402
import gestion as G  # noqa: E402

HOY = dt.date(2026, 11, 26)


@pytest.fixture(scope="module")
def f():
    return demo_stc.fuentes()


@pytest.fixture(scope="module")
def b(f):
    return Q.construir_base(f, HOY)


def test_una_fila_por_persona_y_contacto(b, f):
    assert len(b) == len(f["general"]) and b["doc"].is_unique
    assert b["telefono"].str.match(r"^3\d{9}$").all() and b["correo"].str.contains("@").all()


def test_pendientes_coinciden_con_gestion_diaria(b, f):
    listas = G.listas_pendientes(G.preparar(f["general"]), HOY)
    for etapa, lista in listas.items():
        assert (b["etapa_pendiente"] == etapa).sum() == len(lista)


def test_atajos_de_embudo(b):
    r = Q.aplicar(b, Q.POR_CLAVE["en_verificacion"].filtros)
    assert len(r) and r["momento"].eq("1.En verificación").all() and ~r["baja"].any()
    assert Q.aplicar(b, Q.POR_CLAVE["bajas"].filtros)["momento"].eq("6.Baja").all()


def test_formacion_asistencia_y_plataforma(b, f):
    r = Q.aplicar(b, Q.POR_CLAVE["solo_plataforma"].filtros)
    assert len(r) and (r["asistencia_pct"] == 100).all() and (r["avance_pct"] < 100).all()
    assert not r["estado_formacion"].isin(Q.TERMINADOS).any()
    sin = Q.aplicar(b, Q.POR_CLAVE["sin_asistencia"].filtros)
    assert len(sin) and (sin["asistencia_pct"].fillna(0) == 0).all()
    assert set(b.loc[b["en_formacion"], "tiene_asistencia"]) <= {Q.SI, Q.NO}


def test_porcentajes_en_cualquier_formato():
    assert Q.pct(pd.Series(["85%", "0,5", 1.0, "100", "", None])).tolist()[:4] == [85.0, 50.0, 100.0, 100.0]


def test_orientacion_encuestas_y_fcs(b, f):
    r = Q.aplicar(b, Q.POR_CLAVE["listos_sin_encuesta"].filtros)
    assert r["estado_fcs"].eq("LISTO PARA REPORTAR").all() and r["encuesta"].eq(Q.NO).all()
    fcs_docs = set(f["orientacion_consolidado"]["NÚMERO DE DOCUMENTO"])
    rem_docs = set(f["remisiones"]["NÚMERO DE DOCUMENTO"])
    sin_rem = Q.aplicar(b, Q.POR_CLAVE["sin_remitir"].filtros)
    assert set(sin_rem["doc"]) == fcs_docs - rem_docs
    vac = Q.aplicar(b, Q.POR_CLAVE["campos_vacios"].filtros)
    assert (vac["n_campos_vacios"] >= 1).all() and vac["campos_vacios"].ne("").all()
    assert (Q.aplicar(b, Q.POR_CLAVE["subsanaciones"].filtros)["n_subsanaciones"] >= 1).all()


def test_fechas_por_rango(b):
    f = Q.Filtros("todos", fecha={"f_alta": (dt.date(2026, 9, 1), dt.date(2026, 9, 30), False)})
    r = Q.aplicar(b, f)
    assert len(r) and r["f_alta"].between("2026-09-01", "2026-09-30").all()
    assert "Fecha de alta del 01/09/2026 al 30/09/2026" in Q.describir(f)


def test_resumen_y_distribucion_cuadran(b):
    t = Q.resumen(b, "mes_alta")
    assert t.iloc[-1]["Personas"] == len(b) == t.iloc[:-1]["Personas"].sum()
    d = Q.distribucion(b, "paquete", "momento")
    assert d.iloc[-1]["Total"] == len(b)


def test_csv_para_excel():
    t = Q.para_csv(pd.DataFrame({"asistencia_pct": [87.55], "f_alta": [pd.Timestamp("2026-11-03")]}))
    texto = Q.a_csv(t).decode("utf-8-sig").splitlines()
    assert texto == ["% asistencia;Fecha de alta", "87,6;03/11/2026"] or texto[1].startswith("87,5")


def test_todos_los_atajos_de_lista_corren(b):
    for a in Q.ATAJOS:
        if a.tipo == "lista":
            r = Q.lista(Q.aplicar(b, a.filtros), a.columnas, a.orden, a.asc)
            assert all(c in Q.CAMPOS for c in r.columns), a.clave
