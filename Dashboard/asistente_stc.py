"""
Asistente de datos del dashboard STC 3.0 (nov-2026): botón flotante «Asistente de datos» → ventana con
  * Consultas frecuentes: conversación guiada (eliges la consulta, ajustas el dato que pide y, si quieres, más filtros).
  * Constructor: eliges qué quieres (lista, resumen o distribución) y combinas filtros.
Cada respuesta trae la cifra, una vista previa y el CSV (con documento, nombre, teléfono y correo). La lógica (tabla
por persona, filtros, tablas, CSV) está en consultas_stc.py; aquí solo la interfaz. Sin IA.
Vista previa local con datos sintéticos: STC_ASISTENTE_DEMO=1 streamlit run app.py
Compatible con Streamlit 1.38 (la versión fijada en Dashboard/requirements.txt): sin pills, segmented_control ni
iconos en botones, que llegaron en versiones posteriores.
"""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import streamlit as st

import consultas_stc as Q
import gestion as G

VISTA_PREVIA = 300
# El botón se fija abajo a la derecha. Streamlit 1.38 no pone la clase .st-key-<key> en los widgets: se ubica como el
# elemento que sigue al ancla #asistente-stc-ancla (y en versiones nuevas también por .st-key-asistente_stc_fab).
_FAB = (".st-key-asistente_stc_fab, "
        "div.element-container:has(#asistente-stc-ancla) + div.element-container, "
        "div[data-testid='stElementContainer']:has(#asistente-stc-ancla) + div[data-testid='stElementContainer']")
CSS = f"""<style>
{_FAB} {{ position: fixed; right: 24px; bottom: 24px; left: auto !important; z-index: 999990;
    width: max-content !important; }}
div.element-container:has(#asistente-stc-ancla),
div[data-testid='stElementContainer']:has(#asistente-stc-ancla) {{ display: none; }}
{_FAB.replace(", ", " div, ")} div {{ width: auto !important; }}
{_FAB.replace(", ", " button, ")} button {{ border-radius: 999px; padding: .65rem 1.25rem; font-weight: 600;
    background: #FD531E; border-color: #FD531E; color: #fff; box-shadow: 0 8px 22px rgba(0,0,0,.28); }}
@media (max-width: 640px) {{ {_FAB} {{ right: 12px; bottom: 12px; }} }}
</style><div id="asistente-stc-ancla"></div>"""


def boton_flotante() -> None:
    """Se llama una vez en app.py (arriba de las pestañas): el botón queda fijo abajo a la derecha."""
    st.markdown(CSS, unsafe_allow_html=True)
    if st.button("💬 Asistente de datos", key="asistente_stc_fab", type="primary",
                 help="Consultas puntuales con cifra y CSV"):
        dialogo()


# ------------------------------------------------------------------ datos
def _hoy() -> dt.date:
    return dt.date(2026, 11, 26) if os.getenv("STC_ASISTENTE_DEMO") else dt.date.today()


@st.cache_data(ttl=600, show_spinner="Preparando los datos del asistente…")
def _datos(dia: dt.date) -> tuple[pd.DataFrame, dict, list[str]]:
    """(tabla por persona, fuentes crudas, avisos). Usa las mismas cargas del dashboard (con su caché)."""
    if os.getenv("STC_ASISTENTE_DEMO"):
        import demo_stc
        f = demo_stc.fuentes()
        return Q.construir_base(f, dia), f, ["Datos de demostración (sintéticos)."]
    from analitica import cargar_formacion_consolidado_cache, cargar_todo_cache
    from cargar_datos import cargar_fuente
    f, avisos = dict(cargar_todo_cache()), []
    extra = {"formacion_consolidado": cargar_formacion_consolidado_cache,
             "subsanaciones": lambda: cargar_fuente("subsanaciones")[0],
             "matriz_documental": lambda: cargar_fuente("matriz_documental")[0]}
    for clave, cargar in extra.items():
        try:
            f[clave] = cargar()
        except Exception as e:  # noqa: BLE001 -- una fuente caída no tumba el asistente
            f[clave] = None
            avisos.append(f"No se pudo leer «{clave}» ({type(e).__name__}): sus columnas quedan vacías.")
    return Q.construir_base(f, dia), f, avisos


