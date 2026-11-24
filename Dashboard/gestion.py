# gestion.py
"""Gestión diaria, alertas por tiempos y participantes por hito, a partir del Seguimiento General que reconstruye
el script (Seguimiento_general/) y se carga en BigQuery (tabla STC_3_0_V2_2026).

Todo es pandas puro (sin Streamlit) para poder probarlo; las vistas están en vistas_gestion.py.

Reglas (nov-2026):
  * Orientado = «Reporte» en FINALIZADO o FINALIZADO PENDIENTE X REMISIÓN.
  * Verificado = «Momento del proceso (Back UP)» entre 2.Verificado y 5.Certificado (tiene ID SIS).
  * Baja = «6.Baja»: no entra en las listas de pendientes ni en las alertas.
  * Días = días HÁBILES (lunes a viernes sin festivos de Colombia).
"""
from __future__ import annotations

import datetime as dt
import re

import numpy as np
import pandas as pd

FINALIZADOS = {"FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"}
FESTIVOS_CO = [
    "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03", "2026-05-01", "2026-05-18",
    "2026-06-08", "2026-06-15", "2026-06-29", "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12",
    "2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25", "2027-01-01", "2027-01-11",
]

# Plazos en días hábiles por etapa. Amarillo desde ALERTA_PCT del plazo; rojo al superarlo. Ajustables aquí.
UMBRALES = {
    "Verificación": 3,           # alta en el CRM → verificación de documentos
    "Orientación": 5,            # verificado → orientación finalizada
    "Inscripción a formación": 5,  # orientado (especializado) → primera clase
    "Formación": 30,             # primera clase → finalización
}
ALERTA_PCT = 0.8
ETAPAS = [  # (etapa, columna inicio, columna fin, paquetes a los que aplica)
    ("Verificación", "_f_alta", "_f_verif", {"BÁSICO", "ESPECIALIZADO", ""}),
    ("Orientación", "_f_verif", "_f_orient", {"BÁSICO", "ESPECIALIZADO", ""}),
    ("Inscripción a formación", "_f_orient", "_f_clases", {"ESPECIALIZADO"}),
    ("Formación", "_f_clases", "_f_fin", {"ESPECIALIZADO"}),
]
SEMAFORO = ["🔴 Vencido", "🟡 Por vencer", "🟢 En plazo"]
DIAS_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def etiqueta_dia(d: dt.date) -> str:
    return f"{DIAS_ES[d.weekday()]} {d:%d/%m}"


def _sin_decimal(s: pd.Series) -> pd.Series:
    """«3014938801.0» → «3014938801» (teléfonos y cédulas que llegan como número)."""
    return _texto(s).str.replace(r"\.0+$", "", regex=True)


# ------------------------------------------------------------------ utilidades
def _texto(s: pd.Series) -> pd.Series:
    return s.astype("string").fillna("").str.strip()


def _col(df: pd.DataFrame, nombre: str) -> pd.Series:
    return df[nombre] if nombre in df.columns else pd.Series([""] * len(df), index=df.index)


def fecha(s: pd.Series) -> pd.Series:
    """Fechas en cualquier formato de la hoja/BigQuery (2026-07-09, 09/07/2026, …) → datetime sin hora."""
    t = _texto(s).replace({"--": "", "nan": "", "NaT": "", "None": ""})
    iso = pd.to_datetime(t.where(t.str.match(r"^\d{4}-\d{2}-\d{2}")), errors="coerce", format="mixed")
    dmy = pd.to_datetime(t.where(~t.str.match(r"^\d{4}-\d{2}-\d{2}")), errors="coerce", dayfirst=True,
                         format="mixed")
    out = iso.fillna(dmy)
    out = out.where((out.dt.year >= 2024) & (out.dt.year <= 2030))  # descarta errores de digitación (0206…)
    return out.dt.normalize()


def dias_habiles(desde: pd.Series, hasta: pd.Series | dt.date) -> pd.Series:
    """Días hábiles entre dos fechas (sin contar el día de inicio). NaN si falta alguna."""
    d = pd.to_datetime(desde)
    h = pd.Series(pd.Timestamp(hasta), index=d.index) if not isinstance(hasta, pd.Series) else pd.to_datetime(hasta)
    ok = d.notna() & h.notna() & (h >= d)
    res = pd.Series(np.nan, index=d.index)
    if ok.any():
        res[ok] = np.busday_count(d[ok].values.astype("datetime64[D]"), h[ok].values.astype("datetime64[D]"),
                                  holidays=FESTIVOS_CO)
    return res


