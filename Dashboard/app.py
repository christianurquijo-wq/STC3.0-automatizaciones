# app.py
import streamlit as st
st.set_page_config(page_title="Control STC 3.0", layout="wide")

import pandas as pd
import plotly.express as px
import time
from analitica import (
            cargar_matriz_documental_con_filas, datos_grafica_documentos,
            tabla_editable_documentos, es_valor_verdadero, COLUMNAS_REQUISITOS,
        )
from sheets_write import marcar_documento_cargado
from config import FUENTES
from analitica import carga_personalizada
from cargar_datos import cargar_fuente
from normalizador import normalizar_columna_cedula
from column_mapping import CAMPO_ENTREGADO, MAPEO_CEDULA
from analitica import serie_orientacion_filtrada
import sys, os
# oct-2026: app.py vive en Dashboard/ y python_agente/ en la raiz del repo -> subir un nivel
_RUTA_PYTHON_AGENTE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python_agente")
sys.path.insert(0, _RUTA_PYTHON_AGENTE)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_RUTA_PYTHON_AGENTE, ".env"))
except ImportError:
    pass

try:
    for _clave in ("GEMINI_API_KEY", "GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SERVICE_ACCOUNT_FILE", "REPORT_SPREADSHEET_ID"):
        if _clave not in os.environ and _clave in st.secrets:
            os.environ[_clave] = st.secrets[_clave]
except Exception:
    pass

import pestana_auditoria

@st.cache_data(ttl=600)
def cargar_general():
    from bigquery_api import cargar_general_bigquery
    df = cargar_general_bigquery()
    df = normalizar_columna_cedula(df, MAPEO_CEDULA["general"])
    return df

col_logo1, col_logo2, col_titulo, col_menu = st.columns([1, 1, 3, 1])
with col_logo1:
    st.image("assets/Logo_STC_3_0.png", width=140)
with col_logo2:
    st.image("assets/logo-Kuepa.png", width=140)
with col_titulo:
    st.markdown(
        "<h1 style='color:#292929; margin-top:10px;'>Control de Calidad STC 3.0</h1>",
        unsafe_allow_html=True,
    )

with col_menu:
    st.markdown("<div style='margin-top:35px;'></div>", unsafe_allow_html=True)
    with st.popover("Acciones", use_container_width=True):
        st.markdown("**Webhooks**")

        from webhooks import disparar_webhook, WEBHOOKS_REGISTRADOS, validar_clave
        from github_actions import disparar_workflow

        for wh in WEBHOOKS_REGISTRADOS:
            key_confirmar = f"confirmar_{wh['id']}"
            if key_confirmar not in st.session_state:
                st.session_state[key_confirmar] = False

            if not st.session_state[key_confirmar]:
                if st.button(wh["etiqueta"], key=f"btn_{wh['id']}"):
                    if wh.get("confirmar"):
                        st.session_state[key_confirmar] = True
                        # st.rerun()
                    else:
                        with st.spinner(f"Ejecutando {wh['etiqueta']}..."):
                            if "repo" in wh:
                                exito, mensaje = disparar_workflow(wh["repo"], wh["workflow_file"], token_env=wh.get("token_env", "GITHUB_TOKEN"))
                            else:
                                exito, mensaje = disparar_webhook(
                                    wh["url_env"], wh["header_nombre_env"], wh["header_valor_env"]
                                )
                        if exito:
                            st.success(mensaje)
                        else:
                            st.error(mensaje)
            else:
                st.warning(wh.get("mensaje_confirmacion", "¿Confirmas ejecutar esta acción?"))
                clave_ingresada = st.text_input("Contraseña de autorización", type="password", key=f"clave_{wh['id']}")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Sí", key=f"si_{wh['id']}"):
                        if not validar_clave(clave_ingresada):
                            st.error("Contraseña incorrecta.")
                        else:
                            with st.spinner(f"Ejecutando {wh['etiqueta']}..."):
                                if "repo" in wh:
                                    exito, mensaje = disparar_workflow(wh["repo"], wh["workflow_file"])
                                    if exito:
                                        st.session_state[f"seguimiento_{wh['id']}"] = time.time()
                                else:
                                    exito, mensaje = disparar_webhook(
                                        wh["url_env"], wh["header_nombre_env"], wh["header_valor_env"]
                                    )
                            st.session_state[key_confirmar] = False
                            if exito:
                                st.success(mensaje)
                            else:
                                st.error(mensaje)
                with c2:
                    if st.button("❌ No", key=f"no_{wh['id']}"):
                        st.session_state[key_confirmar] = False
                        st.rerun()
            st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)

            key_seguimiento = f"seguimiento_{wh['id']}"
            if st.session_state.get(key_seguimiento):
                from github_actions import obtener_ultima_ejecucion
                intentos_key = f"intentos_{wh['id']}"
                st.session_state.setdefault(intentos_key, 0)

                resultado_run = obtener_ultima_ejecucion(wh["repo"], wh["workflow_file"], st.session_state[key_seguimiento], token_env=wh.get("token_env", "GITHUB_TOKEN"))

                if resultado_run.get("encontrada") and resultado_run["status"] == "completed":
                    if resultado_run["conclusion"] == "success":
                        st.success(f"✅ '{wh['etiqueta']}' terminó exitosamente. [Ver detalle]({resultado_run['url']})")
                    else:
                        st.error(f"❌ '{wh['etiqueta']}' falló ({resultado_run['conclusion']}). [Ver detalle]({resultado_run['url']})")
                    del st.session_state[key_seguimiento]
                    st.session_state[intentos_key] = 0
                elif st.session_state[intentos_key] >= 20:
                    st.warning(f"No se pudo confirmar el resultado tras varios intentos. Revisa manualmente en GitHub: https://github.com/{wh['repo']}/actions")
                    del st.session_state[key_seguimiento]
                    st.session_state[intentos_key] = 0
                else:
                    st.info(f"⏳ Ejecutando '{wh['etiqueta']}'... (verificando estado)")
                    st.session_state[intentos_key] += 1
                    time.sleep(3)
                    st.rerun()

        st.markdown("**Reporte por correo**")
        st.caption("Ve al tab Overview para enviar el reporte con el detalle completo.")

from analitica import cargar_todo_cache, calcular_prediccion, html_franja_prediccion

try:
    with carga_personalizada("Calculando proyección de avance..."):
        f_prediccion = cargar_todo_cache()
        pred = calcular_prediccion(f_prediccion["general"])
    st.markdown(html_franja_prediccion(pred), unsafe_allow_html=True)
except Exception as e:
    st.error("No se pudo cargar el resumen de avance (posible bache de red). Los demás tabs pueden seguir funcionando.")
    if st.button("🔄 Reintentar carga de avance"):
        st.cache_data.clear()
        st.rerun()

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🔍 Consulta por CC", "📄 Compilador FCS", "⏰ Alertas por tiempos", "📊 Overview",
    "🌐 Dashboard Proyecto", "📋 Evidencias SDDE", "🔎 Auditoría de calidad", "🎯 Seguimiento individual",
])

