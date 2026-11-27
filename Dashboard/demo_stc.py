"""Datos sintéticos (sin datos personales reales) con la misma forma de las fuentes del dashboard STC 3.0.
Los usan las pruebas (test_consultas_stc.py) y la vista previa local del asistente."""
from __future__ import annotations

import numpy as np
import pandas as pd

MOMENTOS = ["0.Sin gestión", "1.En verificación", "2.Verificado", "3.Orientado", "4.Formado", "5.Certificado", "6.Baja"]


def fuentes(n: int = 600, semilla: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(semilla)
    docs = [str(1000000000 + i * 37) for i in range(n)]
    momento = rng.choice(MOMENTOS, n, p=[.12, .1, .2, .25, .18, .1, .05])
    nivel = np.array([int(m[0]) for m in momento])
    paquete = rng.choice(["BÁSICO", "ESPECIALIZADO"], n, p=[.55, .45])
    alta = pd.Timestamp("2026-07-01") + pd.to_timedelta(rng.integers(0, 140, n), unit="D")
    verif = alta + pd.to_timedelta(rng.integers(1, 8, n), unit="D")
    orient = verif + pd.to_timedelta(rng.integers(1, 10, n), unit="D")
    clases = orient + pd.to_timedelta(rng.integers(2, 12, n), unit="D")
    fin = clases + pd.to_timedelta(rng.integers(20, 40, n), unit="D")
    reporte = np.where(nivel >= 3, rng.choice(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"], n), np.where(
        nivel == 2, rng.choice(["", "EN PROCESO"], n), ""))
    esp = paquete == "ESPECIALIZADO"
    est_f = np.where(esp & (nivel == 5), "CERTIFICADO", np.where(esp & (nivel == 4), "FINALIZADO", np.where(
        esp & (nivel == 3), rng.choice(["EN CURSO", "SIN INSCRIBIR", "INSCRITO"], n), "")))
    hito = np.where(nivel.astype(int).__ge__(3) & (rng.random(n) < .6), rng.choice(["Pago 1", "Pago 2", "Pago 2.1", "Pago 3"], n),
                    np.where((nivel >= 1) & (nivel <= 5), "En ruta", ""))
    fmt = lambda s, m: [d.strftime("%Y-%m-%d") if ok else "" for d, ok in zip(s, m)]  # noqa: E731
    general = pd.DataFrame({
        "Fecha": fmt(verif, nivel >= 2), "Evento/Base": rng.choice(["Feria Kennedy", "Base SDDE", "Redes", "Referido"], n),
        "CC Prospecto": docs, "ID CRM": [str(50000 + i) for i in range(n)],
        "Nombre completo": [f"Participante {i}" for i in range(n)], "Correo": [f"p{i}@correo.demo" for i in range(n)],
        "Teléfono": [f"3{i:09d}" for i in range(n)], "Estado CRM": np.where(nivel == 6, "Baja", "Activo"),
        "ID SIS": np.where(nivel >= 2, [str(9000 + i) for i in range(n)], ""), "JCO": rng.choice(["SI", "NO"], n, p=[.3, .7]),
        "Reporte": reporte, "Fecha Orientación": fmt(orient, nivel >= 3), "Paquete": paquete,
        "Remitido": np.where(nivel >= 3, "SI", ""), "Estado de la formación": est_f,
        "Fecha clases": fmt(clases, esp & (nivel >= 3) & (est_f != "SIN INSCRIBIR") & (est_f != "INSCRITO")),
        "Fecha finalización": fmt(fin, esp & (nivel >= 4)), "Momento del proceso": momento,
        "Momento del proceso (Back UP)": momento, "Hito": hito, "Fecha de alta": fmt(alta, np.ones(n, bool)),
        "Verificador": rng.choice(["ana ruiz", "luis gil", "eva paz"], n),
        "Orientador": np.where(nivel >= 2, rng.choice(["marta díaz", "juan rey", "sara león"], n), ""),
    })
    en_f = esp & (nivel >= 3) & (nivel <= 5)
    idx = np.where(en_f)[0]
    m = len(idx)
    asis = rng.choice([0, .25, .5, .75, 1.0], m, p=[.15, .1, .2, .2, .35])
    plat = rng.choice([0, .3, .6, .9, 1.0], m, p=[.15, .15, .2, .2, .3])
    est = est_f[idx]
    formacion = pd.DataFrame({
        "No. DOCUMENTO": [docs[i] for i in idx], "GROUP_ID": rng.choice([3101, 3102, 3205, 3307], m),
        "NOMBRE DEL CURSO": rng.choice(["Servicio al cliente 40H", "Marketing Digital 20H"], m),
        "PROGRAMA": rng.choice(["SERVICIO AL CLIENTE", "MARKETING DIGITAL"], m),
        "ESTADO DE LA FORMACIÓN": np.where(est == "", "EN CURSO", est),
        "% ASISTENCIA": [f"{a * 100:.0f}%" for a in asis], "CANTIDAD DE REGISTROS DE ASISTENCIA (Forms)": (asis * 4).astype(int),
        "FECHA ASISTENCIA A CLASE": [(pd.Timestamp("2026-11-26") - pd.Timedelta(days=int(d))).strftime("%d/%m/%Y")
                                     if a > 0 else "" for d, a in zip(rng.integers(0, 30, m), asis)],
        "% AVANCE PLAT": [f"{p * 100:.0f}%" for p in plat], "Responsable": rng.choice(["Camila", "Diego"], m),
        "FECHA DE CERTIFICACIÓN": np.where(est == "CERTIFICADO", "20/11/2026", ""),
        "CERTIFICADO": np.where((est == "CERTIFICADO") | ((est == "FINALIZADO") & (rng.random(m) < .5)), "https://x/c", "--"),
        "CONSOLIDADO DE FORMACIÓN": rng.choice(["Subido STC", "Generado", "Sin Generar"], m),
        "ALERTA PUBLICACIÓN": np.where(np.isin(est, ["FINALIZADO", "CERTIFICADO"]) & (rng.random(m) < .2),
                                       "ALERTA - REPUBLICAR NOTA", ""),
        "PAQUETE DE PAGO": [hito[i] for i in idx],
    })
    ori = np.where(nivel >= 3)[0]
    cols_fcs = {"NÚMERO DE DOCUMENTO": [docs[i] for i in ori], "Estado Entregable": rng.choice(
        ["LISTO PARA REPORTAR", "REPORTADO", "PENDIENTE"], len(ori))}
    for k in range(1, 20):
        cols_fcs[f"CAMPO {k}"] = np.where(rng.random(len(ori)) < .04, "", "ok")
    fcs = pd.DataFrame(cols_fcs)
    remisiones = pd.DataFrame({"NÚMERO DE DOCUMENTO": [docs[i] for i in ori if rng.random() < .85]})
    enc = [docs[i] for i in ori if rng.random() < .7]
    enc_b = pd.DataFrame({"CEDULA": [d for d in enc if int(d) % 2 == 0], "Marca temporal": "2026-11-20"})
    enc_e = pd.DataFrame({"CEDULA": [d for d in enc if int(d) % 2 == 1], "Marca temporal": "2026-11-21"})
    sub = pd.DataFrame({"Documento": [docs[i] for i in ori[:25]], "Orientador/a": "Marta Díaz",
                        "Dato a usar (KUEPA)": "Vacante 123 - AUXILIAR", "Dato original (FCS)": "Vacante 120 - AUXILIAR"})
    req = ["CÉDULA DE CIUDADANÍA ✓", "ADRES ✓", "ACJ ✓", "DJ ✓", "RENEC ✓", "VRD ✓", "SOPORTE DE RESIDENCIA ✓",
           "FORMACIÓN ✓", "SEGUIMIENTO REMISION ✓", "AUTOPOSTULACIÓN ✓", "ENCUESTA ✓", "MITIGACIÓN EN STC ✓"]
    mat = pd.DataFrame({"CÉDULA": [docs[i] for i in ori], **{r: np.where(rng.random(len(ori)) < .85, "TRUE", "FALSE")
                                                          for r in req}})
    mat["% CUMPLIMIENTO"] = (mat[req].eq("TRUE").mean(axis=1) * 100).round(0).astype(int).astype(str) + "%"
    return {"general": general, "formacion_consolidado": formacion, "orientacion_consolidado": fcs,
            "remisiones": remisiones, "encuesta_basico_jco": enc_b, "encuesta_especializado": enc_e,
            "subsanaciones": sub, "matriz_documental": mat, "verificacion": None}
