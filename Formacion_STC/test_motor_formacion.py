"""Pruebas del motor de formación con datos sintéticos (sin datos personales). Correr: python -m pytest Formacion_STC"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import motor_formacion as F  # noqa: E402

HOY = pd.Timestamp("2026-11-26")


def df(filas, columnas):
    return pd.DataFrame(filas, columns=columnas)


def letras(filas):
    ancho = max(len(f) for f in filas)
    return pd.DataFrame([list(f) + [""] * (ancho - len(f)) for f in filas],
                        columns=[F.get_column_letter(i + 1) for i in range(ancho)])


def fila_sg(doc, curso="SERVICIO AL CLIENTE", orientacion=46296, mes=46296, hito="Pago 2.1"):
    f = [""] * (F.letra("BT") + 1)
    f[F.letra("F")], f[F.letra("AA")], f[F.letra("Q")] = doc, "ANA PEREZ", "Ana Perez Gil"
    f[F.letra("AG")], f[F.letra("AT")], f[F.letra("BI")] = orientacion, curso, mes   # 46296 = 01/10/2026
    f[F.letra("BH")] = hito   # «Hito» del SG: pago en que la SDDE aprobó a la persona
    return f


def fuentes(asist=100, prog_us=100.0, logs_extra=True):
    f = {
        "REPORTE CRM": df([["111", "Ana Perez", "JCO", "501", "300", "a@x.co"], ["222", "Luis Gil", "JCO", "502", "", ""]],
                          ["Documento", "Estudiante", "Adnetwork", "ID CRM", "Telefono", "Correo"]),
        "REPORTE SIS": df([[10, "501", "111", "Básico", "Básico", "GB"],
                           [10, "501", "111", "Especializado 40H", "Servicio al cliente 40H", "G1"],
                           [20, "502", "222", "Especializado 20H", "Marketing Digital 20H", "G2"]],
                          ["ID", "ID CRM", "Cedula", "Paquete", "Programa", "Group_id"]),
        "ASISTENCIAS": df([["10", asist, "2026-10-05T07:00:00.000-05:00"], ["20", 0, "2026-10-06T07:00:00.000-05:00"]],
                          ["ID_SIS", "ATTENDANCE_STATUS", "FECHA_ASISTENCIA"]),
        "USER_STATISTICS": df([["10", "G1", prog_us, "2026-10-20T04:00:00.000Z"]],
                              ["ID_SIS", "GROUP_ID", "PROGRESO", "FECHA_FINALIZACION_ASINCRONICA"]),
        "LOGS": df([["10", 100.0, "2026-10-18T10:00:00.000-05:00"]] if logs_extra else [],
                   ["ID_SIS", "PROGRESO_PROGRAMA", "FECHA_LOG_PROGRAMA"]),
        "LOG_ACCESS": df([["111", "L1", 1.5], ["111", "L2", 0.5], ["222", "", ""]],
                         ["PROFILE_DOC_NUMBER", "LOG_ID", "TIME_VIEW"]),
        "SESIONES": df([["S9", "G2", "Especializado 20H", "26/11/2026", 4, "meet/x", True]],
                       ["CLASS_SESSION_ID", "STRUCTURE_ID", "PROGRAMA", "STAR_DATE", "NUMBER_SESSION", "MEET_LINK",
                        "ENVIADO"]),
        "SG": letras([fila_sg("111"), fila_sg("222", "MARKETING_DIGITAL")]),
    }
    return f


def base(*docs):
    return pd.DataFrame({c: [""] * len(docs) for c in F.COLUMNAS}).assign(G=list(docs))


def test_estados_y_columnas_clave():
    out = F.calcular(base(111, 222, ""), fuentes(), HOY)
    a, b, vacia = out.iloc[0], out.iloc[1], out.iloc[2]
    assert a["D"] == 10 and a["L"] == "G1"            # se prefiere la fila del especializado del SIS
    assert a["N"] == "ESPECIALIZADO 40H" and a["M"] == "SERVICIO AL CLIENTE"
    assert a["E"] == "ANA PEREZ GIL"                   # el más completo entre SG AA y Q
    assert a["AA"] == 1 and a["AD"] == 1 and a["O"] == "FINALIZADO"
    assert a["Y"] == "20/10/2026"                      # la fecha más reciente entre asistencia, US y logs
    assert a["P"] == "FINALIZADO" and a["AS"] == 6
    assert a["AQ"] == 2 and a["AR"] == 2.0             # solo filas con LOG_ID
    assert a["AU"] == "Pago 2.1" and a["V"] == "SERVICIO AL CLIENTE" and a["W"] is True
    assert b["O"] == "INSCRITO" and b["AQ"] == 0
    assert (b["P"], b["Q"], b["R"], b["U"]) == ("S9", 4, "meet/x", True)   # sesión de hoy de su grupo
    assert all(vacia[c] == "" for c in F.CALCULADAS)


def test_en_curso_y_certificado():
    out = F.calcular(base(111), fuentes(asist=0, prog_us=40.0, logs_extra=False), HOY)
    assert out.iloc[0]["O"] == "EN CURSO" and out.iloc[0]["AD"] == 0.4
    f = fuentes()
    f["CERTIFICADOS"] = letras([[""] * 21, ["", "ANA", "111", "", "", "", "", "19/10/2026", "", "", "url", "", "", "21/10/2026",
                                            "", "P1", "APROBADO", "", "", "", True]])
    out = F.calcular(base(111), f, HOY)
    r = out.iloc[0]
    assert r["O"] == "CERTIFICADO" and r["AP"] == "Subido STC" and r["Y"] == "21/10/2026"


def test_especializados_y_nuevas():
    sg = letras([[""] * 72] * 0 + [
        ["" for _ in range(72)] for _ in range(4)])
    sg.loc[:, "F"] = ["1000111", "1000333", "1000444", "1000555"]
    sg.loc[:, "AH"] = ["ESPECIALIZADO", "ESPECIALIZADO", "BÁSICO", "ESPECIALIZADO"]
    sg.loc[:, "AE"] = ["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN", "FINALIZADO", "EN PROCESO"]
    sg.loc[:, "BT"] = ["4.Formado", "3.Orientado", "3.Orientado", "3.Orientado"]
    assert F.especializados_sg(sg) == ["1000111", "1000333"]
    sit = F.situacion_sg(sg)
    assert sit["1000444"].startswith("Paquete") and sit["1000555"].startswith("Orientación")
    tabla, nuevas = F.con_nuevas(base(1000111), F.especializados_sg(sg))
    assert nuevas == ["1000333"] and tabla["G"].tolist() == [1000111, 1000333]


def test_fechas():
    assert F.fecha("2026-11-05T22:00:00.000-05:00") == pd.Timestamp("2026-11-05")
    assert F.fecha("05/11/2026") == pd.Timestamp("2026-11-05")
    assert F.fecha(46331) == pd.Timestamp("2026-11-05")
    assert F.fecha("") is None and F.fecha("--") is None


def test_sis_sin_seguimiento_y_cedulas_raras():
    sis = df([[1, "11", "100", "Especializado 40H"], [2, "22", "200", "Especializado 20H"],
              [3, "33", "300", "Básico"], [4, "44", "999", "Especializado 40H"], [5, "55", "500", "Especializado 40H"]],
             ["ID", "ID CRM", "Cedula", "Paquete"])
    sg = letras([["" for _ in range(30)] for _ in range(2)])
    sg.loc[:, "F"] = ["100", "400"]
    sg.loc[:, "Z"] = ["", "4"]          # el 4 está en el SG con otra cédula: cruza por ID SIS
    b = base(500)
    b.loc[:, "C"] = ["--"]
    sin = F.sis_sin_seguimiento(sis, sg, b)
    assert sin["ID SIS"].tolist() == [2]
    assert F.cedula_rara("38075").startswith("Muy corta")
    assert F.cedula_rara("29/03/2004").startswith("Parece una fecha")
    assert F.cedula_rara("1023034451") == ""


def test_depurar():
    b = base(1000111, 1000222, "", 38075)
    b.loc[:, "AM"] = ["nota 1", "nota 2", "", ""]
    queda, salen = F.depurar(b, {"1000222"})
    assert queda["G"].tolist() == [1000222] and queda["AM"].tolist() == ["nota 2"]
    assert salen["G"].tolist() == [1000111, 38075]


def test_no_agrega_cedulas_raras():
    tabla, nuevas = F.con_nuevas(base(111), ["38075", "29/03/2004", "1023034451"])
    assert nuevas == ["1023034451"]


def test_limpieza_conserva_terminados():
    b = base(1000111, 1000222, 1000333)
    estados = pd.Series(["CERTIFICADO", "INSCRITO", "FINALIZADO"], index=b.index)
    queda, salen = F.depurar(b, set(), estados)
    assert queda["G"].tolist() == [1000111, 1000333] and salen["G"].tolist() == [1000222]
    out = F.calcular(queda, fuentes(), HOY, observaciones={"1000111": "Baja en el CRM (6.Baja)"})
    assert out.iloc[0]["BJ"] == "Baja en el CRM (6.Baja)" and out.iloc[1]["BJ"] == ""


def test_avance_toma_el_dato_mayor_y_revision():
    f = fuentes()
    f["USER_STATISTICS"] = df([["10", "G1", 40.0, "", "Servicio al cliente 40H", "Servicio al cliente 40H - 1"],
                               ["10", "G9", 90.0, "", "Servicio al cliente 40H", "Servicio al cliente 40H - 2"],
                               ["10", "G7", 100.0, "", "Herramientas ofimáticas 40H", "Herramientas 40H - 1"]],
                              ["ID_SIS", "GROUP_ID", "PROGRESO", "FECHA_FINALIZACION_ASINCRONICA", "PROGRAMA", "CARRIL"])
    f["LOGS"] = df([], ["ID_SIS", "PROGRESO_PROGRAMA", "FECHA_LOG_PROGRAMA"])
    out = F.calcular(base(111), f, HOY)
    assert out.iloc[0]["AD"] == 1.0 and out.iloc[0]["AH"] == 1.0          # el mayor, aunque no sea del grupo G1
    rev = F.revision_multigrupo(out, f)
    assert len(rev) == 3 and set(rev["¿El dato mayor es de otro curso?"]) == {"Sí - revisar"}
    assert rev.loc[rev["Group_id en el SIS"] == "G7", "¿Es el dato mayor?"].item() == "Sí"


def test_fecha_fin_solo_para_terminados():
    out = F.calcular(base(111, 222), fuentes(), HOY)
    assert out.iloc[0]["O"] == "FINALIZADO" and out.iloc[0]["Y"] == "20/10/2026"
    assert out.iloc[1]["O"] == "INSCRITO" and out.iloc[1]["Y"] == ""
    en_curso = F.calcular(base(111), fuentes(asist=100, prog_us=40.0, logs_extra=False), HOY).iloc[0]
    assert en_curso["O"] == "EN CURSO" and en_curso["Y"] == ""                  # asistió pero no terminó


def test_paquete_de_pago_es_el_hito_del_sg():
    """AU = «Hito» (BH) del Seguimiento General: «Pago N», «En ruta» o vacío; vacío si la cédula no está en el SG."""
    f = fuentes()
    f["SG"] = letras([fila_sg("111", hito="Pago 3"), fila_sg("222", "MARKETING_DIGITAL", hito="En ruta")])
    out = F.calcular(base(111, 222, 333), f, HOY)
    assert out["AU"].tolist() == ["Pago 3", "En ruta", ""]
    f["SG"] = letras([fila_sg("111", hito=""), fila_sg("222", "MARKETING_DIGITAL", hito=None)])
    assert F.calcular(base(111, 222), f, HOY)["AU"].tolist() == ["", ""]