# =========================================================
# TAB 1: Consulta por CC
# =========================================================
with tab1:
    with carga_personalizada("Cargando información general..."):
        df = cargar_general()

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        paquetes = ["Todos"] + sorted(df["Paquete"].dropna().unique().tolist())
        filtro_paquete = st.selectbox("Paquete", paquetes)
    with col2:
        estados = ["Todos"] + sorted(df["Momento del proceso"].dropna().unique().tolist())
        filtro_estado = st.selectbox("Estado / Etapa", estados)
    with col3:
        eventos = ["Todos"] + sorted(df["Evento/Base"].dropna().unique().tolist())
        filtro_evento = st.selectbox("Evento/Base", eventos)
    with col4:
        hitos = ["Todos"] + sorted(df["Hito"].dropna().unique().tolist())
        filtro_hito = st.selectbox("Hito", hitos)
    with col5:
        filtro_cc = st.text_input("Buscar por CC (parcial o completo)")

    df_filtrado = df.copy()
    if filtro_paquete != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Paquete"] == filtro_paquete]
    if filtro_estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Momento del proceso"] == filtro_estado]
    if filtro_evento != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Evento/Base"] == filtro_evento]
    if filtro_hito != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Hito"] == filtro_hito]
    if filtro_cc:
        df_filtrado = df_filtrado[df_filtrado["cedula_norm"].str.contains(filtro_cc, na=False)]

    st.write(f"**{len(df_filtrado)} personas encontradas**")

    columnas_mostrar = [
        "CC Prospecto", "Nombre completo", "ID CRM", "ID SIS",
        "Paquete", "JCO", "¿Es JCO?", "Resultado del VRD",
        "Momento del proceso", "Estado CRM", "Reporte",
        "Estado de la formación", "Evento/Base", "Hito",
    ]
    columnas_mostrar = [c for c in columnas_mostrar if c in df_filtrado.columns]
    st.dataframe(df_filtrado[columnas_mostrar], use_container_width=True)

    # --- Diagrama de ruta si la búsqueda de CC da un resultado único ---
    if filtro_cc and len(df_filtrado) == 1:
        from analitica import calcular_progreso_ruta, html_diagrama_ruta, cargar_todo_cache

        with carga_personalizada("Calculando progreso de la ruta..."):
            f_ruta = cargar_todo_cache()
            cedula_encontrada = df_filtrado.iloc[0]["cedula_norm"]
            general_normalizado = normalizar_columna_cedula(f_ruta["general"], MAPEO_CEDULA["general"])
            progreso = calcular_progreso_ruta(
                cedula_encontrada, general_normalizado,
                f_ruta["orientacion_consolidado"], f_ruta["encuesta_basico_jco"], f_ruta["encuesta_especializado"],
            )

        st.markdown("#### Progreso de ruta")
        st.markdown(html_diagrama_ruta(progreso), unsafe_allow_html=True)

    # --- Descarga y envío por correo de la tabla filtrada ---
    st.divider()
    col_desc, col_correo = st.columns(2)

    with col_desc:
        csv_filtrado = df_filtrado[columnas_mostrar].to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇️ Descargar tabla filtrada (CSV)", csv_filtrado, "consulta_cc.csv", "text/csv")

    with col_correo:
        with st.popover("📧 Enviar esta tabla por correo"):
            destinatarios_tabla = st.text_input("Correos (separados por coma)", key="correo_tabla_cc")
            if st.button("Enviar", key="btn_enviar_tabla_cc"):
                destinatarios = [d.strip() for d in destinatarios_tabla.split(",") if d.strip()]
                if not destinatarios:
                    st.warning("Escribe al menos un correo.")
                else:
                    from reportes import enviar_tabla_generica
                    with carga_personalizada("Enviando tabla por correo..."):
                        exito, mensaje = enviar_tabla_generica(
                            destinatarios, "Consulta por CC — Tabla filtrada", df_filtrado[columnas_mostrar]
                        )
                    if exito:
                        st.success(mensaje)
                    else:
                        st.error(mensaje)

# =========================================================
# TAB 2: Compilador FCS (siguiente paso)
# =========================================================
with tab2:
    df_or, _ = cargar_fuente("orientacion_consolidado")

    from column_mapping import (
        CAMPO_FECHA_FCS, CAMPO_ESTADO_FCS, CAMPO_PAQUETE_FCS,
        CAMPO_NO_PAGO, FCS_ULTIMA_COLUMNA,
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        paquetes_fcs = ["Todos"] + sorted(df_or[CAMPO_PAQUETE_FCS].dropna().unique().tolist())
        f_paquete = st.selectbox("Paquete", paquetes_fcs, key="fcs_paquete")

    with col2:
        if CAMPO_ESTADO_FCS in df_or.columns:
            estados_fcs = ["Todos"] + sorted(df_or[CAMPO_ESTADO_FCS].dropna().unique().tolist())
            f_estado = st.selectbox("Estado FCS", estados_fcs, key="fcs_estado")
        else:
            st.warning(f"No encuentro la columna '{CAMPO_ESTADO_FCS}' todavía en la hoja.")
            f_estado = "Todos"

    with col3:
        f_no_pago = st.text_input("No. PAGO (parcial o completo)", key="fcs_no_pago")

    with col4:
        fechas_validas = pd.to_datetime(df_or[CAMPO_FECHA_FCS], dayfirst=True, errors="coerce").dropna()
        if len(fechas_validas) > 0:
            rango = st.date_input(
                "Rango de Fecha de Atención",
                value=(fechas_validas.min(), fechas_validas.max()),
                key="fcs_rango_fecha",
            )
        else:
            rango = None

    # --- Aplicar filtros ---
    df_fcs = df_or.copy()
    df_fcs["_fecha_parseada"] = pd.to_datetime(df_fcs[CAMPO_FECHA_FCS], dayfirst=True, errors="coerce")

    if f_paquete != "Todos":
        df_fcs = df_fcs[df_fcs[CAMPO_PAQUETE_FCS] == f_paquete]
    if f_estado != "Todos" and CAMPO_ESTADO_FCS in df_fcs.columns:
        df_fcs = df_fcs[df_fcs[CAMPO_ESTADO_FCS] == f_estado]
    if f_no_pago:
        df_fcs = df_fcs[df_fcs[CAMPO_NO_PAGO].astype(str).str.contains(f_no_pago, na=False)]
    if rango and len(rango) == 2:
        inicio, fin = pd.Timestamp(rango[0]), pd.Timestamp(rango[1])
        df_fcs = df_fcs[df_fcs["_fecha_parseada"].between(inicio, fin)]

    st.write(f"**{len(df_fcs)} registros encontrados**")
    st.dataframe(df_fcs.iloc[:, :FCS_ULTIMA_COLUMNA], use_container_width=True)

    # --- Descarga con formato oficial FCS (columnas A hasta CE únicamente) ---
    csv_fcs = df_fcs.iloc[:, :FCS_ULTIMA_COLUMNA].to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="⬇️ Descargar FCS (CSV)",
        data=csv_fcs,
        file_name="FCS_compilado.csv",
        mime="text/csv",
    )