def dia_habil_anterior(d: dt.date) -> dt.date:
    return pd.Timestamp(np.busday_offset(np.datetime64(d), -1, roll="backward", holidays=FESTIVOS_CO)).date()


def ultimos_habiles(hasta: dt.date, n: int) -> list[dt.date]:
    fin = np.busday_offset(np.datetime64(hasta), 0, roll="backward", holidays=FESTIVOS_CO)
    return [pd.Timestamp(np.busday_offset(fin, -i, holidays=FESTIVOS_CO)).date() for i in range(n - 1, -1, -1)]


def nivel(bt: pd.Series) -> pd.Series:
    """«3.Orientado» → 3; vacío → -1."""
    return pd.to_numeric(_texto(bt).str.extract(r"^(\d)")[0], errors="coerce").fillna(-1).astype(int)


def semaforo(dias: pd.Series, umbral: float) -> pd.Series:
    return pd.Series(np.select([dias > umbral, dias >= umbral * ALERTA_PCT], SEMAFORO[:2], SEMAFORO[2]),
                     index=dias.index).where(dias.notna(), "")


# ------------------------------------------------------------------ preparación
def preparar(general: pd.DataFrame) -> pd.DataFrame:
    df = general.copy()
    df["_paq"] = _texto(_col(df, "Paquete")).str.upper()
    df["_nivel"] = nivel(_col(df, "Momento del proceso (Back UP)"))
    df["_baja"] = df["_nivel"].eq(6)
    df["_verificado"] = df["_nivel"].between(2, 5)
    df["_orientado"] = _texto(_col(df, "Reporte")).isin(FINALIZADOS)
    df["_estado_f"] = _texto(_col(df, "Estado de la formación")).str.upper()
    for destino, origen in (("_f_alta", "Fecha de alta"), ("_f_verif", "Fecha"), ("_f_orient", "Fecha Orientación"),
                            ("_f_clases", "Fecha clases"), ("_f_fin", "Fecha finalización")):
        df[destino] = fecha(_col(df, origen))
    df["_hito"] = _texto(_col(df, "Hito"))
    return df


def _ficha(df: pd.DataFrame, gestor: str, desde: str, umbral_etapa: str, hoy: dt.date) -> pd.DataFrame:
    dias = dias_habiles(df[desde], hoy)
    out = pd.DataFrame({
        "Cédula": _sin_decimal(_col(df, "CC Prospecto")), "Nombre": _col(df, "Nombre completo"),
        "Teléfono": _sin_decimal(_col(df, "Teléfono")), "Correo": _col(df, "Correo"), "Paquete": df["_paq"].str.title(),
        "Evento/Base": _col(df, "Evento/Base"), "Gestor": _texto(_col(df, gestor)),
        "Momento del proceso": _col(df, "Momento del proceso (Back UP)"),
        "Estado formación": _col(df, "Estado de la formación"),
        "Esperando desde": df[desde].dt.date, "Días hábiles": dias,
        "Semáforo": semaforo(dias, UMBRALES[umbral_etapa]),
    })
    # Primero quienes van más avanzados en el proceso (p. ej. 1.En verificación antes que 0.Sin gestión), y dentro
    # de cada grupo los que más llevan esperando.
    out["_n"] = df["_nivel"].values
    out = out.sort_values(["_n", "Días hábiles"], ascending=[False, False], na_position="last")
    return out.drop(columns="_n").reset_index(drop=True)