# ------------------------------------------------------------------ ventana
@st.dialog("Asistente de datos · STC 3.0", width="large")
def dialogo() -> None:
    hoy = _hoy()
    try:
        b, fuentes, avisos = _datos(hoy)
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudieron cargar los datos ({type(e).__name__}: {e}).", icon=":material/error:")
        return
    for a in avisos:
        st.caption(f":material/info: {a}")
    modo = st.radio("Modo", ["Consultas frecuentes", "Constructor"], key="asis_stc_modo", horizontal=True,
                    label_visibility="collapsed")
    if modo == "Constructor":
        _constructor(b, fuentes, hoy)
    else:
        _conversacion(b, fuentes, hoy)


def _elegir(clave_widget: str) -> None:
    for g in {a.grupo for a in Q.ATAJOS}:
        k = f"asis_stc_pill_{g}"
        if k != clave_widget:
            st.session_state[k] = None
    st.session_state["asis_stc_atajo"] = st.session_state.get(clave_widget)


def _conversacion(b: pd.DataFrame, fuentes: dict, hoy: dt.date) -> None:
    titulos = {a.titulo: a.clave for a in Q.ATAJOS}
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        st.markdown("Hola. ¿Qué necesitas? Elige una consulta: te digo la cifra y te dejo el CSV. Después puedes "
                    "acotarla con más filtros (paquete, JCO, evento, mes de alta, gestor, programa, fechas…).")
        for grupo in dict.fromkeys(a.grupo for a in Q.ATAJOS):
            k = f"asis_stc_pill_{grupo}"
            st.radio(f"**{grupo}**", [a.titulo for a in Q.ATAJOS if a.grupo == grupo], index=None, key=k,
                     horizontal=True, on_change=_elegir, args=(k,))
    clave = titulos.get(st.session_state.get("asis_stc_atajo") or "")
    if not clave:
        return
    a = Q.POR_CLAVE[clave]
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(a.pregunta)
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        st.markdown(f"**{a.titulo}.** {a.definicion}")
        extra = _parametro(a, b, hoy, f"asis_stc_p_{clave}")
        with st.expander("Más filtros", icon=":material/filter_alt:"):
            mas = _panel_filtros(b, f"asis_stc_f_{clave}", universo_fijo=a.filtros.universo)
        f = Q.combinar(a.filtros, extra.get("filtros"), mas)
        _resultado(a.tipo, b, fuentes, f, hoy, a.columnas, a.orden, a.asc, extra, a.clave)


