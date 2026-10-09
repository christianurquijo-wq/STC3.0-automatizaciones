"""
Pestaña de Auditoría de Calidad — para incrustar en tu app de Streamlit ya
publicada (la que ya tiene st.tabs() con la info del proyecto).

Uso en tu app.py:

    import pestana_auditoria

    tab_info, tab_otro, tab_auditoria = st.tabs(["Proyecto", "Otro", "🔍 Auditoría de calidad"])
    with tab_auditoria:
        pestana_auditoria.render()

Qué hace: en cuanto se abre la pestaña, LEE lo que ya está escrito en la Sheet
de reporte (Resumen/Hallazgos/Consumo) — no corre nada por sí sola. Muestra
métricas, las 3 tablas con filtros básicos, y un expander con los mismos 3
botones de acción (Ejecutar revisión / Diagnóstico / Estimar consumo) por si
los necesitas desde ahí mismo, sin cambiar de pestaña.
"""
import hmac

import pandas as pd
import streamlit as st

from agente_config import CAMPOS_PLATAFORMA, CONFIG
from google_clients import (
    obtener_cliente_sheets, obtener_credenciales, obtener_o_crear_hoja, obtener_servicio_drive,
)

ESTADOS = ('Verificado', 'Con novedad', 'No encontrado')


def _verificar_acceso() -> bool:
    """
    Gate de contraseña para TODA la pestaña de Auditoría — no solo los
    botones de acción (que gastan tokens y escriben en el Sheet), sino
    también el resumen/hallazgos de solo lectura, porque traen datos
    personales de participantes reales del programa.

    La clave vive en Secrets de Streamlit (AUDITORIA_PASSWORD) — nunca en
    el código ni en el repo. Se recuerda por sesión de navegador
    (st.session_state): no hay que reingresarla en cada rerun de la pestaña,
    pero sí al abrir una pestaña/sesión nueva.
    """
    if st.session_state.get('auditoria_autenticado'):
        return True

    st.subheader('🔒 Auditoría de calidad — acceso protegido')

    clave_correcta = st.secrets.get('AUDITORIA_PASSWORD')
    if not clave_correcta:
        st.error(
            'Falta configurar `AUDITORIA_PASSWORD` en Secrets de Streamlit — sin eso, esta pestaña '
            'no se puede proteger con contraseña. Agrégala en Settings → Secrets (Streamlit Cloud) '
            'o en `.streamlit/secrets.toml` (local) y recarga la app.'
        )
        return False

    clave_ingresada = st.text_input('Contraseña', type='password', key='auditoria_clave_input')
    if st.button('Ingresar', key='auditoria_clave_boton'):
        if clave_ingresada and hmac.compare_digest(clave_ingresada, str(clave_correcta)):
            st.session_state['auditoria_autenticado'] = True
            st.rerun()
        else:
            st.error('Contraseña incorrecta.')
    return False


def _leer_hoja_como_df(ss, nombre_hoja: str) -> pd.DataFrame:
    ws = obtener_o_crear_hoja(ss, nombre_hoja)
    valores = ws.get_all_values()
    if len(valores) < 2:
        return pd.DataFrame(columns=valores[0] if valores else [])
    return pd.DataFrame(valores[1:], columns=valores[0])


def leer_resultados(ss) -> dict:
    """Lee las 3 hojas del reporte y las devuelve como DataFrames — separado de render() para poder testearlo sin Streamlit."""
    return {
        'resumen': _leer_hoja_como_df(ss, CONFIG.NOMBRE_HOJA_RESUMEN),
        'hallazgos': _leer_hoja_como_df(ss, CONFIG.NOMBRE_HOJA_HALLAZGOS),
        'consumo': _leer_hoja_como_df(ss, CONFIG.NOMBRE_HOJA_CONSUMO),
    }