def listas_pendientes(prep: pd.DataFrame, hoy: dt.date) -> dict[str, pd.DataFrame]:
    """Las 4 listas de gestión, sin bajas. «Días hábiles» = tiempo esperando la siguiente etapa."""
    vivos = prep[~prep["_baja"]]
    sin_verificar = vivos[vivos["_nivel"].between(0, 1)]
    verif_sin_orientar = vivos[vivos["_verificado"] & ~vivos["_orientado"]].copy()
    verif_sin_orientar["_desde"] = verif_sin_orientar["_f_verif"].fillna(verif_sin_orientar["_f_alta"])
    orientados = vivos[vivos["_orientado"]]
    return {
        "Sin verificar": _ficha(sin_verificar, "Verificador", "_f_alta", "Verificación", hoy),
        "Verificados sin orientar": _ficha(verif_sin_orientar, "Orientador", "_desde", "Orientación", hoy),
        "Orientados SIN INSCRIBIR": _ficha(orientados[orientados["_estado_f"].eq("SIN INSCRIBIR")], "Orientador",
                                           "_f_orient", "Inscripción a formación", hoy),
        "Orientados INSCRITOS": _ficha(orientados[orientados["_estado_f"].eq("INSCRITO")], "Orientador",
                                       "_f_orient", "Inscripción a formación", hoy),
    }


# ------------------------------------------------------------------ gestión diaria
def _detectar(df: pd.DataFrame, *patrones: str) -> str | None:
    for p in patrones:
        for c in df.columns:
            if re.search(p, str(c), flags=re.I):
                return c
    return None


def actividad(prep: pd.DataFrame, fuentes: dict) -> pd.DataFrame:
    """Registros de gestión con su fecha y gestor: columnas Proceso, Fecha, Gestor, Cédula."""
    partes = []
    ver = fuentes.get("verificacion")
    c_f = _detectar(ver, r"^fecha$") if ver is not None else None
    c_g = _detectar(ver, r"^verificador$") if ver is not None else None
    c_d = _detectar(ver, r"n[uú]mero documento") if ver is not None else None
    if c_f and c_g:
        partes.append(pd.DataFrame({"Proceso": "Verificación", "Fecha": fecha(ver[c_f]),
                                    "Gestor": _texto(ver[c_g]).str.title(),
                                    "Cédula": ver[c_d] if c_d else ""}))
    else:  # respaldo: la fecha de verificación del seguimiento
        v = prep[prep["_verificado"]]
        partes.append(pd.DataFrame({"Proceso": "Verificación", "Fecha": v["_f_verif"],
                                    "Gestor": _texto(_col(v, "Verificador")).str.title(),
                                    "Cédula": _col(v, "CC Prospecto")}))
    o = prep[prep["_orientado"]]
    partes.append(pd.DataFrame({"Proceso": "Orientación", "Fecha": o["_f_orient"],
                                "Gestor": _texto(_col(o, "Orientador")).str.title(), "Cédula": _col(o, "CC Prospecto")}))
    form = fuentes.get("formacion_consolidado")
    c_e = _detectar(form, r"estado de la formaci") if form is not None else None
    c_fin = _detectar(form, r"fecha de finalizaci") if form is not None else None
    c_r = _detectar(form, r"^responsable$") if form is not None else None
    c_doc = _detectar(form, r"no\. documento|^documento|c[eé]dula") if form is not None else None
    if c_e and c_fin:
        fin = form[_texto(form[c_e]).str.upper().isin(["FINALIZADO", "CERTIFICADO"])]
        partes.append(pd.DataFrame({"Proceso": "Formación", "Fecha": fecha(fin[c_fin]),
                                    "Gestor": _texto(fin[c_r]).str.title() if c_r else "",
                                    "Cédula": fin[c_doc] if c_doc else ""}))
    else:
        fz = prep[prep["_estado_f"].isin(["FINALIZADO", "CERTIFICADO"])]
        partes.append(pd.DataFrame({"Proceso": "Formación", "Fecha": fz["_f_fin"], "Gestor": "",
                                    "Cédula": _col(fz, "CC Prospecto")}))
    for clave, etiqueta in (("encuesta_basico_jco", "Básico / JCO"), ("encuesta_especializado", "Especializado")):
        e = fuentes.get(clave)
        if e is None or e.empty:
            continue
        c = _detectar(e, r"marca temporal|timestamp", r"^fecha")
        if c:
            partes.append(pd.DataFrame({"Proceso": "Encuestas", "Fecha": fecha(e[c]), "Gestor": etiqueta,
                                        "Cédula": _col(e, "CEDULA")}))
    act = pd.concat(partes, ignore_index=True)
    act["Gestor"] = act["Gestor"].replace({"": "(sin gestor)", "<NA>": "(sin gestor)"}).fillna("(sin gestor)")
    return act.dropna(subset=["Fecha"])