def _parametro(a: Q.Atajo, b: pd.DataFrame, hoy: dt.date, pfx: str) -> dict:
    p = a.parametro
    if p == "etapa_inscripcion":
        sel = st.multiselect("Etapa", ["Orientados SIN INSCRIBIR", "Orientados INSCRITOS"],
                             default=["Orientados SIN INSCRIBIR", "Orientados INSCRITOS"], key=f"{pfx}_et")
        return {"filtros": Q.Filtros(cat={"etapa_pendiente": sel or ["Orientados SIN INSCRIBIR", "Orientados INSCRITOS"]})}
    if p == "hitos":
        hitos = sorted([h for h in b["hito"].unique() if h], key=G._orden_hito)
        sel = st.multiselect("Hito", hitos, default=[h for h in hitos if h.startswith("Pago")][:1] or hitos[:1],
                             key=f"{pfx}_h")
        return {"filtros": Q.Filtros(cat={"hito": sel or hitos})}
    if p == "momentos":
        momentos = sorted(m for m in b["momento"].unique() if m)
        sel = st.multiselect("Momento del proceso", momentos, default=[m for m in momentos if m.startswith("2")],
                             key=f"{pfx}_m")
        return {"filtros": Q.Filtros(cat={"momento": sel or momentos})}
    if p == "certificado":
        op = st.radio("Caso", ["Finalizados sin certificado", "Generados sin subir a STC"], horizontal=True,
                      key=f"{pfx}_c") or "Finalizados sin certificado"
        if op.startswith("Finalizados"):
            return {"filtros": Q.Filtros(cat={"estado_formacion": ["FINALIZADO"], "tiene_certificado": [Q.NO]})}
        return {"filtros": Q.Filtros(cat={"consolidado_cert": ["Generado"]})}
    if p == "fecha_asistencia":
        dia = st.date_input("Sin asistir a clase desde", value=hoy - dt.timedelta(days=7), max_value=hoy,
                            format="DD/MM/YYYY", key=f"{pfx}_d")
        return {"filtros": Q.Filtros(fecha={"f_ult_asistencia": (None, dia - dt.timedelta(days=1), True)})}
    if p == "encuesta":
        op = st.radio("¿Tiene encuesta?", [Q.NO, Q.SI], horizontal=True, key=f"{pfx}_e") or Q.NO
        return {"filtros": Q.Filtros(cat={"encuesta": [op]})}
    if p == "semaforo":
        sel = st.multiselect("Semáforo", G.SEMAFORO, default=[G.SEMAFORO[0]], key=f"{pfx}_s")
        etapas = ["Sin verificar", "Verificados sin orientar", "Orientados SIN INSCRIBIR", "Orientados INSCRITOS"]
        return {"filtros": Q.Filtros(cat={"semaforo": sel or G.SEMAFORO, "etapa_pendiente": etapas})}
    if p == "actividad":
        c1, c2 = st.columns([1, 2])
        proceso = c1.selectbox("Proceso", ["Verificación", "Orientación", "Formación", "Encuestas"], key=f"{pfx}_pr")
        r = c2.date_input("Días", value=(G.ultimos_habiles(hoy, 10)[0], hoy), max_value=hoy, format="DD/MM/YYYY",
                          key=f"{pfx}_r")
        r = list(r) if isinstance(r, (list, tuple)) else [r]
        return {"proceso": proceso, "desde": r[0] if r else hoy, "hasta": r[-1] if r else hoy}
    if p == "por":
        return {"por": st.selectbox("Agrupar por", Q.DIM_RESUMEN, format_func=Q.CAMPOS.get, key=f"{pfx}_por")}
    if p == "dim":
        c1, c2 = st.columns(2)
        filas = c1.selectbox("Filas", Q.DIM_RESUMEN, format_func=Q.CAMPOS.get, key=f"{pfx}_f")
        cols = c2.selectbox("Columnas", list(Q.COL_DISTRIBUCION), format_func=Q.COL_DISTRIBUCION.get, key=f"{pfx}_c")
        return {"filas": filas, "columnas": cols}
    return {}


# ------------------------------------------------------------------ constructor
TIPOS = {"lista": "Lista de personas (cifra + CSV)", "resumen": "Tabla resumen por…",
         "distribucion": "Distribución (conteo cruzado)"}


def _constructor(b: pd.DataFrame, fuentes: dict, hoy: dt.date) -> None:
    tipo = st.selectbox("¿Qué necesitas?", list(TIPOS), format_func=TIPOS.get, key="asis_stc_c_tipo")
    extra, columnas = {}, Q.COLUMNAS_BASE
    if tipo == "lista":
        columnas = st.multiselect("Columnas del CSV", Q.COLUMNAS_LISTA, default=Q.COLUMNAS_BASE,
                                  format_func=Q.CAMPOS.get, key="asis_stc_c_cols") or Q.COLUMNAS_BASE
    elif tipo == "resumen":
        extra = {"por": st.selectbox("Agrupar por", Q.DIM_RESUMEN, format_func=Q.CAMPOS.get, key="asis_stc_c_por")}
    else:
        c1, c2 = st.columns(2)
        extra = {"filas": c1.selectbox("Filas", Q.DIM_RESUMEN, format_func=Q.CAMPOS.get, key="asis_stc_c_f"),
                 "columnas": c2.selectbox("Columnas", list(Q.COL_DISTRIBUCION), format_func=Q.COL_DISTRIBUCION.get,
                                          key="asis_stc_c_c")}
    st.markdown("**Filtros**")
    f = _panel_filtros(b, "asis_stc_c")
    _resultado(tipo, b, fuentes, f, hoy, columnas, ["momento"], True, extra, "constructor")