# =========================================================
# TAB 3: Análisis de datos
# =========================================================
with tab3:
    from analitica import cargar_todo_cache, generar_resumen, campos_vacios_fcs

    with carga_personalizada("Cargando análisis de datos..."):
        f_tab3 = cargar_todo_cache()

    with carga_personalizada("Calculando análisis..."):
        resumen = generar_resumen(f_tab3)
        vacios = campos_vacios_fcs(f_tab3["orientacion_consolidado"])

    from cargar_datos import cargar_fuente as _cargar_fuente_sub

    with carga_personalizada("Cargando subsanaciones..."):
        subsanaciones, _ = _cargar_fuente_sub("subsanaciones")

    conteo_orientador = subsanaciones["Orientador/a"].value_counts().reset_index()
    conteo_orientador.columns = ["Orientador/a", "Cantidad"]
    st.dataframe(conteo_orientador, use_container_width=True, hide_index=True)

    st.divider()

    col_sub1, col_sub2 = st.columns(2)
    with col_sub1:
        orientadores_sub = ["Todos"] + sorted(subsanaciones["Orientador/a"].dropna().unique().tolist())
        f_orientador_sub = st.selectbox("Orientador/a", orientadores_sub, key="filtro_orientador_sub")
    with col_sub2:
        f_cc_sub = st.text_input("Buscar por CC (parcial o completo)", key="filtro_cc_sub")

    subsanaciones_filtrado = subsanaciones.copy()
    if f_orientador_sub != "Todos":
        subsanaciones_filtrado = subsanaciones_filtrado[subsanaciones_filtrado["Orientador/a"] == f_orientador_sub]
    if f_cc_sub:
        subsanaciones_filtrado = subsanaciones_filtrado[subsanaciones_filtrado["Documento"].astype(str).str.contains(f_cc_sub, na=False)]

    st.write(f"**{len(subsanaciones_filtrado)} registros encontrados**")
    st.dataframe(subsanaciones_filtrado, use_container_width=True)

    st.divider()

    st.subheader("Resumen de inconsistencias por caso")

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        momentos_bu_tab3 = sorted(f_tab3["general"]["Momento del proceso (Back UP)"].dropna().unique().tolist())
        f_momento_bu_tab3 = st.multiselect("Momento del proceso (Back UP)", momentos_bu_tab3, key="f_momento_bu_tab3")
    with fc2:
        hitos_tab3 = sorted(f_tab3["general"]["Hito"].dropna().unique().tolist())
        f_hito_tab3 = st.multiselect("Hito", hitos_tab3, key="f_hito_tab3")
    with fc3:
        paquetes_tab3 = sorted(f_tab3["general"]["Paquete"].dropna().unique().tolist())
        f_paquete_tab3 = st.multiselect("Paquete", paquetes_tab3, key="f_paquete_tab3")

    if f_momento_bu_tab3 or f_hito_tab3 or f_paquete_tab3:
        general_filtrado_tab3 = f_tab3["general"].copy()
        if f_momento_bu_tab3:
            general_filtrado_tab3 = general_filtrado_tab3[general_filtrado_tab3["Momento del proceso (Back UP)"].isin(f_momento_bu_tab3)]
        if f_hito_tab3:
            general_filtrado_tab3 = general_filtrado_tab3[general_filtrado_tab3["Hito"].isin(f_hito_tab3)]
        if f_paquete_tab3:
            general_filtrado_tab3 = general_filtrado_tab3[general_filtrado_tab3["Paquete"].isin(f_paquete_tab3)]
        f_tab3_filtrado = dict(f_tab3)
        f_tab3_filtrado["general"] = general_filtrado_tab3
        with carga_personalizada("Aplicando filtros..."):
            resumen = generar_resumen(f_tab3_filtrado)

    df_resumen = pd.DataFrame([
        {"Caso": nombre, "Cantidad": len(tabla)} for nombre, tabla in resumen.items()
    ]).sort_values("Cantidad", ascending=True)

    fig_resumen = px.bar(
        df_resumen, x="Cantidad", y="Caso", orientation="h", text="Cantidad",
    )
    fig_resumen.update_traces(marker_color="#821F0D", textposition="outside", cliponaxis=False)
    fig_resumen.update_layout(
        height=450,
        showlegend=False,
        margin=dict(l=220, r=60, t=20, b=20),  # margen izquierdo amplio para que no se corten las etiquetas
        yaxis=dict(automargin=True),
    )

    evento = st.plotly_chart(
        fig_resumen, use_container_width=True,
        on_select="rerun", selection_mode="points", key="grafica_resumen",
    )

    puntos = evento.get("selection", {}).get("points", []) if evento else []
    if puntos:
        caso_clic = puntos[0]["y"]
        st.markdown(f"### Detalle: {caso_clic}")
        tabla_clic = resumen[caso_clic]
        st.write(f"**{len(tabla_clic)} registros**")
        st.dataframe(tabla_clic, use_container_width=True)
        csv_clic = tabla_clic.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇️ Descargar este caso (CSV)", csv_clic, f"{caso_clic}.csv", "text/csv")
    else:
        st.info("Haz clic en una barra para ver el detalle de ese caso.")

    st.divider()
    st.subheader("Auditoría de campos vacíos en el FCS (columnas A–CE)")

    top_vacios = vacios["campo_vacio"].value_counts().reset_index()
    top_vacios.columns = ["Campo", "Cantidad"]
    top_vacios = top_vacios.sort_values("Cantidad", ascending=True).tail(20)

    fig_vacios = px.bar(
        top_vacios, x="Cantidad", y="Campo", orientation="h", text="Cantidad",
    )
    fig_vacios.update_traces(marker_color="#FD531E", textposition="outside", cliponaxis=False)
    fig_vacios.update_layout(
        height=600,
        showlegend=False,
        margin=dict(l=280, r=60, t=20, b=20),
        yaxis=dict(automargin=True),
    )

    evento_vacios = st.plotly_chart(
        fig_vacios, use_container_width=True,
        on_select="rerun", selection_mode="points", key="grafica_vacios",
    )

    st.divider()

    puntos_vacios = evento_vacios.get("selection", {}).get("points", []) if evento_vacios else []

    if puntos_vacios:
        campo_clic = puntos_vacios[0]["y"]
        st.markdown(f"### Cédulas con '{campo_clic}' vacío")
        indices_filtro_vacio = vacios[vacios["campo_vacio"] == campo_clic]["indice_fila"].tolist()
    else:
        st.markdown("### FCS completo — todas las cédulas con al menos un campo vacío")
        indices_filtro_vacio = vacios["indice_fila"].unique().tolist()

    detalle_fcs_completo = f_tab3["orientacion_consolidado"].loc[indices_filtro_vacio]

    st.write(f"**{len(detalle_fcs_completo)} registros**")
    st.dataframe(detalle_fcs_completo, use_container_width=True)
    csv_completo = detalle_fcs_completo.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("⬇️ Descargar (CSV)", csv_completo, "fcs_vacios.csv", "text/csv")