def resumen_dia(act: pd.DataFrame, dia: dt.date) -> pd.DataFrame:
    """Por proceso: gestiones del día, del día hábil anterior y diferencia."""
    anterior = dia_habil_anterior(dia)
    filas = []
    for p in ["Verificación", "Orientación", "Formación", "Encuestas"]:
        a = act[act["Proceso"].eq(p)]
        hoy_n = int((a["Fecha"].dt.date == dia).sum())
        ant_n = int((a["Fecha"].dt.date == anterior).sum())
        filas.append({"Proceso": p, "Día": hoy_n, "Día hábil anterior": ant_n, "Diferencia": hoy_n - ant_n})
    return pd.DataFrame(filas)


def matriz_gestores(act: pd.DataFrame, proceso: str, dias: list[dt.date]) -> pd.DataFrame:
    """Gestores × últimos días hábiles, con total del periodo; los que más gestionaron arriba."""
    a = act[act["Proceso"].eq(proceso) & act["Fecha"].dt.date.isin(dias)]
    if a.empty:
        return pd.DataFrame(columns=["Gestor"] + [etiqueta_dia(d) for d in dias] + ["Total"])
    t = (a.assign(D=a["Fecha"].dt.date).pivot_table(index="Gestor", columns="D", values="Proceso", aggfunc="size",
                                                    fill_value=0).reindex(columns=dias, fill_value=0))
    t.columns = [etiqueta_dia(pd.Timestamp(d).date()) for d in t.columns]
    t["Total"] = t.sum(axis=1)
    t = t.sort_values("Total", ascending=False)
    total = pd.DataFrame([t.sum()], index=["TOTAL"])
    return pd.concat([t, total]).reset_index().rename(columns={"index": "Gestor"})


# ------------------------------------------------------------------ tiempos de gestión
def tiempos(prep: pd.DataFrame, hoy: dt.date) -> pd.DataFrame:
    """Una fila por persona y etapa: tiempo que tomó (completada) o que lleva esperando (en curso)."""
    vivos = prep[~prep["_baja"]]
    pendiente = {
        # Solo «1.En verificación» (ya entregó documentos); «0.Sin gestión» es embudo comercial, no demora del equipo.
        "Verificación": vivos["_nivel"].eq(1),
        "Orientación": vivos["_verificado"] & ~vivos["_orientado"],
        "Inscripción a formación": vivos["_orientado"] & vivos["_estado_f"].isin(["SIN INSCRIBIR", "INSCRITO", ""])
        & vivos["_f_clases"].isna(),
        "Formación": vivos["_estado_f"].eq("EN CURSO") & vivos["_f_fin"].isna(),
    }
    gestor = {"Verificación": "Verificador", "Orientación": "Orientador", "Inscripción a formación": "Orientador",
              "Formación": "Orientador"}  # en formación el responsable está en el consolidado; aquí, quien orientó
    filas = []
    for etapa, ini, fin, paquetes in ETAPAS:
        d = vivos[vivos["_paq"].isin(paquetes) & vivos[ini].notna()]
        completada = d[fin].notna() & (d[fin] >= d[ini])
        en_curso = pendiente[etapa].reindex(d.index, fill_value=False) & ~completada
        for estado, m, hasta in (("Completada", completada, d[fin]), ("En curso", en_curso, hoy)):
            x = d[m]
            if x.empty:
                continue
            dias = dias_habiles(x[ini], hasta if isinstance(hasta, dt.date) else hasta[m])
            filas.append(pd.DataFrame({
                "Etapa": etapa, "Estado": estado, "Paquete": x["_paq"].str.title().replace("", "Sin paquete"),
                "Cédula": _sin_decimal(_col(x, "CC Prospecto")), "Nombre": _col(x, "Nombre completo"),
                "Gestor": _texto(_col(x, gestor[etapa])).str.title().replace("", "(sin gestor)"),
                "Inicio": x[ini].dt.date, "Fin": x[fin].dt.date if estado == "Completada" else pd.NaT,
                "Días hábiles": dias, "Plazo": UMBRALES[etapa],
                "Semáforo": semaforo(dias, UMBRALES[etapa]),
            }))
    cols = ["Etapa", "Estado", "Paquete", "Cédula", "Nombre", "Gestor", "Inicio", "Fin", "Días hábiles", "Plazo",
            "Semáforo"]
    return pd.concat(filas, ignore_index=True) if filas else pd.DataFrame(columns=cols)