# ------------------------------------------------------------------ panel de filtros (compartido)
def _opciones(b: pd.DataFrame, col: str) -> list[str]:
    v = sorted({str(x) for x in b[col].dropna().unique() if str(x).strip()})
    if col == "hito":
        return sorted(v, key=G._orden_hito)
    if col == "semaforo":
        return [s for s in G.SEMAFORO if s in v]
    return v


def _panel_filtros(b: pd.DataFrame, pfx: str, universo_fijo: str | None = None) -> Q.Filtros:
    f = Q.Filtros(universo_fijo or "vivos")
    if universo_fijo is None:
        f.universo = st.selectbox("¿A quiénes incluyo?", list(Q.UNIVERSOS), format_func=Q.UNIVERSOS.get,
                                  key=f"{pfx}_univ")
    cols = st.columns(3)
    for i, (col, etiqueta) in enumerate(Q.FILTROS_CAT):
        opciones = _opciones(b, col)
        if not opciones:
            continue
        sel = cols[i % 3].multiselect(etiqueta, opciones, key=f"{pfx}_{col}", placeholder="Todos")
        if sel:
            f.cat[col] = sel
    # Streamlit 1.38 no permite un expander dentro de otro («Más filtros»): rangos y fechas se abren con un interruptor
    if st.toggle("Filtrar por rangos (asistencia, plataforma, días…)", key=f"{pfx}_ver_rangos"):
        cols = st.columns(2)
        for i, (col, etiqueta, lo, hi) in enumerate(Q.FILTROS_RANGO):
            r = cols[i % 2].slider(etiqueta, lo, hi, (lo, hi), step=1.0, key=f"{pfx}_r_{col}")
            if r != (lo, hi):
                f.rango[col] = r
    if st.toggle("Filtrar por fechas (alta, verificación, orientación, clases…)", key=f"{pfx}_ver_fechas"):
        st.caption("Elige un rango en la fecha que quieras filtrar; deja vacío para no filtrar.")
        cols = st.columns(2)
        for i, (col, etiqueta) in enumerate(Q.FILTROS_FECHA):
            r = cols[i % 2].date_input(etiqueta, value=(), format="DD/MM/YYYY", key=f"{pfx}_fd_{col}")
            r = list(r) if isinstance(r, (list, tuple)) else [r]
            if r:
                f.fecha[col] = (r[0], r[-1], False)
    return f