# =========================================================
# TAB 4: Overview
# =========================================================
with tab4:
    from analitica import cargar_todo_cache, cargar_metas, resumen_looker, tabla_estados, serie_temporal

    with carga_personalizada("Cargando datos del overview..."):
        f = cargar_todo_cache()
        metas = cargar_metas()

    def tarjeta(valor, etiqueta, color="#656A71", progreso=None):
        barra_html = ""
        if progreso is not None:
            progreso_clamp = max(0, min(100, progreso))
            barra_html = (
                f'<div style="background-color:#EAEAEA; border-radius:4px; height:6px; margin-top:10px;">'
                f'<div style="background-color:{color}; width:{progreso_clamp}%; height:6px; border-radius:4px;"></div>'
                f'</div>'
            )
        html = (
            f'<div style="background-color:#FFFFFF; border-left:4px solid {color}; padding:16px 18px; '
            f'border-radius:8px; margin-bottom:12px; box-shadow:0 1px 4px rgba(0,0,0,0.08);">'
            f'<div style="font-size:12px; color:#656A71; text-transform:uppercase; letter-spacing:0.5px;">{etiqueta}</div>'
            f'<div style="font-size:28px; color:#292929; font-weight:700; margin-top:4px;">{valor}</div>'
            f'{barra_html}'
            f'</div>'
        )
        st.markdown(html, unsafe_allow_html=True)

    excluir_entregados = st.toggle(
        "Ver solo pendientes por entregar (excluye quienes ya tienen 'Hito' registrado)",
        value=False,
    )

    st.markdown("#### Filtros")
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        paquetes_ov = ["Todos"] + sorted(f["general"]["Paquete"].dropna().unique().tolist())
        f_paquete_ov = st.selectbox("Paquete", paquetes_ov, key="ov_paquete")
    with fc2:
        estados_ov = ["Todos"] + sorted(f["general"]["Momento del proceso"].dropna().unique().tolist())
        f_estado_ov = st.selectbox("Estado / Etapa", estados_ov, key="ov_estado")
    with fc3:
        eventos_ov = ["Todos"] + sorted(f["general"]["Evento/Base"].dropna().unique().tolist())
        f_evento_ov = st.selectbox("Evento/Base", eventos_ov, key="ov_evento")
    with fc4:
        hitos_ov = ["Todos"] + sorted(f["general"]["Hito"].dropna().unique().tolist())
        f_hito_ov = st.selectbox("Hito", hitos_ov, key="ov_hito")

    from analitica import aplicar_filtros_generales
    general_normalizado_ov = normalizar_columna_cedula(f["general"], MAPEO_CEDULA["general"])
    general_filtrado = aplicar_filtros_generales(general_normalizado_ov, f_paquete_ov, f_estado_ov, f_evento_ov, f_hito_ov)

    r = resumen_looker(general_filtrado, metas, excluir_entregados=excluir_entregados, hito_filtro=f_hito_ov)

    st.subheader(f"Dashboard General — mes en curso: {r['mes_actual']}")

    # ============================================================
    # SECCIÓN 1: Datos generales (KPIs)
    # ============================================================
    with st.expander("📊 Datos generales", expanded=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: tarjeta(r["leads"], "Leads en CRM", "#656A71")
        with c2: tarjeta(r["matriculados"], "Matriculados CRM", "#656A71")
        with c3: tarjeta(r["en_proceso"], "En proceso (Verificación)", "#656A71")
        with c4: tarjeta(r["verificados_monitoreo"], "Verificados por Monitoreo", "#656A71")
        with c5: tarjeta(f"{r['avance_fecha_verificacion']}%", "Avance a la fecha", "#FD531E", progreso=r['avance_fecha_verificacion'])

        st.markdown("#### Orientación")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: tarjeta(r["orientados"], "Orientados (Total)", "#656A71")
        with c2: tarjeta(r["orientados_basicos"], "Orientados Básicos", "#656A71")
        with c3: tarjeta(r["orientados_especializados"], "Orientados Especializados", "#656A71")
        with c4: tarjeta(r["revisados_calidad_orientacion"], "Revisados Calidad Orientación", "#656A71")
        with c5: tarjeta(f"{r['avance_general_orientacion']}%", "Avance a la fecha", "#FD531E", progreso=r['avance_general_orientacion'])

        st.markdown("#### Formación")
        c1, c2, c3 = st.columns(3)
        with c1: tarjeta(r["formados_en_curso"], "En curso", "#656A71")
        with c2: tarjeta(r["finalizados_formacion"], "Finalizados", "#656A71")
        with c3: tarjeta(f"{r['avance_general_formacion']}%", "Avance a la fecha", "#FD531E", progreso=r['avance_general_formacion'])

        st.markdown("#### Entregas")
        c1, c2 = st.columns(2)
        with c1: tarjeta(r["cantidad_entregados"], "Cantidad entregados", "#656A71")
        with c2: tarjeta(f"{r['avance_entregas']}%", "Avance sobre meta total (5102)", "#FD531E", progreso=r['avance_entregas'])

        st.divider()
        st.markdown("### 📧 Enviar reporte por correo")

        from reportes import enviar_reporte

        destinatarios_texto = st.text_input(
            "Correos destinatarios (separados por coma)",
            placeholder="persona1@kuepa.com, persona2@kuepa.com",
        )

        if st.button("Enviar reporte ahora"):
            destinatarios = [d.strip() for d in destinatarios_texto.split(",") if d.strip()]
            if not destinatarios:
                st.warning("Escribe al menos un correo destinatario.")
            else:
                tabla_para_reporte = tabla_estados(
                    general_filtrado, f["encuesta_basico_jco"], f["encuesta_especializado"],
                    excluir_entregados=excluir_entregados, por_paquete=True,
                    cedulas_filtro=set(general_filtrado["cedula_norm"]),
                )

                df_momento_reporte = general_filtrado.copy()
                if excluir_entregados and CAMPO_ENTREGADO in df_momento_reporte.columns:
                    from analitica import es_entregado
                    df_momento_reporte = df_momento_reporte[~es_entregado(df_momento_reporte[CAMPO_ENTREGADO])]
                conteo_momento_reporte = df_momento_reporte["Momento del proceso (Back UP)"].value_counts().reset_index()
                conteo_momento_reporte.columns = ["Etapa", "Cantidad"]
                conteo_momento_reporte = conteo_momento_reporte.sort_values("Etapa")

                series_reporte = {
                    "verificacion": serie_temporal(general_filtrado, "Fecha", "Semanal"),
                    "orientacion": serie_orientacion_filtrada(general_filtrado, "Semanal"),
                    "formacion": serie_temporal(general_filtrado, "Fecha finalización", "Semanal"),
                }

                pred_para_reporte = calcular_prediccion(general_filtrado)

                filtros_activos = []
                if f_paquete_ov != "Todos": filtros_activos.append(f"Paquete: {f_paquete_ov}")
                if f_estado_ov != "Todos": filtros_activos.append(f"Estado: {f_estado_ov}")
                if f_evento_ov != "Todos": filtros_activos.append(f"Evento/Base: {f_evento_ov}")
                if f_hito_ov != "Todos": filtros_activos.append(f"Hito: {f_hito_ov}")
                filtros_texto = ", ".join(filtros_activos) if filtros_activos else "Ninguno (datos completos)"

                from analitica import datos_formacion_apilada
                formacion_estado_reporte = datos_formacion_apilada(general_filtrado)

                exito, mensaje = enviar_reporte(destinatarios, r, tabla_para_reporte, conteo_momento_reporte, series_reporte, pred_para_reporte, formacion_estado_reporte, filtros_texto)
                
                if exito:
                    st.success(mensaje)
                else:
                    st.error(mensaje)

    # ============================================================
    # SECCIÓN 2: Tabla de estados + gráfica de Momento del proceso
    # ============================================================
    with st.expander("📋 Tabla de procesos y estado actual", expanded=False):
        vista_paquete = st.toggle("Ver desglosado por paquete (Básico/Especializado)", value=False)
        tabla = tabla_estados(
            general_filtrado, f["encuesta_basico_jco"], f["encuesta_especializado"],
            excluir_entregados=excluir_entregados, por_paquete=vista_paquete,
            cedulas_filtro=set(general_filtrado["cedula_norm"]),
        )
        st.dataframe(tabla, use_container_width=True, hide_index=True)

        st.markdown("#### Momento del proceso (Back UP)")
        df_momento = f["general"].copy()
        if excluir_entregados and CAMPO_ENTREGADO in df_momento.columns:
            from analitica import es_entregado
            df_momento = df_momento[~es_entregado(df_momento[CAMPO_ENTREGADO])]

        conteo_momento = df_momento["Momento del proceso (Back UP)"].value_counts().reset_index()
        conteo_momento.columns = ["Etapa", "Cantidad"]
        conteo_momento = conteo_momento.sort_values("Etapa")

        fig_momento = px.bar(conteo_momento, x="Etapa", y="Cantidad", text="Cantidad")
        fig_momento.update_traces(marker_color="#292929", textposition="outside")
        fig_momento.update_layout(height=450)
        st.plotly_chart(fig_momento, use_container_width=True)

    # ============================================================
    # SECCIÓN 3: Gráficas de evolución temporal
    # ============================================================
    with st.expander("📈 Evolución temporal por proceso", expanded=False):

        st.markdown("#### Verificación")
        ver_semanal_verif = st.toggle("📅 Gráfica por semanas", value=False, key="toggle_verif")
        granularidad_verif = "Semanal" if ver_semanal_verif else "Diaria"
        serie_verificacion = serie_temporal(f["general"], "Fecha", granularidad_verif)
        fig_v = px.line(serie_verificacion, x="Fecha", y="Cantidad", markers=True, text="Cantidad")
        fig_v.update_traces(line_color="#FD531E", textposition="top center")
        fig_v.update_layout(height=350)
        st.plotly_chart(fig_v, use_container_width=True)

        st.markdown("#### Orientación")
        ver_semanal_orient = st.toggle("📅 Gráfica por semanas", value=False, key="toggle_orient")
        granularidad_orient = "Semanal" if ver_semanal_orient else "Diaria"
        serie_orientacion = serie_orientacion_filtrada(general_filtrado, granularidad_orient)
        fig_o = px.line(serie_orientacion, x="Fecha", y="Cantidad", markers=True, text="Cantidad")
        fig_o.update_traces(line_color="#821F0D", textposition="top center")
        fig_o.update_layout(height=350)
        st.plotly_chart(fig_o, use_container_width=True)

        st.markdown("#### Formación")
        ver_semanal_form = st.toggle("📅 Gráfica por semanas", value=False, key="toggle_form")
        granularidad_form = "Semanal" if ver_semanal_form else "Diaria"
        serie_formacion = serie_temporal(general_filtrado, "Fecha finalización", granularidad_form)
        fig_f = px.line(serie_formacion, x="Fecha", y="Cantidad", markers=True, text="Cantidad")
        fig_f.update_traces(line_color="#292929", textposition="top center")
        fig_f.update_layout(height=350)
        st.plotly_chart(fig_f, use_container_width=True)

# =========================================================
# TAB 5: Dashboard
# =========================================================

with tab5:
    import streamlit.components.v1 as components

    st.subheader("Dashboard Proyecto")
    components.iframe(
        "https://datastudio.google.com/embed/reporting/a656828b-105a-43c4-88cc-99bde8b3ea07/page/p_nzkle3pm5d",
        height=800,
        scrolling=True,
    )

# =========================================================
# TAB 6: Gestión Documental / Evidencias SDDE
# =========================================================
with tab6:
    from analitica import (
        cargar_matriz_documental, resumen_cumplimiento_documental, resumen_estado_remision,
        lista_pendientes_por_responsable, detectar_inconsistencias_documentales, buscar_persona_matriz, COLUMNAS_REQUISITOS
    )

    with carga_personalizada("Cargando matriz documental..."):
        matriz = cargar_matriz_documental()

    st.subheader("Evidencias documentales para entrega a SDDE")

    with st.expander("📊 Resumen de cumplimiento", expanded=True):
        from analitica import cargar_matriz_documental_con_filas
        matriz_con_filas = cargar_matriz_documental_con_filas()
        matriz_con_filas = matriz_con_filas[matriz_con_filas["CÉDULA"].notna() & (matriz_con_filas["CÉDULA"].astype(str).str.strip() != "")]
        c1, c2, c3 = st.columns(3)
        with c1:
            control_remision_opciones = ["Todos"] + sorted(matriz_con_filas["CONTROL DE REMISIÓN"].dropna().unique().tolist())
            f_control_remision = st.selectbox("Control de Remisión", control_remision_opciones, key="f_control_remision_doc")
        with c2:
            entrega_sdde_opciones = ["Todos"] + sorted(matriz_con_filas["ENTREGA SDDE"].dropna().unique().tolist())
            f_entrega_sdde = st.selectbox("Entrega SDDE", entrega_sdde_opciones, key="f_entrega_sdde_doc")
        with c3:
            entregado_opciones = ["Todos"] + sorted(matriz_con_filas["ENTREGADO"].dropna().unique().tolist())
            f_entregado = st.selectbox("Entregado", entregado_opciones, key="f_entregado_doc")

        matriz_filtrada_doc = matriz_con_filas.copy()
        if f_control_remision != "Todos":
            matriz_filtrada_doc = matriz_filtrada_doc[matriz_filtrada_doc["CONTROL DE REMISIÓN"] == f_control_remision]
        if f_entrega_sdde != "Todos":
            matriz_filtrada_doc = matriz_filtrada_doc[matriz_filtrada_doc["ENTREGA SDDE"] == f_entrega_sdde]
        if f_entregado != "Todos":
            matriz_filtrada_doc = matriz_filtrada_doc[matriz_filtrada_doc["ENTREGADO"] == f_entregado]

        resumen_doc = resumen_cumplimiento_documental(matriz_filtrada_doc)
        c1, c2, c3 = st.columns(3)
        with c1: tarjeta(resumen_doc["total"], "Total registros", "#656A71")
        with c2: tarjeta(resumen_doc["completos"], "100% completos", "#1280B0")
        with c3: tarjeta(resumen_doc["incompletos"], "Con pendientes", "#821F0D")
        # with c4: tarjeta(f"{resumen_doc['promedio']}%", "Promedio cumplimiento", "#FD531E")

        fig_dist = px.bar(resumen_doc["distribucion"], x="% Cumplimiento", y="Cantidad", text="Cantidad")
        fig_dist.update_traces(marker_color="#FD531E", textposition="outside")
        fig_dist.update_layout(height=350)

        evento_dist = st.plotly_chart(
            fig_dist, use_container_width=True,
            on_select="rerun", selection_mode="points", key="grafica_cumplimiento_dist",
        )

        puntos_dist = evento_dist.get("selection", {}).get("points", []) if evento_dist else []

        if puntos_dist:
            pct_clic = puntos_dist[0]["x"]
            st.info(f"Filtrando por % Cumplimiento: **{pct_clic}%**")
            matriz_seccion1 = matriz_filtrada_doc[matriz_filtrada_doc["% CUMPLIMIENTO_num"] == pct_clic]
        else:
            matriz_seccion1 = matriz_filtrada_doc

        st.write(f"**{len(matriz_seccion1)} personas**")

        tabla_seccion1 = tabla_editable_documentos(matriz_seccion1)

        column_config_seccion1 = {
            "fila_sheet": None,
            "CÉDULA": st.column_config.TextColumn(disabled=True),
            "NOMBRE COMPLETO": st.column_config.TextColumn(disabled=True),
            "PAQUETE": st.column_config.TextColumn(disabled=True),
        }
        for col in COLUMNAS_REQUISITOS:
            nombre_corto = col.replace(" ✓", "")
            column_config_seccion1[nombre_corto] = st.column_config.CheckboxColumn(nombre_corto)

        st.data_editor(
            tabla_seccion1,
            column_config=column_config_seccion1,
            hide_index=True,
            key="editor_documentos_seccion1",
            use_container_width=True,
        )

        cambios_seccion1 = st.session_state.get("editor_documentos_seccion1", {}).get("edited_rows", {})
        if cambios_seccion1:
            doc_column_map_seccion1 = {c.replace(" ✓", ""): c for c in COLUMNAS_REQUISITOS}
            spreadsheet_id_seccion1 = FUENTES["matriz_documental"]["id"]
            hubo_error_seccion1 = False
            for fila_idx, cambios_columna in cambios_seccion1.items():
                fila_sheet_real = int(tabla_seccion1.iloc[int(fila_idx)]["fila_sheet"])
                for nombre_corto, nuevo_valor in cambios_columna.items():
                    columna_real = doc_column_map_seccion1.get(nombre_corto)
                    if columna_real:
                        columna_indice = matriz.columns.get_loc(columna_real)
                        exito, mensaje = marcar_documento_cargado(
                            spreadsheet_id_seccion1, "MATRIZ DOCUMENTAL", fila_sheet_real, columna_indice, bool(nuevo_valor)
                        )
                        if not exito:
                            hubo_error_seccion1 = True
                            st.error(mensaje)
            if not hubo_error_seccion1:
                st.success("Cambios guardados correctamente.")
                st.cache_data.clear()
                st.rerun()

        st.divider()
        st.markdown("#### Avance de remisión al gestor")

        total_lista = len(matriz_filtrada_doc)
        remitidos_gestor = (matriz_filtrada_doc["ENVIADO AL GESTOR ✓"].astype(str).str.strip().str.upper() == "TRUE").sum()
        pct_avance_gestor = round((remitidos_gestor / total_lista) * 100, 1) if total_lista else 0

        c_barra, c_tarjeta = st.columns([3, 1])
        with c_barra:
            st.markdown(
                f'<div style="margin-top:20px;">'
                f'<div style="font-size:13px; color:#292929; margin-bottom:4px;">Remitidos al gestor: {remitidos_gestor} / {total_lista}</div>'
                f'<div style="background-color:#EAEAEA; border-radius:4px; height:20px; width:100%;">'
                f'<div style="background-color:#1280B0; width:{min(pct_avance_gestor,100)}%; height:20px; border-radius:4px;"></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        with c_tarjeta:
            tarjeta(f"{pct_avance_gestor}%", "Avance remisión", "#1280B0")    

    with st.expander("📊 Gestión de documentos (cargados / no cargados)", expanded=True):

        matriz_editable = cargar_matriz_documental_con_filas()
        matriz_editable = matriz_editable[matriz_editable["CÉDULA"].notna() & (matriz_editable["CÉDULA"].astype(str).str.strip() != "")]

        cg1, cg2, cg3 = st.columns(3)
        with cg1:
            control_remision_gestion = ["Todos"] + sorted(matriz_editable["CONTROL DE REMISIÓN"].dropna().unique().tolist())
            f_control_remision_gestion = st.selectbox("Control de Remisión", control_remision_gestion, key="f_control_remision_gestion")
        with cg2:
            entrega_sdde_gestion = ["Todos"] + sorted(matriz_editable["ENTREGA SDDE"].dropna().unique().tolist())
            f_entrega_sdde_gestion = st.selectbox("Entrega SDDE", entrega_sdde_gestion, key="f_entrega_sdde_gestion")
        with cg3:
            entregado_gestion = ["Todos"] + sorted(matriz_editable["ENTREGADO"].dropna().unique().tolist())
            f_entregado_gestion = st.selectbox("Entregado", entregado_gestion, key="f_entregado_gestion")

        if f_control_remision_gestion != "Todos":
            matriz_editable = matriz_editable[matriz_editable["CONTROL DE REMISIÓN"] == f_control_remision_gestion]
        if f_entrega_sdde_gestion != "Todos":
            matriz_editable = matriz_editable[matriz_editable["ENTREGA SDDE"] == f_entrega_sdde_gestion]
        if f_entregado_gestion != "Todos":
            matriz_editable = matriz_editable[matriz_editable["ENTREGADO"] == f_entregado_gestion]

        datos_grafica = datos_grafica_documentos(matriz_editable)
        fig_docs = px.bar(
            datos_grafica, x="Documento", y="Cantidad", color="Estado",
            color_discrete_map={"Cargado": "#1280b0", "No cargado": "#c32e13"},
            barmode="stack", text="Cantidad",
        )
        fig_docs.update_layout(height=450, xaxis_tickangle=-30)

        evento_docs = st.plotly_chart(
            fig_docs, use_container_width=True,
            on_select="rerun", selection_mode="points", key="grafica_documentos",
        )

        puntos_docs = evento_docs.get("selection", {}).get("points", []) if evento_docs else []

        col_filtro1, col_filtro2 = st.columns([3, 1])
        with col_filtro1:
            if puntos_docs:
                doc_clic = puntos_docs[0]["x"]
                estado_clic = puntos_docs[0]["legendgroup"] if "legendgroup" in puntos_docs[0] else None
                st.info(f"Filtrando por: **{doc_clic}**" + (f" — {estado_clic}" if estado_clic else ""))
            else:
                doc_clic = None
                estado_clic = None
        with col_filtro2:
            if st.button("🔄 Quitar filtro de gráfica"):
                st.rerun()

        cc_filtro_gestion = st.text_input("Buscar por CC (parcial o completo)", key="cc_gestion_docs")

        matriz_tabla = matriz_editable.copy()
        if cc_filtro_gestion:
            matriz_tabla = matriz_tabla[matriz_tabla["cedula_norm"].str.contains(cc_filtro_gestion, na=False)]
        if doc_clic:
            columna_real_clic = doc_clic + " ✓"
            if columna_real_clic in matriz_tabla.columns:
                if estado_clic == "Cargado":
                    matriz_tabla = matriz_tabla[matriz_tabla[columna_real_clic].apply(es_valor_verdadero)]
                elif estado_clic == "No cargado":
                    matriz_tabla = matriz_tabla[~matriz_tabla[columna_real_clic].apply(es_valor_verdadero)]

        st.write(f"**{len(matriz_tabla)} personas** — haz clic en las casillas para marcar/desmarcar documentos")

        tabla_para_editar = tabla_editable_documentos(matriz_tabla)

        column_config = {
            "fila_sheet": None,
            "CÉDULA": st.column_config.TextColumn(disabled=True),
            "NOMBRE COMPLETO": st.column_config.TextColumn(disabled=True),
            "PAQUETE": st.column_config.TextColumn(disabled=True),
        }
        for col in COLUMNAS_REQUISITOS:
            nombre_corto = col.replace(" ✓", "")
            column_config[nombre_corto] = st.column_config.CheckboxColumn(nombre_corto)

        st.data_editor(
            tabla_para_editar,
            column_config=column_config,
            hide_index=True,
            key="editor_documentos",
            use_container_width=True,
        )

        cambios = st.session_state.get("editor_documentos", {}).get("edited_rows", {})
        if cambios:
            doc_column_map = {c.replace(" ✓", ""): c for c in COLUMNAS_REQUISITOS}
            spreadsheet_id = FUENTES["matriz_documental"]["id"]
            hubo_error = False
            for fila_idx, cambios_columna in cambios.items():
                fila_sheet_real = int(tabla_para_editar.iloc[int(fila_idx)]["fila_sheet"])
                for nombre_corto, nuevo_valor in cambios_columna.items():
                    columna_real = doc_column_map.get(nombre_corto)
                    if columna_real:
                        columna_indice = matriz_editable.columns.get_loc(columna_real)
                        exito, mensaje = marcar_documento_cargado(
                            spreadsheet_id, "MATRIZ DOCUMENTAL", fila_sheet_real, columna_indice, bool(nuevo_valor)
                        )
                        if not exito:
                            hubo_error = True
                            st.error(mensaje)
            if not hubo_error:
                st.success("Cambios guardados correctamente.")
                st.cache_data.clear()
                st.rerun()

    # with st.expander("🔍 Consulta por cédula", expanded=False):
            # cc_matriz = st.text_input("Buscar por CC (parcial o completo)", key="cc_matriz_doc")
            # if cc_matriz:
                # resultado_matriz = matriz[matriz["cedula_norm"].str.contains(cc_matriz, na=False)]
                # st.write(f"**{len(resultado_matriz)} personas encontradas**")
                # st.dataframe(resultado_matriz.drop(columns=["cedula_norm", "% CUMPLIMIENTO_num"]), use_container_width=True)

    with st.expander("📦 Estado de remisión al gestor", expanded=False):
        estado_remision = resumen_estado_remision(matriz)
        fig_estado = px.bar(estado_remision, x="Estado", y="Cantidad", text="Cantidad")
        fig_estado.update_traces(marker_color="#292929", textposition="outside")
        fig_estado.update_layout(height=350)
        st.plotly_chart(fig_estado, use_container_width=True)
        st.dataframe(estado_remision, use_container_width=True, hide_index=True)

    with st.expander("⚠️ Lista de pendientes por responsable", expanded=False):
        pendientes = lista_pendientes_por_responsable(matriz)
        st.write(f"**{len(pendientes)} personas con observaciones pendientes**")
        st.dataframe(pendientes, use_container_width=True)
        csv_pendientes = pendientes.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("⬇️ Descargar pendientes (CSV)", csv_pendientes, "pendientes_documentales.csv", "text/csv")

    with st.expander("🔴 Inconsistencias (100% pero con observación pendiente)", expanded=False):
        inconsistencias_doc = detectar_inconsistencias_documentales(matriz)
        st.write(f"**{len(inconsistencias_doc)} casos encontrados**")
        if len(inconsistencias_doc) > 0:
            st.dataframe(inconsistencias_doc, use_container_width=True)
        else:
            st.success("No se encontraron inconsistencias de este tipo.")

    st.divider()
    st.subheader("📸 Estado de Pantallazos")

    from analitica import cargar_todo_cache
    with carga_personalizada("Cargando datos de pantallazos..."):
        f_pantallazos = cargar_todo_cache()
    general_pant = f_pantallazos["general"]

    general_pant = general_pant.copy()
    tiene_link = general_pant["Paquete de pantallazos"].notna() & (general_pant["Paquete de pantallazos"].astype(str).str.strip() != "")
    general_pant["Estado del paquete"] = tiene_link.map({True: "Paquete creado", False: "Sin paquete creado"})

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        estados_formacion_pant = ["Todos"] + sorted(general_pant["Estado de la formación"].dropna().unique().tolist())
        f_estado_form_pant = st.selectbox("Estado de la formación", estados_formacion_pant, key="filtro_estado_form_pant")
    with col_p2:
        f_estado_paquete_pant = st.selectbox("Estado del paquete de pantallazos", ["Todos", "Paquete creado", "Sin paquete creado"], key="filtro_estado_paquete_pant")

    pant_df = general_pant.copy()

    if f_estado_form_pant != "Todos":
        pant_df = pant_df[pant_df["Estado de la formación"] == f_estado_form_pant]
    if f_estado_paquete_pant != "Todos":
        pant_df = pant_df[pant_df["Estado del paquete"] == f_estado_paquete_pant]

    pant_df = pant_df[pant_df["Estado de la formación"].notna() & (pant_df["Estado de la formación"].astype(str).str.strip() != "")]

    datos_pant = pant_df.groupby(["Estado del paquete", "Estado de la formación"]).size().reset_index(name="Cantidad")

    fig_pant = px.bar(
        datos_pant, x="Estado del paquete", y="Cantidad", color="Estado de la formación",
        custom_data=["Estado de la formación"], barmode="stack", text="Cantidad",
    )
    fig_pant.update_layout(height=450, xaxis_tickangle=-20)

    evento_pant = st.plotly_chart(
        fig_pant, use_container_width=True,
        on_select="rerun", selection_mode="points", key="grafica_pantallazos",
    )

    puntos_pant = evento_pant.get("selection", {}).get("points", []) if evento_pant else []

    if puntos_pant:
        paquete_clic = puntos_pant[0]["x"]
        estado_form_clic = puntos_pant[0]["customdata"][0]
        st.info(f"Filtrando por: **{paquete_clic}** — {estado_form_clic}")
        detalle_pant = pant_df[
            (pant_df["Estado del paquete"] == paquete_clic)
            & (pant_df["Estado de la formación"] == estado_form_clic)
        ]
    else:
        detalle_pant = pant_df

    st.write(f"**{len(detalle_pant)} personas**")
    st.dataframe(
        detalle_pant[["CC Prospecto", "Nombre completo", "Paquete de pantallazos", "Estado de la formación"]],
        use_container_width=True,
    )

    from github_actions import disparar_workflow
    from webhooks import GITHUB_ACTIONS_REGISTRADOS

    for accion in GITHUB_ACTIONS_REGISTRADOS:
        key_confirmar_pant = f"confirmar_pant_{accion['id']}"
        if key_confirmar_pant not in st.session_state:
            st.session_state[key_confirmar_pant] = False

        if not st.session_state[key_confirmar_pant]:
            if st.button(accion["etiqueta"], key=f"btn_pant_{accion['id']}"):
                st.session_state[key_confirmar_pant] = True
                st.rerun()
        else:
            st.warning(accion["mensaje_confirmacion"])
            cgp1, cgp2 = st.columns(2)
            clave_ingresada_pant = st.text_input("Contraseña de autorización", type="password", key=f"clave_pant_{accion['id']}")
            with cgp1:
                if st.button("✅ Sí", key=f"si_pant_{accion['id']}"):
                    if not validar_clave(clave_ingresada_pant):
                        st.error("Contraseña incorrecta.")
                    else:
                        with st.spinner(f"Ejecutando {accion['etiqueta']}..."):
                            exito, mensaje = disparar_workflow(accion["repo"], accion["workflow_file"])
                        st.session_state[key_confirmar_pant] = False
                        if exito:
                            st.toast(mensaje, icon="✅")
                        else:
                            st.toast(mensaje, icon="❌")
                        st.rerun()
            with cgp2:
                if st.button("❌ No", key=f"no_pant_{accion['id']}"):
                    st.session_state[key_confirmar_pant] = False
                    st.rerun()

# =========================================================
# TAB 7: Auditoría de calidad (agente IA)
# =========================================================
with tab7:
    pestana_auditoria.render()

# =========================================================
# TAB 8: Seguimiento Individual
# =========================================================
with tab8:
    from analitica import (
        cargar_todo_cache, cargar_formacion_consolidado_cache, serie_lineal_por_grupo,
        tabla_resumen_calidad, tabla_resumen_formacion, datos_barras_estado_formacion,
        datos_barras_cuartiles, META_VERIFICACION_LINEA, META_ORIENTACION_LINEA, META_FORMACION_LINEA,
    )
    from normalizador_texto import normalizar_texto

    st.subheader("🎯 Seguimiento Individual")

    granularidad_individual = st.radio("Granularidad de las gráficas de línea:", ["Diaria", "Semanal"], horizontal=True, key="gran_individual")

    with carga_personalizada("Cargando datos..."):
        f_ind = cargar_todo_cache()
    general_ind = f_ind["general"]

    # ---------------------------------------------------
    # Expander 1: Verificación
    # ---------------------------------------------------
    with st.expander("✅ Verificación", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            verificadores = sorted(general_ind["Verificador"].dropna().unique().tolist())
            f_verificador = st.multiselect("Verificador", verificadores, key="f_verificador_ind")
        with c2:
            hitos_v = sorted(general_ind["Hito"].dropna().unique().tolist())
            f_hito_v = st.multiselect("Hito", hitos_v, key="f_hito_v_ind")
        with c3:
            f_calidad_v = st.multiselect("Revisión de calidad", ["TRUE", "FALSE"], key="f_calidad_v_ind")

        df_v = general_ind[general_ind["Estado CRM"].astype(str).str.strip() == "Matriculado"].copy()
        if f_verificador:
            df_v = df_v[df_v["Verificador"].isin(f_verificador)]
        if f_hito_v:
            df_v = df_v[df_v["Hito"].isin(f_hito_v)]
        if f_calidad_v:
            df_v = df_v[df_v["Verificación Calidad"].astype(str).str.strip().str.upper().isin(f_calidad_v)]

        st.write(f"**{len(df_v)} matriculados**")

        serie_v = serie_lineal_por_grupo(df_v, "Verificador", "Fecha de alta", granularidad_individual)
        if not serie_v.empty:
            fig_v = px.line(serie_v, x="Periodo", y="Cantidad", color="Verificador", markers=True)
            fig_v.add_hline(y=META_VERIFICACION_LINEA, line_dash="dash", line_color="#821F0D",
                             annotation_text=f"Meta: {META_VERIFICACION_LINEA}")
            fig_v.update_layout(height=400)
            st.plotly_chart(fig_v, use_container_width=True)
        else:
            st.info("Sin datos para los filtros seleccionados.")

        calidad_bool_v = df_v["Verificación Calidad"].astype(str).str.strip().str.upper() == "TRUE"
        st.dataframe(tabla_resumen_calidad(df_v, "Verificador", calidad_bool_v), use_container_width=True, hide_index=True)

    # ---------------------------------------------------
    # Expander 2: Orientación
    # ---------------------------------------------------
    with st.expander("🧭 Orientación", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            orientadores = sorted(general_ind["Orientador"].dropna().unique().tolist())
            f_orientador = st.multiselect("Orientador", orientadores, key="f_orientador_ind")
        with c2:
            hitos_o = sorted(general_ind["Hito"].dropna().unique().tolist())
            f_hito_o = st.multiselect("Hito", hitos_o, key="f_hito_o_ind")
        with c3:
            f_calidad_o = st.multiselect("Revisión de calidad", ["Revisado", "Sin revisar"], key="f_calidad_o_ind")

        reporte_o = general_ind["Reporte"].astype(str).str.strip()
        df_o = general_ind[reporte_o.isin(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"])].copy()

        if f_orientador:
            df_o = df_o[df_o["Orientador"].isin(f_orientador)]
        if f_hito_o:
            df_o = df_o[df_o["Hito"].isin(f_hito_o)]
        if f_calidad_o:
            mask_calidad_o = df_o["Fecha Calidad Orientación"].notna() & (df_o["Fecha Calidad Orientación"].astype(str).str.strip() != "")
            condiciones = []
            if "Revisado" in f_calidad_o:
                condiciones.append(mask_calidad_o)
            if "Sin revisar" in f_calidad_o:
                condiciones.append(~mask_calidad_o)
            df_o = df_o[pd.concat(condiciones, axis=1).any(axis=1)]

        st.write(f"**{len(df_o)} orientados (reporte finalizado)**")

        serie_o = serie_lineal_por_grupo(df_o, "Orientador", "Fecha Orientación", granularidad_individual)
        if not serie_o.empty:
            fig_o = px.line(serie_o, x="Periodo", y="Cantidad", color="Orientador", markers=True)
            fig_o.add_hline(y=META_ORIENTACION_LINEA, line_dash="dash", line_color="#821F0D",
                             annotation_text=f"Meta: {META_ORIENTACION_LINEA}")
            fig_o.update_layout(height=400)
            st.plotly_chart(fig_o, use_container_width=True)
        else:
            st.info("Sin datos para los filtros seleccionados.")

        calidad_bool_o = df_o["Fecha Calidad Orientación"].notna() & (df_o["Fecha Calidad Orientación"].astype(str).str.strip() != "")
        st.dataframe(tabla_resumen_calidad(df_o, "Orientador", calidad_bool_o), use_container_width=True, hide_index=True)

    # ---------------------------------------------------
    # Expander 3: Formación
    # ---------------------------------------------------
    with st.expander("🎓 Formación", expanded=False):
        with carga_personalizada("Cargando seguimiento de formación..."):
            form_cons = cargar_formacion_consolidado_cache()

        c1, c2, c3 = st.columns(3)
        with c1:
            estados_f = sorted(form_cons["ESTADO DE LA FORMACIÓN"].dropna().unique().tolist())
            f_estado_f = st.multiselect("Estado de la formación", estados_f, key="f_estado_form_ind")
        with c2:
            responsables_f = sorted(form_cons["Responsable"].dropna().unique().tolist())
            f_responsable_f = st.multiselect("Responsable", responsables_f, key="f_responsable_ind")
        with c3:
            paquetes_pago_f = sorted(form_cons["PAQUETE DE PAGO"].dropna().unique().tolist())
            f_paquete_pago_f = st.multiselect("Paquete de pago", paquetes_pago_f, key="f_paquete_pago_ind")

        df_f = form_cons.copy()
        if f_estado_f:
            df_f = df_f[df_f["ESTADO DE LA FORMACIÓN"].isin(f_estado_f)]
        if f_responsable_f:
            df_f = df_f[df_f["Responsable"].isin(f_responsable_f)]
        if f_paquete_pago_f:
            df_f = df_f[df_f["PAQUETE DE PAGO"].isin(f_paquete_pago_f)]

        st.write(f"**{len(df_f)} registros**")

        estado_f_serie = df_f["ESTADO DE LA FORMACIÓN"].astype(str).str.strip().str.upper()
        df_finalizados = df_f[estado_f_serie.isin(["FINALIZADO", "CERTIFICADO"])]

        serie_f = serie_lineal_por_grupo(df_finalizados, "Responsable", "FECHA DE FINALIZACIÓN (DD/MM/AAAA)", granularidad_individual)
        if not serie_f.empty:
            fig_f = px.line(serie_f, x="Periodo", y="Cantidad", color="Responsable", markers=True)
            fig_f.add_hline(y=META_FORMACION_LINEA, line_dash="dash", line_color="#821F0D",
                             annotation_text=f"Meta: {META_FORMACION_LINEA}")
            fig_f.update_layout(height=400)
            st.plotly_chart(fig_f, use_container_width=True)
        else:
            st.info("Sin datos de finalizados/certificados para los filtros seleccionados.")

        st.markdown("#### Resumen por responsable")
        st.dataframe(tabla_resumen_formacion(df_f), use_container_width=True, hide_index=True)

        st.markdown("#### Asignados por Responsable y Estado")
        datos_estado_f = datos_barras_estado_formacion(df_f)
        if not datos_estado_f.empty:
            fig_estado_f = px.bar(datos_estado_f, y="Responsable", x="Cantidad", color="Estado",
                                   orientation="h", barmode="stack")
            fig_estado_f.update_layout(height=450)
            st.plotly_chart(fig_estado_f, use_container_width=True)

        st.markdown("#### Progreso de plataforma por cuartil (Responsable)")
        asistencias_disponibles = sorted(form_cons["% ASISTENCIA"].dropna().unique().tolist())
        f_asistencia_cuartil = st.multiselect("Filtrar por % Asistencia", asistencias_disponibles, key="f_asistencia_cuartil_ind")

        df_cuartil = df_f.copy()
        if f_asistencia_cuartil:
            df_cuartil = df_cuartil[df_cuartil["% ASISTENCIA"].isin(f_asistencia_cuartil)]

        datos_cuartil = datos_barras_cuartiles(df_cuartil)
        if not datos_cuartil.empty:
            fig_cuartil = px.bar(datos_cuartil, y="Responsable", x="Cantidad", color="Cuartil",
                                  orientation="h", barmode="stack",
                                  category_orders={"Cuartil": ["0% - 25%", "25% - 50%", "50% - 75%", "75% - 100%"]})
            fig_cuartil.update_layout(height=450)
            st.plotly_chart(fig_cuartil, use_container_width=True)
        else:
            st.info("Sin datos de progreso para el filtro actual.")