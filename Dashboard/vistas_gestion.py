# vistas_gestion.py
"""Vistas de Streamlit para: Gestión diaria (pestaña nueva), Tiempos de gestión (pestaña de alertas) y
Participantes por hito (Overview). La lógica está en gestion.py."""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd
import plotly.express as px
import streamlit as st

import gestion as G
from column_mapping import META_TOTAL_PROGRAMA

NARANJA, ROJO, GRIS, OSCURO = "#FD531E", "#821F0D", "#656A71", "#292929"
COLOR_SEMAFORO = {G.SEMAFORO[0]: "#C62828", G.SEMAFORO[1]: "#F9A825", G.SEMAFORO[2]: "#2E7D32"}
PROCESOS = ["Verificación", "Orientación", "Formación", "Encuestas"]


def _tarjeta(valor, etiqueta, sub="", color=GRIS):
    st.markdown(
        f'<div style="background:#FFFFFF;border-left:4px solid {color};padding:12px 14px;border-radius:8px;'
        f'margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,0.08);">'
        f'<div style="font-size:12px;color:{GRIS};text-transform:uppercase;letter-spacing:.5px;">{etiqueta}</div>'
        f'<div style="font-size:26px;color:{OSCURO};font-weight:700;margin-top:2px;">{valor}</div>'
        f'<div style="font-size:12px;color:{GRIS};">{sub}</div></div>', unsafe_allow_html=True)