# ------------------------------------------------------------------ resultado (cifra, vista previa y CSV)
def _resultado(tipo: str, b: pd.DataFrame, fuentes: dict, f: Q.Filtros, hoy: dt.date, columnas: list[str],
               orden: list[str], asc, extra: dict, nombre: str) -> None:
    d = Q.aplicar(b, f)
    base_n = len(Q.universo(b, f.universo))
    filtros_txt = Q.describir(f)
    st.divider()
    if tipo == "lista":
        p = f"{len(d) / base_n * 100:.1f} %".replace(".", ",") if base_n else "—"
        st.markdown(f"Encontré **{_n(len(d))} personas** ({p} de {_n(base_n)} · {Q.UNIVERSOS[f.universo].lower()}).")
        if d.empty:
            return _sin_resultados()
        _salida(Q.para_csv(Q.lista(d, columnas, orden, asc)), nombre, hoy, filtros_txt)
    elif tipo == "resumen":
        if d.empty:
            return _sin_resultados()
        por = extra.get("por", "mes_alta")
        st.markdown(f"Resumen por **{Q.CAMPOS[por].lower()}** de **{_n(len(d))} personas**.")
        _salida(Q.resumen(d, por), f"{nombre}_{por}", hoy, filtros_txt)
    elif tipo == "distribucion":
        if d.empty:
            return _sin_resultados()
        filas, cols = extra.get("filas", "paquete"), extra.get("columnas", "momento")
        st.markdown(f"**{_n(len(d))} personas** por {Q.CAMPOS[filas].lower()} y {Q.COL_DISTRIBUCION[cols].lower()}.")
        _salida(Q.distribucion(d, filas, cols), f"{nombre}_{filas}", hoy, filtros_txt)
    elif tipo == "tiempos":
        prep = G.preparar(fuentes["general"])
        t = G.tiempos(prep, hoy)
        t = t[t["Cédula"].map(Q.norm_doc).isin(set(d["doc"]))]
        if t.empty:
            return _sin_resultados()
        r = G.resumen_tiempos(t)
        st.markdown(f"Tiempos de **{_n(t['Cédula'].nunique())} personas** (días hábiles; plazos: "
                    + " · ".join(f"{e} {u}" for e, u in G.UMBRALES.items()) + ").")
        _salida(r, nombre, hoy, filtros_txt)
        venc = t[t["Estado"].eq("En curso") & t["Semáforo"].eq(G.SEMAFORO[0])]
        if len(venc):
            st.markdown(f"**{_n(len(venc))} en curso vencidos** (detalle):")
            _salida(venc.drop(columns=["Estado"]), f"{nombre}_vencidos", hoy, filtros_txt, clave="v")
    elif tipo == "actividad":
        act = G.actividad(G.preparar(fuentes["general"]), fuentes)
        dias = G.habiles_entre(extra["desde"], extra["hasta"])
        m = G.matriz_gestores(act, extra["proceso"], dias)
        if m.empty or m["Total"].sum() == 0:
            st.markdown(f"Sin registros de {extra['proceso'].lower()} en esos días.")
            return
        st.markdown(f"**{_n(int(m['Total'].iloc[-1]))} efectivos** de {extra['proceso'].lower()} entre el "
                    f"{extra['desde']:%d/%m/%Y} y el {extra['hasta']:%d/%m/%Y}.")
        _salida(m, f"{nombre}_{extra['proceso']}", hoy, f"{extra['proceso']} · {extra['desde']}–{extra['hasta']}")
        return
    elif tipo == "hitos":
        from column_mapping import META_TOTAL_PROGRAMA
        prep = G.preparar(fuentes["general"])
        prep = prep[prep["CC Prospecto"].map(Q.norm_doc).isin(set(d["doc"]))]
        m = G.matriz_hitos(prep, META_TOTAL_PROGRAMA)
        if m.empty:
            return _sin_resultados()
        apro = m.loc[m["Hito"].eq("Total aprobados"), "Total"]
        st.markdown(f"**{_n(int(apro.iloc[0]) if len(apro) else 0)} aprobados** por la SDDE en los pagos "
                    f"(meta del programa: {_n(META_TOTAL_PROGRAMA)}).")
        _salida(m, nombre, hoy, filtros_txt)
    st.caption(f"Corte: {hoy:%d/%m/%Y} · Filtros: {filtros_txt}")


def _n(x) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _sin_resultados() -> None:
    st.info("No hay resultados con estos filtros. Prueba quitando alguno en «Más filtros».",
            icon=":material/filter_alt_off:")


def _registrar(archivo: str, filas: int, detalle: str) -> None:
    """Registro de descargas en el log del servidor (Streamlit Cloud › Manage app › Logs)."""
    print(f"[asistente_stc] {dt.datetime.now():%Y-%m-%d %H:%M:%S} descarga {archivo} · {filas} filas · {detalle}",
          flush=True)


def _salida(t: pd.DataFrame, nombre: str, hoy: dt.date, detalle: str, clave: str = "") -> None:
    previa = t.head(VISTA_PREVIA)
    st.dataframe(previa, hide_index=True, use_container_width=True, height=min(420, 38 + 35 * len(previa)))
    if len(t) > VISTA_PREVIA:
        st.caption(f"Vista previa de {VISTA_PREVIA} filas; el CSV trae las {_n(len(t))}.")
    archivo = f"STC3_{nombre}_{hoy:%Y%m%d}.csv".replace(" ", "_")
    st.download_button(f"⬇️ Descargar CSV ({_n(len(t))} filas)", Q.a_csv(Q.para_csv(t)), archivo, "text/csv",
                       type="primary", key=f"asis_stc_dl_{nombre}_{clave}",
                       on_click=_registrar, args=(archivo, len(t), detalle[:400]))