def calcular_metricas(df_resumen: pd.DataFrame) -> dict:
    """
    Cuenta participantes y, por cada estado (Verificado/Con novedad/No
    encontrado), cuántas CELDAS de campo tienen ese estado en todo el
    resumen — función pura, testeable sin Streamlit ni Sheets.
    """
    campos_presentes = [c for c in CAMPOS_PLATAFORMA if c in df_resumen.columns]
    metricas = {'participantes': len(df_resumen), 'Verificado': 0, 'Con novedad': 0, 'No encontrado': 0}

    if df_resumen.empty or not campos_presentes:
        return metricas

    valores = df_resumen[campos_presentes].to_numpy().flatten()
    for estado in ESTADOS:
        metricas[estado] = int((valores == estado).sum())
    return metricas


def _fila_tiene_novedad(fila, campos_presentes) -> bool:
    return any(fila.get(c) == 'Con novedad' for c in campos_presentes)


def render():
    if not _verificar_acceso():
        return

    st.subheader('🔍 Auditoría de calidad documental — STC 3.0')

    try:
        credenciales = obtener_credenciales()
        gc = obtener_cliente_sheets(credenciales)
        ss = gc.open_by_key(CONFIG.REPORT_SPREADSHEET_ID)
    except Exception as e:
        st.error(f'No se pudo conectar con la Sheet de reporte: {e}')
        return

    if st.button('🔄 Actualizar', key='auditoria_refrescar'):
        st.rerun()

    resultados = leer_resultados(ss)
    df_resumen, df_hallazgos, df_consumo = resultados['resumen'], resultados['hallazgos'], resultados['consumo']

    metricas = calcular_metricas(df_resumen)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Participantes revisados', metricas['participantes'])
    col2.metric('Campos verificados', metricas['Verificado'])
    col3.metric('Campos con novedad', metricas['Con novedad'])
    col4.metric('Campos no encontrados', metricas['No encontrado'])

    if df_resumen.empty:
        st.info('Todavía no hay datos en la Sheet de reporte — corre una revisión desde el panel de abajo.')

    sub_resumen, sub_hallazgos, sub_consumo = st.tabs(['📋 Resumen por participante', '⚠️ Hallazgos', '📊 Consumo del agente'])

    with sub_resumen:
        if df_resumen.empty:
            st.caption('Sin datos todavía.')
        else:
            campos_presentes = [c for c in CAMPOS_PLATAFORMA if c in df_resumen.columns]
            col_f1, col_f2 = st.columns([2, 1])
            meses = sorted(df_resumen['Mes'].unique()) if 'Mes' in df_resumen.columns else []
            mes_sel = col_f1.multiselect('Filtrar por mes', meses, default=meses) if meses else []
            solo_con_novedad = col_f2.checkbox('Solo con alguna novedad')

            df_mostrar = df_resumen[df_resumen['Mes'].isin(mes_sel)] if meses else df_resumen
            if solo_con_novedad and campos_presentes:
                mask = df_mostrar.apply(lambda fila: _fila_tiene_novedad(fila, campos_presentes), axis=1)
                df_mostrar = df_mostrar[mask]

            st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

    with sub_hallazgos:
        if df_hallazgos.empty:
            st.caption('Sin hallazgos todavía.')
        else:
            col_f1, col_f2 = st.columns(2)
            campos_h = sorted(df_hallazgos['Campo'].unique()) if 'Campo' in df_hallazgos.columns else []
            campo_sel = col_f1.multiselect('Filtrar por campo', campos_h, default=campos_h) if campos_h else []
            texto_buscar = col_f2.text_input('Buscar por cédula o código')

            df_mostrar = df_hallazgos[df_hallazgos['Campo'].isin(campo_sel)] if campos_h else df_hallazgos
            if texto_buscar:
                mascara = (
                    df_mostrar['Participante (No. documento)'].astype(str).str.contains(texto_buscar, case=False, na=False)
                    | df_mostrar['Código'].astype(str).str.contains(texto_buscar, case=False, na=False)
                )
                df_mostrar = df_mostrar[mascara]

            st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

    with sub_consumo:
        if df_consumo.empty:
            st.caption('Sin registros de consumo todavía.')
        else:
            st.dataframe(df_consumo, use_container_width=True, hide_index=True)

    with st.expander('⚙️ Acciones (ejecutar / diagnosticar)'):
        col_a, col_b, col_c = st.columns(3)

        if col_a.button('▶ Ejecutar revisión', type='primary', key='auditoria_ejecutar'):
            import revision
            with st.spinner('Revisando documentos…'):
                try:
                    drive_service = obtener_servicio_drive(credenciales)
                    resultado = revision.ejecutar_revision(CONFIG, drive_service, gc)
                except Exception as e:
                    st.error(f'La revisión falló: {e}')
                else:
                    st.success(resultado['mensaje'])
                    for titulo, mensaje in resultado['avisos']:
                        st.warning(f'**{titulo}** — {mensaje}')
                    st.rerun()

        if col_b.button('🔧 Diagnóstico', key='auditoria_diagnostico'):
            import agente
            from diagnostico import buscar_primer_pdf
            from google_clients import descargar_bytes_archivo
            with st.spinner('Probando conexión…'):
                try:
                    drive_service = obtener_servicio_drive(credenciales)
                    primer_archivo = buscar_primer_pdf(drive_service, CONFIG.ROOT_FOLDER_ID)
                    if not primer_archivo:
                        st.warning('No se encontró ningún archivo para probar.')
                    else:
                        client = agente.obtener_cliente_gemini()
                        archivo_bytes = descargar_bytes_archivo(drive_service, primer_archivo['id'])
                        resultado = agente.probar_lectura_agente(client, CONFIG.MODELO_GEMINI, archivo_bytes)
                        if resultado['error']:
                            st.error(resultado['error'])
                        else:
                            st.success(f"OK ({resultado['tokens_usados']} token(s) usados) — {primer_archivo['name']}")
                except Exception as e:
                    st.error(f'Falló: {e}')

        if col_c.button('📊 Estimar consumo mensual', key='auditoria_estimar'):
            from consumo import estimar_consumo_mensual
            sh_consumo = obtener_o_crear_hoja(ss, CONFIG.NOMBRE_HOJA_CONSUMO)
            st.code(estimar_consumo_mensual(sh_consumo, CONFIG), language=None)

    with st.expander('🧾 Diccionario de nombres de archivo (con ayuda de IA)'):
        st.caption(
            'Barrido completo de Drive (no solo "En ruta") para detectar nombres de archivo que '
            'el sistema todavía no reconoce, y sugerir con IA a qué campo oficial corresponde cada '
            'uno. Nada se aplica solo — cada fila se revisa y se aprueba a mano antes de agregarse '
            'a la pestaña "Diccionario" del Sheet de reporte.'
        )

        if st.button('🔍 1. Escanear Drive y detectar nombres nuevos', key='dicc_escanear'):
            import diccionario as diccionario_mod
            import sugerencias_diccionario as sug_mod
            with st.spinner('Recorriendo Drive completo — puede tardar varios minutos si hay muchos archivos…'):
                try:
                    drive_service = obtener_servicio_drive(credenciales)
                    dicc_actual, ignorar_actual = diccionario_mod.cargar_diccionario(ss)
                    glosario = sug_mod.escanear_glosario_drive(drive_service, CONFIG.ROOT_FOLDER_ID)
                    nuevos = sug_mod.filtrar_nombres_nuevos(glosario, dicc_actual, ignorar_actual)
                except Exception as e:
                    st.error(f'Falló el escaneo: {e}')
                else:
                    st.session_state['dicc_nombres_nuevos'] = nuevos
                    st.session_state['dicc_actual'] = dicc_actual
                    st.session_state.pop('dicc_sugerencias', None)
                    st.success(f'{len(glosario)} nombres únicos encontrados en Drive — {len(nuevos)} todavía sin reconocer.')

        nombres_nuevos = st.session_state.get('dicc_nombres_nuevos')
        if nombres_nuevos:
            st.write(f'**{len(nombres_nuevos)} nombres sin reconocer** (de mayor a menor frecuencia):')
            st.dataframe(
                pd.DataFrame(sorted(nombres_nuevos, key=lambda x: -x['cantidad'])),
                use_container_width=True, hide_index=True,
            )

            if st.button('🤖 2. Pedir sugerencia de mapeo a Gemini', key='dicc_sugerir'):
                import agente
                import sugerencias_diccionario as sug_mod
                with st.spinner('Consultando al agente IA (una sola llamada, sin abrir PDFs)…'):
                    try:
                        client = agente.obtener_cliente_gemini()
                        resultado = sug_mod.sugerir_mapeo_ia(
                            client, nombres_nuevos, st.session_state.get('dicc_actual', {}), CONFIG,
                        )
                    except Exception as e:
                        st.error(f'Falló la sugerencia: {e}')
                    else:
                        if resultado['error']:
                            st.error(resultado['error'])
                        else:
                            st.session_state['dicc_sugerencias'] = resultado['sugerencias']
                            st.success(f"{len(resultado['sugerencias'])} sugerencia(s) recibida(s) ({resultado['tokens_usados']} tokens usados).")

        sugerencias = st.session_state.get('dicc_sugerencias')
        if sugerencias:
            st.write('**Revisa y aprueba** (las de confianza ALTA vienen pre-marcadas; edita campo/población si el agente se equivocó):')

            df_sug = pd.DataFrame(sugerencias)
            df_sug['aprobar'] = df_sug['confianza'] == 'ALTA'
            df_sug = df_sug[['aprobar', 'alias', 'campo_sugerido', 'poblacion_sugerida', 'confianza', 'justificacion']]

            df_editado = st.data_editor(
                df_sug,
                column_config={
                    'aprobar': st.column_config.CheckboxColumn('Aprobar'),
                    'campo_sugerido': st.column_config.SelectboxColumn(
                        'Campo', options=CAMPOS_PLATAFORMA + ['IGNORAR', 'NO_RECONOCIDO'],
                    ),
                    'poblacion_sugerida': st.column_config.SelectboxColumn('Población', options=['', 'GENERAL', 'JCO']),
                },
                hide_index=True, use_container_width=True, key='dicc_editor',
            )

            if st.button('✅ 3. Aplicar aprobados al Diccionario', type='primary', key='dicc_aplicar'):
                import diccionario as diccionario_mod
                aprobados = df_editado[df_editado['aprobar'] & (df_editado['campo_sugerido'] != 'NO_RECONOCIDO')]
                entradas = [
                    {
                        'alias': fila['alias'], 'campo': fila['campo_sugerido'],
                        'poblacion': fila['poblacion_sugerida'], 'origen': 'Aprobado por IA + revisión humana',
                    }
                    for _, fila in aprobados.iterrows()
                ]
                if not entradas:
                    st.warning('No hay filas marcadas para aprobar.')
                else:
                    try:
                        diccionario_mod.agregar_entradas(ss, entradas)
                    except Exception as e:
                        st.error(f'Falló al escribir en el Diccionario: {e}')
                    else:
                        st.success(f'{len(entradas)} alias agregados a la pestaña "Diccionario" — la próxima corrida ya los reconoce.')
                        st.session_state.pop('dicc_sugerencias', None)
                        st.session_state.pop('dicc_nombres_nuevos', None)
                        st.rerun()

    st.divider()
    st.subheader('🔬 Modo debug — ver el detalle del agente IA para una cédula')
    st.caption(
        'Corre el agente IA sobre todos los documentos clasificados de UNA cédula puntual y '
        'muestra el detalle completo de cada llamada: el prompt exacto que se le mandó (incluyendo '
        'qué datos del FCS y qué rango de vigencia usó) y la respuesta cruda completa — incluso '
        'cuando el documento está en regla, que hoy no queda registrado en ningún lado. Úsalo para '
        'calibrar por qué el agente marca (o no marca) una novedad. Cada documento revisado aquí '
        'hace una llamada real a Gemini (gasta tokens de verdad).'
    )

    cedula_debug = st.text_input('Número de documento a revisar', key='debug_cedula')

    if st.button('🔬 Ejecutar diagnóstico detallado', key='debug_ejecutar'):
        import agente
        import debug_agente
        import diccionario as diccionario_mod
        from fcs import cargar_fcs
        from utilidades import normalizar_documento

        with st.spinner('Buscando la carpeta y llamando al agente sobre cada documento clasificado…'):
            try:
                drive_service = obtener_servicio_drive(credenciales)
                dicc_actual, ignorar_actual = diccionario_mod.cargar_diccionario(ss)
                carpeta = debug_agente.buscar_carpeta_participante(drive_service, CONFIG.ROOT_FOLDER_ID, cedula_debug)

                if not carpeta:
                    st.warning(f'No se encontró carpeta para la cédula "{cedula_debug}".')
                else:
                    fcs_por_documento = cargar_fcs(gc, CONFIG) if CONFIG.USAR_FCS else {}
                    datos_fcs = fcs_por_documento.get(normalizar_documento(cedula_debug))
                    client = agente.obtener_cliente_gemini()
                    resultados = debug_agente.depurar_participante(
                        client, drive_service, CONFIG, dicc_actual, ignorar_actual, carpeta, cedula_debug, datos_fcs,
                    )
            except Exception as e:
                st.error(f'Falló el diagnóstico: {e}')
            else:
                st.session_state['debug_resultados'] = resultados
                st.session_state['debug_carpeta'] = carpeta
                st.session_state['debug_fcs'] = datos_fcs

    resultados_debug = st.session_state.get('debug_resultados')
    if resultados_debug:
        carpeta_info = st.session_state.get('debug_carpeta') or {}
        st.write(
            f"**Carpeta:** {carpeta_info.get('nombre_mes')}/{carpeta_info.get('name')} — "
            f"{len(resultados_debug)} documento(s) clasificado(s) revisado(s)."
        )
        fcs_info = st.session_state.get('debug_fcs')
        st.write(f"**Datos del FCS usados para esta cédula:** {fcs_info if fcs_info else 'no había datos del FCS.'}")

        if not resultados_debug:
            st.info('Esta cédula no tiene ningún documento clasificado por el Diccionario en su carpeta.')

        for r in resultados_debug:
            titulo = f"📄 {r['nombre_archivo']}  →  campo: {r['campo']}"
            if r['error']:
                titulo += '  ⚠️ ERROR'
            with st.expander(titulo):
                if r['error']:
                    st.error(r['error'])
                else:
                    datos = r['datos_crudos'] or {}
                    st.write(f"**¿Documento legible según el agente?:** {datos.get('documentoLegible')}")
                    hallazgos = datos.get('hallazgos') or []
                    if hallazgos:
                        st.write('**Hallazgos que reportó:**')
                        st.dataframe(pd.DataFrame(hallazgos), use_container_width=True, hide_index=True)
                    else:
                        st.success('El agente no reportó ninguna novedad para este documento.')

                st.write(f"**Tokens usados en esta llamada:** {r['tokens_usados']}")
                st.write('**Códigos de observación disponibles para este campo:**')
                st.code(', '.join(r['codigos_disponibles']), language=None)
                st.write('**Prompt exacto enviado al agente (el contexto del documento, sin el PDF):**')
                st.code(r['prompt_documento'], language=None)