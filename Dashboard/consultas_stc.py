"""
Asistente de datos del dashboard STC 3.0 (nov-2026): consultas puntuales del equipo con cifra y CSV.

Sin IA. El equipo elige un atajo (consulta frecuente) o arma la suya en el constructor. Todo sale de las mismas
fuentes que ya usa el dashboard, unidas en UNA tabla por persona (construir_base):
  * Seguimiento General (BigQuery STC_3_0_V2_2026): embudo, paquete, JCO, gestores, hito de pago, fechas.
  * CONSOLIDADO de formación: estado, programa, grupo, % asistencia, % avance en plataforma, certificado, nota.
  * Consolidado FCS (orientación), remisiones, encuestas de mitigación (básico/JCO y especializado),
    subsanaciones de Kuepa empleo y matriz documental.
Las reglas son las del dashboard: gestion.py (pendientes, días hábiles, semáforo, tiempos, actividad, hitos) y
analitica.py (orientados sin remitir, listos sin encuesta, campos vacíos del FCS). Este módulo no usa Streamlit:
se prueba con pytest (test_consultas_stc.py).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import gestion as G

SI, NO = "Sí", "No"
TERMINADOS = {"FINALIZADO", "CERTIFICADO"}
REPORTES_FINALIZADOS = {"FINALIZADO", "FINALIZADO PENDIENTE X REMISION"}
FCS_ULTIMA_COLUMNA, FCS_EXCLUIR = 83, {6, 7}  # A:CE sin G y H (igual que analitica.campos_vacios_fcs)
REQUISITOS = ["CÉDULA DE CIUDADANÍA ✓", "ADRES ✓", "ACJ ✓", "DJ ✓", "RENEC ✓", "VRD ✓", "SOPORTE DE RESIDENCIA ✓",
              "FORMACIÓN ✓", "SEGUIMIENTO REMISION ✓", "AUTOPOSTULACIÓN ✓", "ENCUESTA ✓", "MITIGACIÓN EN STC ✓"]

# ------------------------------------------------------------------ columnas (nombre interno → encabezado del CSV)
CAMPOS = {
    "documento": "Documento", "nombre": "Nombre", "telefono": "Teléfono", "correo": "Correo",
    "id_crm": "ID CRM", "id_sis": "ID SIS", "evento": "Evento/Base", "estado_crm": "Estado CRM", "jco": "JCO",
    "paquete": "Paquete", "momento": "Momento del proceso", "reporte": "Reporte de orientación",
    "verificador": "Verificador", "orientador": "Orientador", "hito": "Hito de pago", "remitido": "Remitido",
    "bono": "Bono enviado", "mes_alta": "Mes de alta",
    "f_alta": "Fecha de alta", "f_verif": "Fecha de verificación", "f_orient": "Fecha de orientación",
    "f_clases": "Fecha de clases", "f_fin": "Fecha de finalización",
    "etapa_pendiente": "Pendiente de", "gestor_pendiente": "Responsable de la etapa", "esperando_desde": "Esperando desde",
    "dias_habiles": "Días hábiles esperando", "semaforo": "Semáforo",
    "estado_formacion": "Estado de la formación", "programa": "Programa", "curso": "Curso", "grupo": "Grupo (GROUP_ID)",
    "asistencia_pct": "% asistencia", "tiene_asistencia": "¿Tiene asistencia?", "registros_asistencia": "Registros de asistencia",
    "f_ult_asistencia": "Última asistencia a clase", "avance_pct": "% avance en plataforma",
    "tiene_progreso": "¿Tiene progreso en plataforma?", "f_inicio_form": "Inicio de formación",
    "f_fin_form": "Fin de formación", "f_cert": "Fecha de certificación", "tiene_certificado": "¿Tiene certificado?",
    "consolidado_cert": "Certificado en STC", "alerta_nota": "Alerta de nota", "paquete_pago": "Paquete de pago",
    "responsable_form": "Responsable de formación",
    "en_fcs": "¿Está en el FCS?", "estado_fcs": "Estado entregable (FCS)", "en_remisiones": "¿Está en remisiones?",
    "encuesta": "¿Tiene encuesta?", "tipo_encuesta": "Encuesta",
    "n_campos_vacios": "Campos vacíos en el FCS", "campos_vacios": "Cuáles campos vacíos",
    "n_subsanaciones": "Subsanaciones", "subsanaciones": "Detalle de subsanaciones",
    "pct_matriz": "% cumplimiento matriz documental", "faltantes_matriz": "Documentos faltantes",
}
CONTACTO = ["documento", "nombre", "telefono", "correo"]
EMBUDO = ["evento", "paquete", "jco", "momento", "verificador", "orientador", "hito"]
FORMACION = ["estado_formacion", "programa", "grupo", "asistencia_pct", "avance_pct", "f_ult_asistencia"]
COLUMNAS_BASE = CONTACTO + EMBUDO + ["estado_formacion", "f_alta"]
COLUMNAS_LISTA = list(CAMPOS)

UNIVERSOS = {
    "vivos": "Todos sin bajas",
    "todos": "Todos (incluye bajas)",
    "formacion": "En el consolidado de formación (sin bajas)",
    "formacion_curso": "En formación sin terminar (sin bajas)",
    "orientados": "Orientados (reporte finalizado, sin bajas)",
}
FILTROS_CAT = [("evento", "Evento/Base"), ("paquete", "Paquete"), ("jco", "JCO"), ("estado_crm", "Estado CRM"),
               ("momento", "Momento del proceso"), ("mes_alta", "Mes de alta"), ("verificador", "Verificador"),
               ("orientador", "Orientador"), ("hito", "Hito de pago"), ("etapa_pendiente", "Pendiente de"),
               ("semaforo", "Semáforo"), ("estado_formacion", "Estado de la formación"), ("programa", "Programa"),
               ("grupo", "Grupo"), ("responsable_form", "Responsable de formación"),
               ("tiene_asistencia", "¿Tiene asistencia?"), ("tiene_progreso", "¿Tiene progreso en plataforma?"),
               ("tiene_certificado", "¿Tiene certificado?"), ("consolidado_cert", "Certificado en STC"),
               ("paquete_pago", "Paquete de pago"), ("encuesta", "¿Tiene encuesta?"), ("en_remisiones", "¿Está en remisiones?"),
               ("estado_fcs", "Estado entregable (FCS)")]
FILTROS_RANGO = [("asistencia_pct", "% asistencia", 0.0, 100.0), ("avance_pct", "% avance en plataforma", 0.0, 100.0),
                 ("dias_habiles", "Días hábiles esperando", 0.0, 60.0),
                 ("n_campos_vacios", "Campos vacíos en el FCS", 0.0, 80.0),
                 ("pct_matriz", "% cumplimiento matriz documental", 0.0, 100.0)]
FILTROS_FECHA = [("f_alta", "Fecha de alta"), ("f_verif", "Fecha de verificación"), ("f_orient", "Fecha de orientación"),
                 ("f_clases", "Fecha de clases"), ("f_fin", "Fecha de finalización"),
                 ("f_cert", "Fecha de certificación"), ("f_ult_asistencia", "Última asistencia a clase")]
ETIQUETA = dict(FILTROS_CAT + [(k, v) for k, v, *_ in FILTROS_RANGO] + FILTROS_FECHA)

DIM_RESUMEN = ["mes_alta", "evento", "paquete", "jco", "momento", "verificador", "orientador", "hito", "programa",
               "grupo", "estado_formacion", "responsable_form"]
COL_DISTRIBUCION = {"momento": "Momento del proceso", "hito": "Hito de pago", "paquete": "Paquete",
                    "estado_formacion": "Estado de la formación", "semaforo": "Semáforo", "encuesta": "¿Tiene encuesta?"}


@dataclass
class Filtros:
    universo: str = "vivos"
    cat: dict[str, list[str]] = field(default_factory=dict)
    rango: dict[str, tuple[float, float]] = field(default_factory=dict)
    fecha: dict[str, tuple] = field(default_factory=dict)   # columna → (desde | None, hasta | None, incluir_vacíos)


# ------------------------------------------------------------------ utilidades
def norm_doc(v) -> str:
    """Solo dígitos (sin .0 de Excel); vacío si tiene menos de 6 (igual que normalizador.normalizar_cedula)."""
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return ""
    t = re.sub(r"\D", "", re.sub(r"\.0+$", "", str(v).strip()))
    return t if len(t) >= 6 else ""


def plano(v) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(v if v is not None else "")).encode("ascii", "ignore").decode()
    return " ".join(t.upper().split())


def _txt(s: pd.Series) -> pd.Series:
    return s.astype("string").fillna("").str.strip().replace({"<NA>": "", "nan": "", "None": ""})


def _col(df: pd.DataFrame | None, *nombres: str) -> pd.Series:
    """Primera columna que exista (comparando sin tildes ni mayúsculas); vacía si ninguna."""
    if df is None:
        return pd.Series(dtype=object)
    por_plano = {plano(c): c for c in df.columns}
    for n in nombres:
        if plano(n) in por_plano:
            return df[por_plano[plano(n)]]
    return pd.Series([""] * len(df), index=df.index, dtype=object)


def pct(s: pd.Series) -> pd.Series:
    """«85%», «0,85», 0.85 o 85 → 85.0. Sin «%» y ≤ 1 se toma como fracción (el consolidado guarda 0–1)."""
    t = _txt(s)
    con_pct = t.str.contains("%")
    n = pd.to_numeric(t.str.replace("%", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")
    return n.where(con_pct | (n > 1), n * 100).round(1)


def _por_doc(df: pd.DataFrame | None, *col_doc: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    d["_doc"] = _col(d, *col_doc).map(norm_doc)
    return d[d["_doc"].ne("")]


def _primera(d: pd.DataFrame, valores: pd.Series) -> dict:
    return dict(zip(d["_doc"][::-1], valores[::-1]))   # la primera fila de cada cédula gana


# ------------------------------------------------------------------ tabla única por persona
def construir_base(f: dict[str, pd.DataFrame | None], hoy: dt.date) -> pd.DataFrame:
    """f: general, formacion_consolidado, orientacion_consolidado, remisiones, encuesta_basico_jco,
    encuesta_especializado, subsanaciones, matriz_documental (las que falten quedan vacías)."""
    gen = f["general"]
    prep = G.preparar(gen)
    b = pd.DataFrame(index=prep.index)
    b["doc"] = _col(prep, "CC Prospecto").map(norm_doc)
    b["documento"] = b["doc"]
    b["nombre"] = _txt(_col(prep, "Nombre completo"))
    b["telefono"] = _txt(_col(prep, "Teléfono")).str.replace(r"\.0+$", "", regex=True)
    b["correo"] = _txt(_col(prep, "Correo")).str.lower()
    b["id_crm"] = _txt(_col(prep, "ID CRM")).str.replace(r"\.0+$", "", regex=True)
    b["id_sis"] = _txt(_col(prep, "ID SIS")).str.replace(r"\.0+$", "", regex=True)
    b["evento"] = _txt(_col(prep, "Evento/Base"))
    b["estado_crm"] = _txt(_col(prep, "Estado CRM"))
    jco = _txt(_col(prep, "¿Es JCO?", "JCO"))
    b["jco"] = jco.map(lambda v: SI if plano(v) in {"SI", "TRUE", "1", "JCO", "VERDADERO"} else (NO if v else ""))
    b["paquete"] = prep["_paq"].str.title()
    b["momento"] = _txt(_col(prep, "Momento del proceso (Back UP)"))
    b["reporte"] = _txt(_col(prep, "Reporte"))
    b["verificador"] = _txt(_col(prep, "Verificador")).str.title()
    b["orientador"] = _txt(_col(prep, "Orientador")).str.title()
    b["hito"] = prep["_hito"]
    b["remitido"] = _txt(_col(prep, "Remitido"))
    b["bono"] = _txt(_col(prep, "Bono enviado"))
    b["f_alta"], b["f_verif"], b["f_orient"] = prep["_f_alta"], prep["_f_verif"], prep["_f_orient"]
    b["f_clases"], b["f_fin"] = prep["_f_clases"], prep["_f_fin"]
    b["mes_alta"] = b["f_alta"].dt.strftime("%Y-%m").fillna("")
    b["baja"], b["orientado"] = prep["_baja"], prep["_orientado"]
    b["estado_formacion"] = _txt(_col(prep, "Estado de la formación")).str.upper()

    # pendientes por etapa (las 4 listas de Gestión diaria, con días hábiles y semáforo)
    partes = [l.assign(_etapa=e) for e, l in G.listas_pendientes(prep, hoy).items() if not l.empty]
    pend = (pd.concat(partes, ignore_index=True) if partes else
            pd.DataFrame(columns=["Cédula", "_etapa", "Gestor", "Esperando desde", "Días hábiles", "Semáforo"]))
    pend["doc"] = pend["Cédula"].map(norm_doc)
    pend = pend[pend["doc"].ne("")].drop_duplicates("doc").set_index("doc")
    b["etapa_pendiente"] = b["doc"].map(pend["_etapa"]).fillna("")
    b["gestor_pendiente"] = b["doc"].map(pend["Gestor"]).fillna("")
    b["esperando_desde"] = pd.to_datetime(b["doc"].map(pend["Esperando desde"]), errors="coerce")
    b["dias_habiles"] = pd.to_numeric(b["doc"].map(pend["Días hábiles"]), errors="coerce")
    b["semaforo"] = b["doc"].map(pend["Semáforo"]).fillna("")

    # formación (CONSOLIDADO, una fila por cédula)
    fo = _por_doc(f.get("formacion_consolidado"), "No. DOCUMENTO", "Cedula")
    b["en_formacion"] = b["doc"].isin(set(fo["_doc"])) if len(fo) else False
    def de_form(*nombres, transformar=None):
        if not len(fo):
            return pd.Series([""] * len(b), index=b.index, dtype=object)
        v = _col(fo, *nombres)
        v = transformar(v) if transformar else _txt(v)
        return b["doc"].map(_primera(fo, v))
    est_f = de_form("ESTADO DE LA FORMACIÓN").fillna("").str.upper()
    b["estado_formacion"] = est_f.where(est_f.ne(""), b["estado_formacion"])
    b["programa"] = de_form("PROGRAMA").fillna("")
    b["curso"] = de_form("NOMBRE DEL CURSO").fillna("")
    b["grupo"] = de_form("GROUP_ID").fillna("").astype(str).str.replace(r"\.0+$", "", regex=True)
    b["asistencia_pct"] = pd.to_numeric(de_form("% ASISTENCIA", transformar=pct), errors="coerce")
    b["registros_asistencia"] = pd.to_numeric(de_form("CANTIDAD DE REGISTROS DE ASISTENCIA (Forms)",
                                                      "CANTIDAD DE REGISTROS DE ASISTENCIA"), errors="coerce")
    b["f_ult_asistencia"] = G.fecha(de_form("FECHA ASISTENCIA A CLASE").fillna(""))
    b["avance_pct"] = pd.to_numeric(de_form("% AVANCE PLAT", transformar=pct), errors="coerce")
    b["f_inicio_form"] = G.fecha(de_form("FECHA DE INICIO (DD/MM/AAAA)", "FECHA DE INICIO").fillna(""))
    b["f_fin_form"] = G.fecha(de_form("FECHA DE FINALIZACIÓN (DD/MM/AAAA)", "FECHA DE FINALIZACIÓN").fillna(""))
    b["f_cert"] = G.fecha(de_form("FECHA DE CERTIFICACIÓN").fillna(""))
    cert = de_form("CERTIFICADO").fillna("")
    b["tiene_certificado"] = np.where(~b["en_formacion"], "", np.where(cert.ne("") & cert.ne("--"), SI, NO))
    b["consolidado_cert"] = de_form("CONSOLIDADO DE FORMACIÓN").fillna("")
    b["alerta_nota"] = de_form("ALERTA PUBLICACIÓN").fillna("")
    b["paquete_pago"] = de_form("PAQUETE DE PAGO").fillna("")
    b["responsable_form"] = de_form("Responsable").fillna("").str.title()
    asis_ok = b["asistencia_pct"].fillna(0).gt(0) | b["registros_asistencia"].fillna(0).gt(0)
    b["tiene_asistencia"] = np.where(b["en_formacion"], np.where(asis_ok, SI, NO), "")
    b["tiene_progreso"] = np.where(b["en_formacion"], np.where(b["avance_pct"].fillna(0).gt(0), SI, NO), "")

    # orientación (FCS), remisiones, encuestas, campos vacíos del FCS
    fcs = _por_doc(f.get("orientacion_consolidado"), "NÚMERO DE DOCUMENTO")
    rem = _por_doc(f.get("remisiones"), "NÚMERO DE DOCUMENTO")
    b["en_fcs"] = np.where(b["doc"].isin(set(fcs["_doc"]) if len(fcs) else set()), SI, NO)
    b["en_remisiones"] = np.where(b["doc"].isin(set(rem["_doc"]) if len(rem) else set()), SI, NO)
    b["estado_fcs"] = (b["doc"].map(_primera(fcs, _txt(_col(fcs, "Estado Entregable")).str.upper())).fillna("")
                       if len(fcs) else "")
    enc_b = set(_por_doc(f.get("encuesta_basico_jco"), "CEDULA").get("_doc", []))
    enc_e = set(_por_doc(f.get("encuesta_especializado"), "CEDULA").get("_doc", []))
    b["encuesta"] = np.where(b["doc"].isin(enc_b | enc_e), SI, NO)
    b["tipo_encuesta"] = np.select([b["doc"].isin(enc_e), b["doc"].isin(enc_b)], ["Especializado", "Básico / JCO"], "")
    vac_n, vac_txt = campos_vacios_fcs(f.get("orientacion_consolidado"))
    b["n_campos_vacios"] = b["doc"].map(vac_n).where(b["en_fcs"].eq(SI))
    b["campos_vacios"] = b["doc"].map(vac_txt).fillna("")

    # subsanaciones (Kuepa empleo) y matriz documental
    sub = _por_doc(f.get("subsanaciones"), "Documento")
    if len(sub):
        dato = _txt(_col(sub, "Dato a usar (KUEPA)")) + " ← " + _txt(_col(sub, "Dato original (FCS)"))
        g = pd.DataFrame({"_doc": sub["_doc"], "t": dato}).groupby("_doc")["t"]
        b["n_subsanaciones"] = b["doc"].map(g.size()).fillna(0).astype(int)
        b["subsanaciones"] = b["doc"].map(g.apply(lambda s: " | ".join(s))).fillna("")
    else:
        b["n_subsanaciones"], b["subsanaciones"] = 0, ""
    mat = _por_doc(f.get("matriz_documental"), "CÉDULA")
    if len(mat):
        b["pct_matriz"] = b["doc"].map(_primera(mat, pct(_col(mat, "% CUMPLIMIENTO"))))
        presentes = [c for c in REQUISITOS if c in mat.columns]
        falt = mat[presentes].apply(lambda r: ", ".join(c.replace(" ✓", "") for c in presentes
                                                         if plano(r[c]) not in {"TRUE", "VERDADERO", "SI", "1"}), axis=1)
        b["faltantes_matriz"] = b["doc"].map(_primera(mat, falt)).fillna("")
    else:
        b["pct_matriz"], b["faltantes_matriz"] = np.nan, ""
    b = b[b["doc"].ne("")].drop_duplicates("doc").reset_index(drop=True)
    return b


def campos_vacios_fcs(fcs: pd.DataFrame | None) -> tuple[dict, dict]:
    """{cédula: n.º de campos vacíos} y {cédula: lista} en A:CE sin G y H (regla de analitica.campos_vacios_fcs)."""
    if fcs is None or fcs.empty or "NÚMERO DE DOCUMENTO" not in fcs:
        return {}, {}
    cols = [c for i, c in enumerate(fcs.columns[:FCS_ULTIMA_COLUMNA]) if i not in FCS_EXCLUIR]
    x = fcs[cols].astype("string").fillna("").apply(lambda s: s.str.strip()).eq("")
    docs = fcs["NÚMERO DE DOCUMENTO"].map(norm_doc)
    n, txt = {}, {}
    for d, fila in zip(docs, x.itertuples(index=False)):
        if d and d not in n:
            vacios = [c for c, v in zip(cols, fila) if v]
            n[d], txt[d] = len(vacios), ", ".join(vacios)
    return n, txt


# ------------------------------------------------------------------ filtros
def universo(b: pd.DataFrame, clave: str) -> pd.DataFrame:
    if clave == "todos":
        return b
    vivos = b[~b["baja"]]
    if clave == "formacion":
        return vivos[vivos["en_formacion"]]
    if clave == "formacion_curso":
        return vivos[vivos["en_formacion"] & ~vivos["estado_formacion"].isin(TERMINADOS)]
    if clave == "orientados":
        return vivos[vivos["orientado"]]
    return vivos


def aplicar(b: pd.DataFrame, f: Filtros) -> pd.DataFrame:
    d = universo(b, f.universo)
    for col, valores in f.cat.items():
        if valores and col in d:
            d = d[d[col].astype(str).isin([str(v) for v in valores])]
    for col, (lo, hi) in f.rango.items():
        if col in d:
            d = d[pd.to_numeric(d[col], errors="coerce").between(lo, hi)]
    for col, (desde, hasta, vacios) in f.fecha.items():
        if col in d and (desde is not None or hasta is not None):
            v = pd.to_datetime(d[col], errors="coerce").dt.normalize()
            ok = pd.Series(True, index=d.index)
            if desde is not None:
                ok &= v >= pd.Timestamp(desde)
            if hasta is not None:
                ok &= v <= pd.Timestamp(hasta)
            d = d[ok | (v.isna() if vacios else False)]
    return d


def describir(f: Filtros) -> str:
    partes = [UNIVERSOS.get(f.universo, f.universo)]
    for col, valores in f.cat.items():
        if valores:
            partes.append(f"{ETIQUETA.get(col, CAMPOS.get(col, col))}: {', '.join(map(str, valores))}")
    for col, (lo, hi) in f.rango.items():
        partes.append(f"{ETIQUETA.get(col, CAMPOS.get(col, col))} entre {lo:g} y {hi:g}")
    for col, (desde, hasta, vacios) in f.fecha.items():
        if desde is None and hasta is None:
            continue
        rango = (f"del {pd.Timestamp(desde):%d/%m/%Y}" if desde is not None else "") + \
                (f" al {pd.Timestamp(hasta):%d/%m/%Y}" if hasta is not None else "")
        partes.append(f"{ETIQUETA.get(col, CAMPOS.get(col, col))} {rango.strip()}" + (" (o sin fecha)" if vacios else ""))
    return " · ".join(partes)


def combinar(base: Filtros, *otros: Filtros | None) -> Filtros:
    f = Filtros(base.universo, dict(base.cat), dict(base.rango), dict(base.fecha))
    for o in otros:
        if o is not None:
            f.cat.update({k: v for k, v in o.cat.items() if v})
            f.rango.update(o.rango)
            f.fecha.update(o.fecha)
    return f


# ------------------------------------------------------------------ resultados
def lista(d: pd.DataFrame, columnas: list[str], orden: list[str] | None = None, asc=True) -> pd.DataFrame:
    cols = [c for c in columnas if c in d]
    orden = [c for c in (orden or []) if c in d]
    if orden:
        d = d.sort_values(orden, ascending=asc if isinstance(asc, bool) else asc[:len(orden)], na_position="last")
    return d[cols].reset_index(drop=True)


def resumen(d: pd.DataFrame, por: str) -> pd.DataFrame:
    """Una fila por valor de la dimensión, con el embudo y la formación (mismas reglas del dashboard)."""
    x = d.copy()
    x[por] = x[por].replace("", "(vacío)").fillna("(vacío)")
    nivel = pd.to_numeric(x["momento"].str.extract(r"^(\d)")[0], errors="coerce")
    est = x["estado_formacion"]
    basico_ok = x["paquete"].eq("Básico") & x["reporte"].map(plano).isin(REPORTES_FINALIZADOS)
    esp_ok = x["paquete"].eq("Especializado") & x["reporte"].map(plano).isin(REPORTES_FINALIZADOS) & est.isin(TERMINADOS)
    x = x.assign(_sg=nivel.eq(0), _ver=nivel.eq(1), _verif=nivel.between(2, 5), _ori=x["orientado"],
                 _bas=basico_ok, _esp=esp_ok, _form=x["en_formacion"], _cert=est.eq("CERTIFICADO"), _baja=nivel.eq(6),
                 _pago=x["hito"].str.startswith("Pago"), _venc=x["semaforo"].eq(G.SEMAFORO[0]))
    g = x.groupby(por)
    t = pd.DataFrame({
        "Personas": g.size(), "0. Sin gestión": g["_sg"].sum(), "1. En verificación": g["_ver"].sum(),
        "Verificados": g["_verif"].sum(), "Orientados": g["_ori"].sum(), "Básico logrado": g["_bas"].sum(),
        "Especializado logrado": g["_esp"].sum(), "En formación": g["_form"].sum(), "Certificados": g["_cert"].sum(),
        "Con pago aprobado": g["_pago"].sum(), "Pendientes vencidos": g["_venc"].sum(), "Bajas": g["_baja"].sum(),
        "% asistencia promedio": g["asistencia_pct"].mean().round(1),
        "% avance plataforma promedio": g["avance_pct"].mean().round(1),
    })
    t = t.reset_index().rename(columns={por: CAMPOS.get(por, por)})
    num = [c for c in t.columns[1:] if not c.startswith("%")]
    t[num] = t[num].astype(int)
    total = {t.columns[0]: "Total", **{c: int(t[c].sum()) for c in num},
             "% asistencia promedio": round(float(x["asistencia_pct"].mean()), 1) if x["asistencia_pct"].notna().any() else None,
             "% avance plataforma promedio": round(float(x["avance_pct"].mean()), 1) if x["avance_pct"].notna().any() else None}
    return pd.concat([t, pd.DataFrame([total])], ignore_index=True)


def distribucion(d: pd.DataFrame, filas: str, columnas: str) -> pd.DataFrame:
    x = d.assign(**{filas: d[filas].replace("", "(vacío)").fillna("(vacío)"),
                    columnas: d[columnas].replace("", "(vacío)").fillna("(vacío)")})
    t = pd.crosstab(x[filas], x[columnas])
    t["Total"] = t.sum(axis=1)
    t.loc["Total"] = t.sum()
    t.index.name = CAMPOS.get(filas, filas)
    t.columns.name = None
    return t.reset_index()


# ------------------------------------------------------------------ exportación
def para_csv(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    for c in t.columns:
        s = t[c]
        if s.dtype == bool:
            t[c] = s.map({True: SI, False: NO})
        elif pd.api.types.is_datetime64_any_dtype(s):
            t[c] = s.dt.strftime("%d/%m/%Y")
        elif pd.api.types.is_float_dtype(s):
            t[c] = s.round(1)
    return t.rename(columns={c: CAMPOS.get(c, c) for c in t.columns})


def a_csv(t: pd.DataFrame) -> bytes:
    """CSV para Excel en español: «;», coma decimal, UTF-8 con BOM."""
    return t.to_csv(sep=";", index=False, decimal=",").encode("utf-8-sig")


# ------------------------------------------------------------------ atajos
@dataclass
class Atajo:
    clave: str
    grupo: str
    titulo: str
    pregunta: str
    tipo: str          # lista | tiempos | actividad | hitos | resumen | distribucion
    definicion: str
    filtros: Filtros = field(default_factory=Filtros)
    columnas: list[str] = field(default_factory=lambda: list(COLUMNAS_BASE))
    orden: list[str] = field(default_factory=list)
    asc: bool | list[bool] = True
    parametro: str = ""


_PEND = CONTACTO + ["evento", "paquete", "jco", "momento", "etapa_pendiente", "gestor_pendiente", "esperando_desde",
                    "dias_habiles", "semaforo"]
_FORM = CONTACTO + ["paquete", "orientador", "programa", "grupo", "estado_formacion", "asistencia_pct",
                    "registros_asistencia", "f_ult_asistencia", "avance_pct", "responsable_form", "hito"]
_ORI = CONTACTO + ["evento", "paquete", "jco", "orientador", "reporte", "f_orient", "estado_fcs", "en_remisiones",
                   "encuesta", "tipo_encuesta"]

ATAJOS: list[Atajo] = [
    # Embudo y estado
    Atajo("sin_gestion", "Embudo y estado", "Sin gestión", "¿Quiénes siguen sin gestión?", "lista",
          "Leads en «0.Sin gestión»: no han entregado documentos. Días hábiles desde el alta en el CRM.",
          Filtros("vivos", cat={"momento": ["0.Sin gestión"]}), _PEND + ["f_alta", "verificador"], ["dias_habiles"], False),
    Atajo("en_verificacion", "Embudo y estado", "En verificación", "¿Quiénes están en verificación?", "lista",
          f"«1.En verificación»: entregaron documentos y esperan verificación. Plazo {G.UMBRALES['Verificación']} días "
          "hábiles desde el alta; semáforo 🔴 vencido · 🟡 por vencer · 🟢 en plazo.",
          Filtros("vivos", cat={"momento": ["1.En verificación"]}), _PEND + ["verificador"], ["dias_habiles"], False),
    Atajo("sin_orientar", "Embudo y estado", "Verificados sin orientar", "¿Quiénes están verificados y sin orientar?",
          "lista", "Verificados (con ID SIS) cuyo reporte no está FINALIZADO ni FINALIZADO PENDIENTE X REMISIÓN. "
          f"Plazo {G.UMBRALES['Orientación']} días hábiles.",
          Filtros("vivos", cat={"etapa_pendiente": ["Verificados sin orientar"]}), _PEND + ["orientador", "f_verif"],
          ["dias_habiles"], False),
    Atajo("esp_sin_formacion", "Embudo y estado", "Orientados especializados sin iniciar formación",
          "¿Qué orientados especializados no han empezado formación?", "lista",
          "Orientación finalizada y formación SIN INSCRIBIR o INSCRITO sin clases. Días desde la orientación; plazo "
          f"{G.UMBRALES['Inscripción a formación']} días hábiles.", Filtros("vivos"),
          _PEND + ["orientador", "f_orient", "estado_formacion"], ["dias_habiles"], False, "etapa_inscripcion"),
    Atajo("por_hito", "Embudo y estado", "Por hito de pago", "¿Quiénes están en el Pago…?", "lista",
          "Hito del Seguimiento General: pago en que la SDDE aprobó a la persona («Pago 1», «Pago 2.1»…) o «En ruta».",
          Filtros("todos"), CONTACTO + EMBUDO + ["estado_formacion", "paquete_pago"], ["hito"], parametro="hitos"),
    Atajo("bajas", "Embudo y estado", "Bajas en el CRM", "¿Quiénes son baja?", "lista",
          "«6.Baja»: baja en el CRM (registro más reciente).", Filtros("todos", cat={"momento": ["6.Baja"]}),
          CONTACTO + EMBUDO + ["estado_crm", "f_alta"], ["f_alta"]),
    Atajo("por_momento", "Embudo y estado", "Lista por momento, paquete o JCO",
          "Necesito la lista de los que están en…", "lista",
          "Elige momentos del proceso; acota con paquete, JCO, evento o mes de alta en «Más filtros».", Filtros("todos"),
          CONTACTO + EMBUDO + ["estado_formacion", "f_alta", "f_verif", "f_orient"], ["momento"], parametro="momentos"),
    # Formación
    Atajo("sin_asistencia", "Formación", "En formación sin asistencia", "¿Quiénes no han ido a clase?", "lista",
          "En el consolidado de formación, sin terminar, con 0 % de asistencia y sin registros de asistencia.",
          Filtros("formacion_curso", cat={"tiene_asistencia": [NO]}), _FORM, ["grupo"]),
    Atajo("sin_progreso", "Formación", "Sin progreso en plataforma", "¿Quiénes no han avanzado en plataforma?", "lista",
          "En el consolidado de formación con 0 % de avance en plataforma.",
          Filtros("formacion_curso", cat={"tiene_progreso": [NO]}), _FORM, ["grupo"]),
    Atajo("solo_plataforma", "Formación", "Les falta solo plataforma", "¿A quiénes solo les falta la plataforma?",
          "lista", "100 % de asistencia y menos de 100 % de avance en plataforma, sin terminar la formación.",
          Filtros("formacion_curso", rango={"asistencia_pct": (100, 100), "avance_pct": (0, 99.9)}), _FORM, ["avance_pct"], False),
    Atajo("solo_asistencia", "Formación", "Les falta solo asistencia", "¿A quiénes solo les falta asistir?", "lista",
          "100 % de avance en plataforma y menos de 100 % de asistencia, sin terminar la formación.",
          Filtros("formacion_curso", rango={"avance_pct": (100, 100), "asistencia_pct": (0, 99.9)}), _FORM,
          ["asistencia_pct"], False),
    Atajo("certificados", "Formación", "Certificados pendientes", "¿Qué certificados faltan?", "lista",
          "Finalizados sin certificado, o certificados generados que no se han subido a STC.", Filtros("formacion"),
          CONTACTO + ["paquete", "programa", "grupo", "estado_formacion", "f_fin_form", "tiene_certificado",
                      "consolidado_cert", "f_cert", "hito"], ["f_fin_form"], parametro="certificado"),
    Atajo("alerta_nota", "Formación", "Alerta de nota (republicar)", "¿A quiénes hay que republicar la nota?", "lista",
          "Finalizados o certificados cuya nota publicada no es 5 (ALERTA - REPUBLICAR NOTA en el consolidado).",
          Filtros("formacion", cat={"alerta_nota": ["ALERTA - REPUBLICAR NOTA"]}),
          CONTACTO + ["programa", "grupo", "estado_formacion", "alerta_nota", "responsable_form"], ["grupo"]),
    Atajo("sin_actividad", "Formación", "Sin asistencia desde una fecha", "¿Quiénes no van a clase desde…?", "lista",
          "En formación sin terminar cuya última asistencia a clase es anterior a la fecha (o que nunca han asistido).",
          Filtros("formacion_curso"), _FORM, ["f_ult_asistencia"], parametro="fecha_asistencia"),
    # Orientación, remisión y encuestas
    Atajo("sin_remitir", "Orientación, remisión y encuestas", "Orientados sin remitir",
          "¿Quiénes están en el FCS y no en remisiones?", "lista",
          "Cédulas del Consolidado FCS que no aparecen en la hoja de remisiones (regla de «Orientados sin remitir»).",
          Filtros("todos", cat={"en_fcs": [SI], "en_remisiones": [NO]}), _ORI, ["f_orient"]),
    Atajo("listos_sin_encuesta", "Orientación, remisión y encuestas", "Listos para reportar sin encuesta",
          "¿Quiénes están listos para reportar y no tienen encuesta?", "lista",
          "Estado entregable «LISTO PARA REPORTAR» en el FCS y sin respuesta en las encuestas de mitigación.",
          Filtros("todos", cat={"estado_fcs": ["LISTO PARA REPORTAR"], "encuesta": [NO]}),
          _ORI, ["orientador"]),
    Atajo("con_encuesta", "Orientación, remisión y encuestas", "Encuestas por persona",
          "¿Quiénes tienen (o no) encuesta?", "lista",
          "Respuesta en las encuestas de mitigación (básico/JCO o especializado).", Filtros("orientados"),
          _ORI, ["encuesta", "orientador"], parametro="encuesta"),
    Atajo("campos_vacios", "Orientación, remisión y encuestas", "Campos vacíos en el FCS",
          "¿Quiénes tienen campos vacíos en el FCS?", "lista",
          "Columnas A a CE del Consolidado FCS sin diligenciar (sin contar G y H, que pueden quedar vacías).",
          Filtros("todos", rango={"n_campos_vacios": (1, 80)}),
          CONTACTO + ["orientador", "n_campos_vacios", "campos_vacios"], ["n_campos_vacios"], False),
    Atajo("subsanaciones", "Orientación, remisión y encuestas", "Subsanaciones pendientes",
          "¿Qué subsanaciones de Kuepa empleo hay?", "lista",
          "Diferencias entre Kuepa empleo y el FCS (pestaña SUBSANACIONES_KUEPA_EMPLEO): dato a usar ← dato del FCS.",
          Filtros("todos", rango={"n_subsanaciones": (1, 1000)}),
          CONTACTO + ["orientador", "n_subsanaciones", "subsanaciones"], ["orientador"]),
    # Gestión del equipo
    Atajo("pendientes_gestor", "Gestión del equipo", "Pendientes por responsable",
          "¿Qué tiene pendiente cada verificador u orientador?", "lista",
          "Las 4 listas de «Gestión diaria» (sin verificar, verificados sin orientar, orientados sin inscribir e "
          "inscritos sin clases) con días hábiles y semáforo. Elige el semáforo; acota por responsable en «Más filtros».",
          Filtros("vivos"), _PEND, ["gestor_pendiente", "dias_habiles"], [True, False], parametro="semaforo"),
    Atajo("tiempos", "Gestión del equipo", "Tiempos por etapa", "¿Cuánto nos estamos demorando por etapa?", "tiempos",
          "Mediana y percentil 75 de días hábiles de lo completado, % dentro del plazo y en curso por semáforo, por "
          "etapa y paquete (igual que «Tiempos de gestión»).", Filtros("vivos")),
    Atajo("actividad", "Gestión del equipo", "Actividad diaria por responsable",
          "¿Cuántos efectivos hizo cada responsable?", "actividad",
          "Gestiones completadas por día hábil y por responsable en verificación, orientación, formación o encuestas "
          "(igual que «Gestión diaria»).", Filtros("todos"), parametro="actividad"),
    Atajo("hitos", "Gestión del equipo", "Pagos (hitos) contra la meta", "¿Cuántos van aprobados por pago?", "hitos",
          "Personas por hito y paquete (Pago 1, Pago 2, Pago 2.1… y En ruta), con el total aprobado y el % de la meta "
          "del programa.", Filtros("todos")),
    Atajo("matriz", "Gestión del equipo", "Documentos faltantes (matriz documental)",
          "¿Qué documentos le faltan a cada persona?", "lista",
          "Requisitos de la matriz documental que no están marcados como cargados, con el % de cumplimiento.",
          Filtros("todos", rango={"pct_matriz": (0, 99.9)}),
          CONTACTO + ["paquete", "orientador", "pct_matriz", "faltantes_matriz"], ["pct_matriz"]),
    # Cifras
    Atajo("resumen", "Cifras y tablas", "Resumen por mes, evento, gestor…", "Dame las cifras por…", "resumen",
          "Personas, embudo (sin gestión → certificados), logrados básico y especializado, pagos aprobados, pendientes "
          "vencidos, bajas y promedios de asistencia y plataforma, con fila de total.", Filtros("todos"), parametro="por"),
    Atajo("distribucion", "Cifras y tablas", "Distribución cruzada", "¿Cuántos hay de cada… por…?", "distribucion",
          "Conteo cruzado de dos dimensiones (p. ej. momento del proceso por mes de alta, o hito por paquete).",
          Filtros("todos"), parametro="dim"),
]
POR_CLAVE = {a.clave: a for a in ATAJOS}