def _excel(hojas: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for nombre, df in hojas.items():
            df.to_excel(xw, sheet_name=nombre[:31], index=False)
    return buf.getvalue()


@st.cache_data(ttl=600, show_spinner=False)
def _preparado(general: pd.DataFrame) -> pd.DataFrame:
    return G.preparar(general)


# ------------------------------------------------------------------ Gestión diaria
def render_gestion_diaria(fuentes: dict, form_cons: pd.DataFrame | None = None) -> None:
    st.subheader("📆 Gestión diaria")
    st.caption("Lo que hizo cada gestor por día en Verificación, Orientación, Formación y Encuestas, y las listas de "
               "personas que esperan la siguiente etapa. Datos del Seguimiento General (se reconstruye L-V de 6 a. m. "
               "a 6 p. m. cada 2 horas). Días = días hábiles.")
    prep = _preparado(fuentes["general"])
    hoy = dt.date.today()
    fuentes_act = dict(fuentes)
    if form_cons is not None:
        fuentes_act["formacion_consolidado"] = form_cons
    act = G.actividad(prep, fuentes_act)

    ultimo = act["Fecha"].max().date() if not act.empty else hoy
    c1, c2 = st.columns([1, 3])
    dia = c1.date_input("Día", value=min(hoy, ultimo) if ultimo else hoy, max_value=hoy, format="DD/MM/YYYY",
                        key="gd_dia")
    c2.markdown(f"<div style='margin-top:32px;color:{GRIS}'>Comparado con el día hábil anterior: "
                f"<b>{G.dia_habil_anterior(dia):%d/%m/%Y}</b></div>", unsafe_allow_html=True)

    res = G.resumen_dia(act, dia)
    cols = st.columns(4)
    for col, (_, fila) in zip(cols, res.iterrows()):
        dif = fila["Diferencia"]
        signo = "▲" if dif > 0 else "▼" if dif < 0 else "="
        with col:
            _tarjeta(int(fila["Día"]), fila["Proceso"], f"{signo} {abs(dif)} vs. día hábil anterior "
                     f"({int(fila['Día hábil anterior'])})", NARANJA if dif >= 0 else ROJO)

    st.markdown("#### Gestión por gestor · últimos 10 días hábiles")
    dias = G.ultimos_habiles(dia, 10)
    pestanas = st.tabs(PROCESOS)
    for tab, proceso in zip(pestanas, PROCESOS):
        with tab:
            m = G.matriz_gestores(act, proceso, dias)
            if m.empty or m["Total"].sum() == 0:
                st.info(f"Sin registros de {proceso.lower()} en esos días.")
                continue
            st.dataframe(m, use_container_width=True, hide_index=True)
            serie = act[act["Proceso"].eq(proceso) & act["Fecha"].dt.date.isin(dias)]
            serie = serie.groupby(serie["Fecha"].dt.date).size().reindex(dias, fill_value=0).reset_index()
            serie.columns = ["Día", "Gestiones"]
            serie["Día"] = [G.etiqueta_dia(d) for d in serie["Día"]]
            fig = px.bar(serie, x="Día", y="Gestiones", text="Gestiones")
            fig.update_traces(marker_color=NARANJA, textposition="outside", cliponaxis=False)
            fig.update_layout(height=260, margin=dict(t=10, b=10, l=10, r=10), xaxis=dict(type="category",
                              title=None))
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("#### Personas pendientes por etapa (sin bajas)")
    listas = G.listas_pendientes(prep, hoy)
    cols = st.columns(4)
    for col, (nombre, df) in zip(cols, listas.items()):
        vencidos = int(df["Semáforo"].eq(G.SEMAFORO[0]).sum())
        with col:
            _tarjeta(len(df), nombre, f"{vencidos} vencidos", ROJO if vencidos else GRIS)

    f1, f2, f3 = st.columns(3)
    paquetes = f1.multiselect("Paquete", ["Básico", "Especializado"], key="gd_paq")
    semaforos = f2.multiselect("Semáforo", G.SEMAFORO, key="gd_sem")
    texto = f3.text_input("Buscar cédula o nombre", key="gd_buscar")

    def filtrar(df):
        if paquetes:
            df = df[df["Paquete"].isin(paquetes)]
        if semaforos:
            df = df[df["Semáforo"].isin(semaforos)]
        if texto:
            t = texto.strip().lower()
            df = df[df["Cédula"].astype(str).str.contains(t, na=False)
                    | df["Nombre"].astype(str).str.lower().str.contains(t, na=False)]
        return df

    filtradas = {n: filtrar(df) for n, df in listas.items()}
    for tab, (nombre, df) in zip(st.tabs([f"{n} ({len(d)})" for n, d in filtradas.items()]), filtradas.items()):
        with tab:
            ayuda = {
                "Sin verificar": "0.Sin gestión y 1.En verificación. Días desde el alta en el CRM; plazo "
                                 f"{G.UMBRALES['Verificación']} días hábiles.",
                "Verificados sin orientar": "Verificados (con ID SIS) cuyo reporte no está FINALIZADO ni FINALIZADO "
                                            f"PENDIENTE X REMISIÓN. Plazo {G.UMBRALES['Orientación']} días hábiles.",
                "Orientados SIN INSCRIBIR": "Orientación finalizada y formación SIN INSCRIBIR. Días desde la "
                                            f"orientación; plazo {G.UMBRALES['Inscripción a formación']} días hábiles.",
                "Orientados INSCRITOS": "Orientación finalizada e inscritos en formación, sin clases aún. Días desde "
                                        "la orientación.",
            }[nombre]
            st.caption(ayuda)
            if nombre == "Sin verificar" and not df.empty:
                st.caption(" · ".join(f"{k}: {v}" for k, v in df["Momento del proceso"].value_counts().items()))
            st.dataframe(df, use_container_width=True, hide_index=True, height=420, column_config={
                "Días hábiles": st.column_config.NumberColumn(format="%d"),
                "Esperando desde": st.column_config.DateColumn(format="DD/MM/YYYY")})
    st.download_button("⬇️ Descargar las 4 listas (Excel)", _excel(filtradas),
                       f"pendientes_stc_{hoy:%Y%m%d}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="gd_excel")


# ------------------------------------------------------------------ Tiempos de gestión
def render_tiempos(general: pd.DataFrame) -> None:
    st.subheader("⏱️ Tiempos de gestión")
    plazos = " · ".join(f"{e}: {d} días" for e, d in G.UMBRALES.items())
    st.caption(f"Plazos en días hábiles — {plazos}. 🟡 desde el {int(G.ALERTA_PCT * 100)} % del plazo, 🔴 al "
               "superarlo. Básicos: Verificación y Orientación. Especializados: además Inscripción a formación "
               "y Formación. Sin bajas.")
    prep = _preparado(general)
    t = G.tiempos(prep, dt.date.today())
    if t.empty:
        st.info("No hay fechas suficientes para calcular tiempos.")
        return

    c1, c2 = st.columns([1, 3])
    paq = c1.radio("Paquete", ["Todos", "Básico", "Especializado"], horizontal=False, key="tg_paq")
    tt = t if paq == "Todos" else t[t["Paquete"].eq(paq)]

    en_curso = tt[tt["Estado"].eq("En curso")]
    with c2:
        cols = st.columns(len(G.ETAPAS))
        for col, (etapa, *_r) in zip(cols, G.ETAPAS):
            e = en_curso[en_curso["Etapa"].eq(etapa)]
            v = int(e["Semáforo"].eq(G.SEMAFORO[0]).sum())
            with col:
                _tarjeta(v, f"{etapa} · vencidos", f"{len(e)} en curso · {int(e['Semáforo'].eq(G.SEMAFORO[1]).sum())}"
                         " por vencer", ROJO if v else GRIS)

    st.markdown("#### Resumen por etapa y paquete")
    st.dataframe(G.resumen_tiempos(tt), use_container_width=True, hide_index=True, column_config={
        "Mediana (días)": st.column_config.NumberColumn(format="%.1f"),
        "P75 (días)": st.column_config.NumberColumn(format="%.1f"),
        "% en plazo": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)})

    izq, der = st.columns(2)
    with izq:
        st.markdown("##### Días que tomó cada etapa (completadas)")
        comp = tt[tt["Estado"].eq("Completada")]
        if not comp.empty:
            fig = px.box(comp, x="Etapa", y="Días hábiles", color="Paquete", points=False,
                         category_orders={"Etapa": [e[0] for e in G.ETAPAS]},
                         color_discrete_map={"Básico": GRIS, "Especializado": NARANJA})
            fig.update_layout(height=360, margin=dict(t=10, b=10), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)
    with der:
        st.markdown("##### En curso por semáforo")
        if not en_curso.empty:
            s = en_curso.groupby(["Etapa", "Semáforo"]).size().reset_index(name="Personas")
            fig = px.bar(s, y="Etapa", x="Personas", color="Semáforo", orientation="h",
                         color_discrete_map=COLOR_SEMAFORO, category_orders={"Semáforo": G.SEMAFORO,
                                                                             "Etapa": [e[0] for e in G.ETAPAS]})
            fig.update_layout(height=360, margin=dict(t=10, b=10), legend=dict(orientation="h", y=1.1),
                              barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Por gestor")
    etapa = st.selectbox("Etapa", [e[0] for e in G.ETAPAS], key="tg_etapa")
    st.dataframe(G.tiempos_por_gestor(tt, etapa), use_container_width=True, hide_index=True,
                 column_config={"Mediana (días)": st.column_config.NumberColumn(format="%.1f")})

    st.markdown("#### Personas fuera de plazo o por vencer")
    alerta = en_curso[en_curso["Semáforo"].isin(G.SEMAFORO[:2])].sort_values("Días hábiles", ascending=False)
    st.dataframe(alerta.drop(columns=["Estado", "Fin"]), use_container_width=True, hide_index=True, height=380,
                 column_config={"Días hábiles": st.column_config.NumberColumn(format="%d"),
                                "Inicio": st.column_config.DateColumn(format="DD/MM/YYYY")})
    st.download_button("⬇️ Descargar alertas (Excel)", _excel({"Alertas": alerta, "Tiempos": tt}),
                       f"alertas_tiempos_stc_{dt.date.today():%Y%m%d}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="tg_excel")


# ------------------------------------------------------------------ Hitos (Overview)
def render_hitos(general: pd.DataFrame) -> None:
    prep = _preparado(general)
    m = G.matriz_hitos(prep, META_TOTAL_PROGRAMA)
    if m.empty:
        st.info("Aún no hay hitos registrados.")
        return
    st.caption("Pago N = aprobado por la SDDE en ese pago (2.1 y 3.1 son sub-entregas). En ruta = sin aprobación "
               "y con proceso activo (entre En verificación y Certificado). % sobre la meta del programa "
               f"({META_TOTAL_PROGRAMA:,}).".replace(",", "."))
    izq, der = st.columns([1.3, 1])
    with izq:
        st.dataframe(m, use_container_width=True, hide_index=True, column_config={
            "% de la meta": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)})
    with der:
        b = m[~m["Hito"].str.startswith("Total")].melt(id_vars="Hito", value_vars=["Básico", "Especializado"],
                                                        var_name="Paquete", value_name="Personas")
        fig = px.bar(b, x="Hito", y="Personas", color="Paquete", text="Personas", barmode="stack",
                     color_discrete_map={"Básico": GRIS, "Especializado": NARANJA})
        fig.update_traces(textposition="inside")
        fig.update_layout(height=330, margin=dict(t=10, b=10), legend=dict(orientation="h", y=1.12),
                          xaxis=dict(type="category"))
        st.plotly_chart(fig, use_container_width=True)