def resumen_tiempos(t: pd.DataFrame) -> pd.DataFrame:
    """Por etapa y paquete: mediana y percentil 75 de lo completado, % dentro del plazo y en curso por semáforo."""
    filas = []
    orden = [e[0] for e in ETAPAS]
    for (etapa, paq), g in t.groupby(["Etapa", "Paquete"]):
        c = g[g["Estado"].eq("Completada")]["Días hábiles"]
        e = g[g["Estado"].eq("En curso")]
        filas.append({
            "Etapa": etapa, "Paquete": paq, "Plazo (días háb.)": UMBRALES[etapa],
            "Completadas": len(c), "Mediana (días)": c.median() if len(c) else np.nan,
            "P75 (días)": c.quantile(.75) if len(c) else np.nan,
            "% en plazo": (c <= UMBRALES[etapa]).mean() * 100 if len(c) else np.nan,
            "En curso": len(e), "🔴 Vencidos": int(e["Semáforo"].eq(SEMAFORO[0]).sum()),
            "🟡 Por vencer": int(e["Semáforo"].eq(SEMAFORO[1]).sum()),
            "🟢 En plazo": int(e["Semáforo"].eq(SEMAFORO[2]).sum()),
        })
    r = pd.DataFrame(filas)
    if r.empty:
        return r
    r["_o"] = r["Etapa"].map({e: i for i, e in enumerate(orden)})
    return r.sort_values(["_o", "Paquete"]).drop(columns="_o").reset_index(drop=True)


def tiempos_por_gestor(t: pd.DataFrame, etapa: str) -> pd.DataFrame:
    g = t[t["Etapa"].eq(etapa)]
    if g.empty:
        return pd.DataFrame()
    c = g[g["Estado"].eq("Completada")].groupby("Gestor")["Días hábiles"].agg(["count", "median"])
    e = g[g["Estado"].eq("En curso")].groupby("Gestor")["Semáforo"].agg(
        en_curso="size", vencidos=lambda s: int(s.eq(SEMAFORO[0]).sum()))
    r = c.join(e, how="outer").fillna({"count": 0, "en_curso": 0, "vencidos": 0}).reset_index()
    r.columns = ["Gestor", "Completadas", "Mediana (días)", "En curso", "🔴 Vencidos"]
    return r.sort_values(["🔴 Vencidos", "En curso"], ascending=False)


# ------------------------------------------------------------------ hitos
def _orden_hito(h: str) -> tuple:
    n = re.findall(r"\d+", h)
    return (0, *map(int, n)) if h.startswith("Pago") else (1,)


def matriz_hitos(prep: pd.DataFrame, meta_total: int) -> pd.DataFrame:
    """Hito × paquete: Pago 1, Pago 2, Pago 2.1, … (presentados y aprobados por la SDDE) y En ruta."""
    d = prep[prep["_hito"].ne("")]
    if d.empty:
        return pd.DataFrame()
    paq = d["_paq"].replace({"": "SIN PAQUETE"}).str.title()
    t = pd.crosstab(d["_hito"], paq)
    t.columns.name = None
    for c in ("Básico", "Especializado"):
        if c not in t:
            t[c] = 0
    otras = [c for c in t.columns if c not in ("Básico", "Especializado")]
    t = t[["Básico", "Especializado"] + otras]
    t["Total"] = t.sum(axis=1)
    t = t.loc[sorted(t.index, key=_orden_hito)]
    pagos = t[[i.startswith("Pago") for i in t.index]]
    filas = [t.loc[[i]] for i in pagos.index]
    sub = pd.DataFrame([pagos.sum()], index=["Total aprobados"])
    resto = [t.loc[[i]] for i in t.index if not i.startswith("Pago")]
    out = pd.concat(filas + [sub] + resto)
    out["% de la meta"] = (out["Total"] / meta_total * 100).round(1) if meta_total else np.nan
    return out.reset_index().rename(columns={"index": "Hito", "_hito": "Hito"})
