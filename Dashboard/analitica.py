# analitica.py
import pandas as pd
import streamlit as st
import numpy as np
from cargar_datos import cargar_fuente
from normalizador import normalizar_cedula
from column_mapping import CAMPO_ESTADO_FCS
from normalizador_texto import normalizar_texto
from concurrent.futures import ThreadPoolExecutor, as_completed

# Columnas del FCS a excluir de la auditoría de vacíos (G y H = fechas de
# inscripción en plataformas que legítimamente quedan vacías para muchos casos)
COLUMNAS_EXCLUIR_VACIOS = [6, 7]  # índices 0-based de G y H
FCS_ULTIMA_COLUMNA_AUDITORIA = 83  # A hasta CE

def _set_cedulas(df: pd.DataFrame, columna: str) -> set:
    return set(df[columna].apply(normalizar_cedula).dropna())

def cargar_todo():
    from bigquery_api import cargar_general_bigquery

    nombres_sheets = ["verificacion", "formacion", "orientacion_consolidado",
                       "remisiones", "encuesta_basico_jco", "encuesta_especializado"]
    fuentes = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        futuros = {executor.submit(cargar_fuente, nombre): nombre for nombre in nombres_sheets}
        futuro_bq = executor.submit(cargar_general_bigquery)

        for futuro in as_completed(futuros):
            nombre = futuros[futuro]
            df, _ = futuro.result()
            fuentes[nombre] = df

        fuentes["general"] = futuro_bq.result()

    return fuentes

@st.cache_data(ttl=600)
def cargar_todo_cache():
    return cargar_todo()

# --- Caso 1: Leads sin gestión ---
def leads_sin_gestion(general: pd.DataFrame) -> pd.DataFrame:
    return general[general["Momento del proceso"] == "0.Sin gestión"]

# --- Caso 2: Leads en verificación ---
def leads_en_verificacion(general: pd.DataFrame) -> pd.DataFrame:
    return general[general["Momento del proceso"] == "1.En verificación"]

# --- Caso 3: Verificados sin reporte de orientación ---
def verificados_sin_reporte_orientacion(general: pd.DataFrame, orientacion: pd.DataFrame) -> pd.DataFrame:
    verificados = general[general["Verificado"] == "1"].copy()
    verificados["cedula_norm"] = verificados["CC Prospecto"].apply(normalizar_cedula)

    orient_con_reporte = orientacion[orientacion["REPORTE"].notna() & (orientacion["REPORTE"].str.strip() != "")]
    cedulas_con_reporte = _set_cedulas(orient_con_reporte, "NÚMERO DE DOCUMENTO")

    return verificados[~verificados["cedula_norm"].isin(cedulas_con_reporte)]

# --- Caso 4: Formación vs Orientados Especializado (100% dentro de General) ---
def formados_sin_orientar(general: pd.DataFrame) -> pd.DataFrame:
    """AX (Estado de la formación) lleno + AE (Reporte) vacío = está en formación pero sin reporte de orientación."""
    en_formacion = general["Estado de la formación"].notna() & (general["Estado de la formación"].astype(str).str.strip() != "")
    sin_reporte = general["Reporte"].isna() | (general["Reporte"].astype(str).str.strip() == "")
    return general[en_formacion & sin_reporte]

def orientados_especializado_sin_formacion(general: pd.DataFrame) -> pd.DataFrame:
    """AE (Reporte) lleno + AH (Paquete)=ESPECIALIZADO + AX (Estado de la formación) vacío = orientado especializado que no está en formación."""
    con_reporte = general["Reporte"].notna() & (general["Reporte"].astype(str).str.strip() != "")
    es_especializado = general["Paquete"].astype(str).str.strip().str.upper() == "ESPECIALIZADO"
    sin_formacion = general["Estado de la formación"].isna() | (general["Estado de la formación"].astype(str).str.strip() == "")
    return general[con_reporte & es_especializado & sin_formacion]

# --- Caso 5: Orientados vs Remitidos ---
def diff_orientados_vs_remitidos(orientacion: pd.DataFrame, remisiones: pd.DataFrame) -> dict:
    cedulas_orientados = _set_cedulas(orientacion, "NÚMERO DE DOCUMENTO")
    cedulas_remitidos = _set_cedulas(remisiones, "NÚMERO DE DOCUMENTO")

    solo_orientados = cedulas_orientados - cedulas_remitidos
    solo_remitidos = cedulas_remitidos - cedulas_orientados

    return {
        "solo_orientados": orientacion[orientacion["NÚMERO DE DOCUMENTO"].apply(normalizar_cedula).isin(solo_orientados)],
        "solo_remitidos": remisiones[remisiones["NÚMERO DE DOCUMENTO"].apply(normalizar_cedula).isin(solo_remitidos)],
    }

# --- Caso 6: Encuestados vs Listos para reportar ---
def diff_encuestados_vs_listos_reportar(orientacion: pd.DataFrame, enc_basico: pd.DataFrame, enc_esp: pd.DataFrame) -> dict:
    cedulas_encuestados = _set_cedulas(enc_basico, "CEDULA") | _set_cedulas(enc_esp, "CEDULA")

    listos = orientacion[orientacion[CAMPO_ESTADO_FCS].str.strip().str.upper() == "LISTO PARA REPORTAR"]
    cedulas_listos = _set_cedulas(listos, "NÚMERO DE DOCUMENTO")

    solo_encuestados = cedulas_encuestados - cedulas_listos
    solo_listos = cedulas_listos - cedulas_encuestados

    return {
        "solo_encuestados": solo_encuestados,   # sets simples, no siempre hay fila completa disponible
        "solo_listos": listos[listos["NÚMERO DE DOCUMENTO"].apply(normalizar_cedula).isin(solo_listos)],
    }

# --- Auditoría de campos vacíos en el FCS (A hasta CE, excepto G y H) ---
def campos_vacios_fcs(orientacion: pd.DataFrame) -> pd.DataFrame:
    # Solo auditar filas con cédula real (descarta filas fantasma vacías del rango de la API)
    tiene_cedula = orientacion["NÚMERO DE DOCUMENTO"].notna() & (orientacion["NÚMERO DE DOCUMENTO"].astype(str).str.strip() != "")
    orientacion = orientacion[tiene_cedula]

    columnas_auditar = [
        c for i, c in enumerate(orientacion.columns[:FCS_ULTIMA_COLUMNA_AUDITORIA])
        if i not in COLUMNAS_EXCLUIR_VACIOS
    ]

    registros = []
    for idx, fila in orientacion.iterrows():
        cedula = fila.get("NÚMERO DE DOCUMENTO", "SIN CÉDULA")
        for col in columnas_auditar:
            valor = fila.get(col)
            if pd.isna(valor) or str(valor).strip() == "":
                registros.append({"indice_fila": idx, "cedula": cedula, "campo_vacio": col})

    return pd.DataFrame(registros)

# --- Resumen para el dashboard (Tab 3) ---
def generar_resumen(f: dict) -> dict:
    """Corre las 6 reglas y devuelve un dict {nombre_caso: DataFrame} listo para graficar y filtrar."""
    general = f["general"]
    orientacion = f["orientacion_consolidado"]
    remisiones = f["remisiones"]
    enc_basico = f["encuesta_basico_jco"]
    enc_esp = f["encuesta_especializado"]

    diff_or = diff_orientados_vs_remitidos(orientacion, remisiones)
    diff_enc = diff_encuestados_vs_listos_reportar(orientacion, enc_basico, enc_esp)

    resultado = {
        "Leads sin gestión": leads_sin_gestion(general),
        "Leads en verificación": leads_en_verificacion(general),
        "Verificados sin reporte orientación": verificados_sin_reporte_orientacion(general, orientacion),
        "Formados sin orientar": formados_sin_orientar(general),
        "Orientados Esp. sin formación": orientados_especializado_sin_formacion(general),
        "Orientados sin remitir": diff_or["solo_orientados"],
        "Remitidos sin orientar": diff_or["solo_remitidos"],
        "Encuestados sin marcar listo": general[general["CC Prospecto"].apply(normalizar_cedula).isin(diff_enc["solo_encuestados"])],
        "Listos sin encuestar": diff_enc["solo_listos"],
    }
    return resultado

from column_mapping import (
    CAMPO_MOMENTO_BACKUP, CAMPO_ENTREGADO, META_TOTAL_BASICO,
    META_TOTAL_ESPECIALIZADO, META_TOTAL_PROGRAMA, MESES_ORDEN,
)
import datetime

def cargar_metas() -> pd.DataFrame:
    from bigquery_api import cargar_metas_bigquery
    df = cargar_metas_bigquery()
    for col in ["Básico", "Especializado", "Total"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df

def meta_acumulada(df_metas: pd.DataFrame, mes_actual: str, columna: str) -> float:
    """Suma la meta de esa columna desde Julio (inicio del programa en la tabla) hasta el mes actual."""
    if mes_actual not in MESES_ORDEN:
        return 0
    idx_actual = MESES_ORDEN.index(mes_actual)
    meses_validos = set(MESES_ORDEN[:idx_actual + 1])
    return df_metas[df_metas["Mes"].isin(meses_validos)][columna].sum()

def mes_actual_es() -> str:
    meses = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
             7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
    return meses[datetime.date.today().month]

def es_entregado(serie: pd.Series) -> pd.Series:
    """True solo si el valor contiene la palabra 'Reportado' (ej. 'Entregado P1 - Reportado')."""
    return serie.astype(str).str.contains("Reportado", case=False, na=False)

def resumen_looker(general: pd.DataFrame, df_metas: pd.DataFrame, excluir_entregados: bool = False, hito_filtro: str = "Todos") -> dict:
    mes_actual = mes_actual_es()

    df = general.copy()
    if excluir_entregados and CAMPO_ENTREGADO in df.columns:
        df = df[~es_entregado(df[CAMPO_ENTREGADO])]

    leads = len(df)
    matriculados = (df["Estado CRM"].astype(str).str.strip() == "Matriculado").sum()
    en_proceso = (df[CAMPO_MOMENTO_BACKUP].astype(str).str.strip() == "1.En verificación").sum()

    reporte = df["Reporte"].astype(str).str.strip()
    paquete = df["Paquete"].astype(str).str.strip().str.upper()
    finalizados_reporte = reporte.isin(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"])

    orientados = finalizados_reporte.sum()
    orientados_basicos = (finalizados_reporte & (paquete == "BÁSICO")).sum()
    orientados_especializados = (finalizados_reporte & (paquete == "ESPECIALIZADO")).sum()

    estado_form = df["Estado de la formación"].astype(str).str.strip().str.upper()
    formados_en_curso = (estado_form == "EN CURSO").sum()
    finalizados_formacion = estado_form.isin(["FINALIZADO", "CERTIFICADO"]).sum()

    verificados_monitoreo = (df["Verificación Calidad"].astype(str).str.strip().str.upper() == "TRUE").sum()
    revisados_calidad_orientacion = (df["Fecha Calidad Orientación"].notna() & (df["Fecha Calidad Orientación"].astype(str).str.strip() != "")).sum()

    if CAMPO_ENTREGADO in general.columns:
        cantidad_entregados = es_entregado(general[CAMPO_ENTREGADO]).sum()
    else:
        cantidad_entregados = 0

    meta_acum_basico = determinar_meta_denominador(hito_filtro, mes_actual, df_metas, "Básico")
    meta_acum_especializado = determinar_meta_denominador(hito_filtro, mes_actual, df_metas, "Especializado")
    meta_acum_total = determinar_meta_denominador(hito_filtro, mes_actual, df_metas, "Total")

    def pct(num, den):
        return round(100 * num / den, 2) if den else 0

    return {
        "mes_actual": mes_actual,
        "leads": leads,
        "matriculados": matriculados,
        "en_proceso": en_proceso,
        "orientados": orientados,
        "orientados_basicos": orientados_basicos,
        "orientados_especializados": orientados_especializados,
        "formados_en_curso": formados_en_curso,
        "finalizados_formacion": finalizados_formacion,
        "cantidad_entregados": cantidad_entregados,
        "avance_fecha_verificacion": pct(verificados_monitoreo, meta_acum_total),
        "avance_general_orientacion": pct(revisados_calidad_orientacion, meta_acum_total),
        "avance_general_formacion": pct(finalizados_formacion, meta_acum_especializado),
        "avance_entregas": pct(cantidad_entregados, META_TOTAL_PROGRAMA),
        "verificados_monitoreo": verificados_monitoreo,
        "revisados_calidad_orientacion": revisados_calidad_orientacion,
    }


def tabla_estados(general: pd.DataFrame, enc_basico: pd.DataFrame, enc_esp: pd.DataFrame,
                   excluir_entregados: bool = False, por_paquete: bool = False, cedulas_filtro: set = None) -> pd.DataFrame:
    df = general.copy()
    if excluir_entregados and CAMPO_ENTREGADO in df.columns:
        df = df[~es_entregado(df[CAMPO_ENTREGADO])]

    if cedulas_filtro is not None:
        enc_basico = enc_basico[enc_basico["CEDULA"].apply(normalizar_cedula).isin(cedulas_filtro)]
        enc_esp = enc_esp[enc_esp["CEDULA"].apply(normalizar_cedula).isin(cedulas_filtro)]

    paquete = df["Paquete"].astype(str).str.strip().str.upper()
    reporte = df["Reporte"].astype(str).str.strip()
    finalizados_reporte = reporte.isin(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"])
    estado_form = df["Estado de la formación"].astype(str).str.strip().str.upper()
    finalizados_formacion = estado_form.isin(["FINALIZADO", "CERTIFICADO"])
    matriculados = df["Estado CRM"].astype(str).str.strip() == "Matriculado"

    paquete_enc_basico = enc_basico["PAQUETE"].astype(str).str.strip().str.upper() if "PAQUETE" in enc_basico.columns else pd.Series(dtype=str)
    paquete_enc_esp = enc_esp["PAQUETE"].astype(str).str.strip().str.upper() if "PAQUETE" in enc_esp.columns else pd.Series(dtype=str)

    if not por_paquete:
        filas = [
            {"Etapa": "Verificación (Matriculados)", "Total": matriculados.sum()},
            {"Etapa": "Orientación", "Total": finalizados_reporte.sum()},
            {"Etapa": "Formación (Finalizada)", "Total": finalizados_formacion.sum()},
            {"Etapa": "Encuesta", "Total": len(enc_basico) + len(enc_esp)},
        ]
        return pd.DataFrame(filas)

    filas = [
        {
            "Etapa": "Verificación (Matriculados)",
            "Básico": (matriculados & (paquete == "BÁSICO")).sum(),
            "Especializado": (matriculados & (paquete == "ESPECIALIZADO")).sum(),
            "Total": matriculados.sum(),
        },
        {
            "Etapa": "Orientación",
            "Básico": (finalizados_reporte & (paquete == "BÁSICO")).sum(),
            "Especializado": (finalizados_reporte & (paquete == "ESPECIALIZADO")).sum(),
            "Total": finalizados_reporte.sum(),
        },
        {
            "Etapa": "Formación (Finalizada)",
            "Básico": None,  # Formación solo aplica a Especializado/JCO
            "Especializado": finalizados_formacion.sum(),
            "Total": finalizados_formacion.sum(),
        },
        {
            "Etapa": "Encuesta",
            "Básico": (paquete_enc_basico == "BÁSICO").sum(),
            "Especializado": (paquete_enc_esp == "ESPECIALIZADO").sum(),
            "Total": len(enc_basico) + len(enc_esp),
        },
    ]
    return pd.DataFrame(filas)

def serie_temporal(general: pd.DataFrame, columna_fecha: str, granularidad: str = "Diaria") -> pd.DataFrame:
    """Cuenta leads por fecha, agrupando diario o por semana calendario (lunes a domingo)."""
    fechas = pd.to_datetime(general[columna_fecha], dayfirst=True, errors="coerce").dropna()

    if granularidad == "Diaria":
        conteo = fechas.dt.date.value_counts().sort_index()
        df = conteo.reset_index()
        df.columns = ["Fecha", "Cantidad"]
    else:  # Semanal
        inicio_semana = (fechas - pd.to_timedelta(fechas.dt.weekday, unit="D")).dt.date
        conteo = inicio_semana.value_counts().sort_index()
        df = conteo.reset_index()
        df.columns = ["Fecha", "Cantidad"]
        df["Fecha"] = df["Fecha"].apply(lambda d: f"Semana del {d.strftime('%d/%m/%Y')}")

    return df

from contextlib import contextmanager

@contextmanager
def carga_personalizada(mensaje="Cargando..."):
    placeholder = st.empty()
    placeholder.markdown(f'''
        <div style="display:flex; align-items:center; gap:12px; padding:20px 0;">
            <div style="width:28px; height:28px; border:3px solid #EAEAEA; border-top:3px solid #FD531E;
                        border-radius:50%; animation: girar 0.8s linear infinite;"></div>
            <span style="color:#656A71; font-size:14px;">{mensaje}</span>
        </div>
        <style>
        @keyframes girar {{ 0% {{transform: rotate(0deg);}} 100% {{transform: rotate(360deg);}} }}
        </style>
    ''', unsafe_allow_html=True)
    try:
        yield
    finally:
        placeholder.empty()

def calcular_progreso_ruta(cedula_norm: str, general: pd.DataFrame,
                            orientacion: pd.DataFrame, enc_basico: pd.DataFrame, enc_esp: pd.DataFrame) -> dict:
    persona = general[general["cedula_norm"] == cedula_norm]
    if persona.empty:
        return None
    persona = persona.iloc[0]

    jco = normalizar_texto(persona.get("JCO"))
    paquete = normalizar_texto(persona.get("Paquete"))

    if jco == "SI":
        ruta = "JCO"
        etapas = ["Verificación", "Orientación", "Formación", "Remisión", "Encuesta"]
    elif paquete == "ESPECIALIZADO":
        ruta = "Especializado"
        etapas = ["Verificación", "Orientación", "Formación", "Remisión", "Mitigación", "Encuesta"]
    elif paquete == "BÁSICO":
        ruta = "Básico"
        etapas = ["Verificación", "Orientación", "Remisión", "Encuesta"]
    else:
        return {"ruta": "Sin clasificar todavía", "etapas": [], "completado": {}}

    completado = {}
    completado["Verificación"] = str(persona.get("Estado CRM", "")).strip() == "Matriculado"

    reporte = str(persona.get("Reporte", "")).strip()
    completado["Orientación"] = reporte in ["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"]

    if "Formación" in etapas:
        estado_formacion_persona = str(persona.get("Estado de la formación", "")).strip().upper()
        completado["Formación"] = estado_formacion_persona in ["FINALIZADO", "CERTIFICADO"]

    completado["Remisión"] = normalizar_texto(persona.get("Remitido")) == "SI"
    
    if "Mitigación" in etapas:
        completado["Mitigación"] = str(persona.get("Bono enviado", "")).strip().upper() == "SI"

    en_encuesta_basico = cedula_norm in set(enc_basico["CEDULA"].apply(normalizar_cedula).dropna())
    en_encuesta_esp = cedula_norm in set(enc_esp["CEDULA"].apply(normalizar_cedula).dropna())
    completado["Encuesta"] = en_encuesta_basico or en_encuesta_esp

    return {"ruta": ruta, "etapas": etapas, "completado": completado}

def html_diagrama_ruta(progreso: dict) -> str:
    if not progreso or not progreso["etapas"]:
        mensaje = progreso["ruta"] if progreso else "Cédula no encontrada en General"
        return f'<p style="color:#656A71;">{mensaje}</p>'

    total = len(progreso["etapas"])
    pasos_html = ""
    for i, etapa in enumerate(progreso["etapas"]):
        hecho = progreso["completado"].get(etapa, False)
        color = "#FD531E" if hecho else "#D9D9D9"
        texto_color = "#FFFFFF" if hecho else "#656A71"
        icono = "✓" if hecho else str(i + 1)

        paso = (
            f'<div style="display:flex; flex-direction:column; align-items:center; min-width:90px;">'
            f'<div style="width:38px; height:38px; border-radius:50%; background-color:{color}; '
            f'display:flex; align-items:center; justify-content:center; font-weight:bold; color:{texto_color};">'
            f'{icono}</div>'
            f'<div style="font-size:12px; color:#292929; margin-top:6px; text-align:center;">{etapa}</div>'
            f'</div>'
        )

        if i < total - 1:
            color_linea = "#FD531E" if hecho else "#D9D9D9"
            paso += f'<div style="flex:1; height:3px; background-color:{color_linea}; margin-top:19px;"></div>'

        pasos_html += paso

    return (
        f'<div style="margin:16px 0;">'
        f'<div style="font-size:13px; color:#656A71; margin-bottom:12px;">Ruta: '
        f'<b style="color:#292929;">{progreso["ruta"]}</b></div>'
        f'<div style="display:flex; align-items:flex-start;">{pasos_html}</div>'
        f'</div>'
    )

import datetime as dt

def calcular_prediccion(general: pd.DataFrame) -> dict:
    fecha_inicio = dt.date(2026, 7, 10)
    fecha_fin = dt.date(2026, 11, 30)
    hoy = dt.date.today()

    dias_totales = (fecha_fin - fecha_inicio).days
    dias_transcurridos = max(0, min((hoy - fecha_inicio).days, dias_totales))
    dias_restantes = max(0, (fecha_fin - hoy).days)
    pct_tiempo = round((dias_transcurridos / dias_totales) * 100, 1) if dias_totales else 0

    FESTIVOS_COLOMBIA_2026 = [
        "2026-10-12",  # Día de la Raza / Diversidad Étnica y Cultural
        "2026-11-02",  # Todos los Santos
        "2026-11-16",  # Independencia de Cartagena
    ]
    dias_habiles_restantes = int(np.busday_count(
        hoy.isoformat(), (fecha_fin + dt.timedelta(days=1)).isoformat(),
        holidays=FESTIVOS_COLOMBIA_2026,
    ))
    dias_habiles_restantes = max(dias_habiles_restantes, 1)  # evita división por cero al final del proyecto

    reporte = general["Reporte"].astype(str).str.strip()
    paquete = general["Paquete"].astype(str).str.strip().str.upper()
    estado_form = general["Estado de la formación"].astype(str).str.strip().str.upper()

    finalizados_reporte = reporte.isin(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"])
    avance_basico = (finalizados_reporte & (paquete == "BÁSICO")).sum()
    avance_especializado = estado_form.isin(["FINALIZADO", "CERTIFICADO"]).sum()
    avance_total = avance_basico + avance_especializado

    def construir(real, meta):
        esperado_num = round(meta * (pct_tiempo / 100))
        diferencia_num = real - esperado_num
        pct_real = round((real / meta) * 100, 1) if meta else 0
        faltan_meta = max(meta - real, 0)
        ritmo_diario_necesario = round(faltan_meta / dias_habiles_restantes, 1)
        return {
            "real": real, "meta": meta, "pct_real": pct_real,
            "esperado_num": esperado_num, "diferencia_num": diferencia_num,
            "ritmo_diario_necesario": ritmo_diario_necesario,
        }

    return {
        "hoy": hoy.strftime("%d/%m/%Y"),
        "dias_totales": dias_totales,
        "dias_restantes": dias_restantes,
        "dias_habiles_restantes": dias_habiles_restantes,
        "pct_tiempo": pct_tiempo,
        "basico": construir(avance_basico, META_TOTAL_BASICO),
        "especializado": construir(avance_especializado, META_TOTAL_ESPECIALIZADO),
        "total": construir(avance_total, META_TOTAL_PROGRAMA),
    }


def html_barra_prediccion(etiqueta: str, datos: dict) -> str:
    real_pct = datos["pct_real"]
    esperado_pct = round((datos["esperado_num"] / datos["meta"]) * 100, 1) if datos["meta"] else 0
    diferencia = datos["diferencia_num"]

    color_barra = "#FD531E" if diferencia >= 0 else "#821F0D"
    ancho_real = min(real_pct, 100)
    ancho_esperado = min(esperado_pct, 100)

    if diferencia >= 0:
        texto_dif = f"+{diferencia} adelante del ritmo esperado"
        color_dif = "#1E8E3E"
    else:
        texto_dif = f"{abs(diferencia)} personas atrás del ritmo esperado"
        color_dif = "#821F0D"

    return (
        f'<div style="margin-bottom:14px;">'
        f'<div style="display:flex; justify-content:space-between; font-size:12px; color:#656A71; margin-bottom:4px;">'
        f'<span><b style="color:#292929;">{etiqueta}</b> — {datos["real"]}/{datos["meta"]} ({real_pct}%)</span>'
        f'<span style="color:{color_dif}; font-weight:bold;">{texto_dif}</span>'
        f'</div>'
        f'<div style="position:relative; background-color:#EAEAEA; border-radius:4px; height:14px; width:100%;">'
        f'<div style="background-color:{color_barra}; width:{ancho_real}%; height:14px; border-radius:4px;"></div>'
        f'<div style="position:absolute; top:-3px; left:{ancho_esperado}%; width:2px; height:20px; background-color:#292929;"></div>'
        f'</div>'
        f'</div>'
    )


def html_franja_prediccion(pred: dict) -> str:
    barra_basico = html_barra_prediccion("Básico", pred["basico"])
    barra_especializado = html_barra_prediccion("Especializado", pred["especializado"])
    barra_total = html_barra_prediccion("Total", pred["total"])
    tarjetas_ritmo = html_tarjetas_ritmo(pred)

    return (
        f'<div style="background-color:#FFFFFF; border:1px solid #EAEAEA; border-radius:10px; padding:16px 20px; margin-bottom:16px;">'
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">'
        f'<span style="font-size:13px; color:#656A71;">Proyecto: 10/07/2026 — 30/11/2026 &nbsp;·&nbsp; Hoy: {pred["hoy"]}</span>'
        f'<span style="font-size:13px; color:#292929; font-weight:bold;">⏳ {pred["dias_restantes"]} días restantes &nbsp;|&nbsp; {pred["pct_tiempo"]}% del tiempo transcurrido</span>'
        f'</div>'
        f'{barra_basico}{barra_especializado}{barra_total}'
        f'<div style="font-size:11px; color:#656A71; margin-top:4px;">La línea negra marca dónde deberías estar según el tiempo transcurrido.</div>'
        f'{tarjetas_ritmo}'
        f'</div>'
    )

def html_tarjetas_ritmo(pred: dict) -> str:
    def tarjeta(etiqueta, datos, color):
        return (
            f'<div style="background-color:#FFFFFF; border-left:4px solid {color}; padding:14px 16px; '
            f'border-radius:8px; flex:1; box-shadow:0 1px 3px rgba(0,0,0,0.08);">'
            f'<div style="font-size:12px; color:#656A71; text-transform:uppercase;">{etiqueta}</div>'
            f'<div style="font-size:22px; color:#292929; font-weight:bold; margin-top:4px;">{datos["ritmo_diario_necesario"]} / día hábil</div>'
            f'<div style="font-size:11px; color:#656A71; margin-top:2px;">Faltan {datos["meta"] - datos["real"]} para la meta</div>'
            f'</div>'
        )

    return (
        f'<div style="margin-top:16px;">'
        f'<div style="font-size:13px; color:#656A71; margin-bottom:8px;">'
        f'Ritmo necesario para llegar a la meta el 30/11/2026 ({pred["dias_habiles_restantes"]} días hábiles restantes):</div>'
        f'<div style="display:flex; gap:12px;">'
        f'{tarjeta("Básico", pred["basico"], "#FD531E")}'
        f'{tarjeta("Especializado", pred["especializado"], "#821F0D")}'
        f'{tarjeta("Total", pred["total"], "#292929")}'
        f'</div>'
        f'</div>'
    )

def aplicar_filtros_generales(df: pd.DataFrame, paquete=None, estado=None, evento=None, hito=None) -> pd.DataFrame:
    resultado = df.copy()
    if paquete and paquete != "Todos":
        resultado = resultado[resultado["Paquete"] == paquete]
    if estado and estado != "Todos":
        resultado = resultado[resultado["Momento del proceso"] == estado]
    if evento and evento != "Todos":
        resultado = resultado[resultado["Evento/Base"] == evento]
    if hito and hito != "Todos":
        resultado = resultado[resultado["Hito"] == hito]
    return resultado

def meta_del_mes(df_metas: pd.DataFrame, mes: str, columna: str) -> float:
    """Meta de un solo mes (no acumulada)."""
    fila = df_metas[df_metas["Mes"] == mes]
    return fila[columna].sum() if not fila.empty else 0


def avance_por_mes(general: pd.DataFrame, orientacion_col_fecha: str, monitoreo_col_fecha: str,
                    mes_nombre: str, año: int, df_metas: pd.DataFrame) -> dict:
    meses_numero = {"Enero":1,"Febrero":2,"Marzo":3,"Abril":4,"Mayo":5,"Junio":6,
                     "Julio":7,"Agosto":8,"Septiembre":9,"Octubre":10,"Noviembre":11,"Diciembre":12}
    num_mes = meses_numero[mes_nombre]

    fecha_monitoreo = pd.to_datetime(general[monitoreo_col_fecha], dayfirst=True, errors="coerce")
    verificados_mes = ((general["Verificación Calidad"].astype(str).str.strip().str.upper() == "TRUE")
                        & (fecha_monitoreo.dt.month == num_mes) & (fecha_monitoreo.dt.year == año)).sum()

    fecha_orientacion = pd.to_datetime(general[orientacion_col_fecha], dayfirst=True, errors="coerce")
    orientados_mes = (general[orientacion_col_fecha].notna()
                       & (fecha_orientacion.dt.month == num_mes) & (fecha_orientacion.dt.year == año)).sum()

    meta_verif_mes = meta_del_mes(df_metas, mes_nombre, "Total")
    meta_orient_mes = meta_del_mes(df_metas, mes_nombre, "Total")

    def pct(num, den):
        return round((num / den) * 100, 1) if den else 0

    return {
        "verificados_mes": verificados_mes, "meta_verif_mes": meta_verif_mes,
        "pct_verif_mes": pct(verificados_mes, meta_verif_mes),
        "orientados_mes": orientados_mes, "meta_orient_mes": meta_orient_mes,
        "pct_orient_mes": pct(orientados_mes, meta_orient_mes),
    }

def determinar_meta_denominador(hito_filtro: str, mes_actual: str, df_metas: pd.DataFrame, columna: str) -> float:
    """
    Si el filtro de Hito es 'Reportado <Mes>' -> meta de ESE mes puntual.
    Si es 'En ruta' -> meta del mes en curso.
    Si es 'Todos' (sin filtro específico) -> meta acumulada a la fecha.
    """
    if hito_filtro and hito_filtro.startswith("Reportado "):
        mes_del_hito = hito_filtro.replace("Reportado ", "").strip()
        return meta_del_mes(df_metas, mes_del_hito, columna)
    elif hito_filtro == "En ruta":
        return meta_del_mes(df_metas, mes_actual, columna)
    else:
        return meta_acumulada(df_metas, mes_actual, columna)

# --- Gestión Documental / Evidencias SDDE ---

COLUMNAS_REQUISITOS = [
    "CÉDULA DE CIUDADANÍA ✓", "ADRES ✓", "ACJ ✓", "DJ ✓", "RENEC ✓", "VRD ✓",
    "SOPORTE DE RESIDENCIA ✓", "FORMACIÓN ✓", "SEGUIMIENTO REMISION ✓",
    "AUTOPOSTULACIÓN ✓", "ENCUESTA ✓", "MITIGACIÓN EN STC ✓",
]

def cargar_matriz_documental() -> pd.DataFrame:
    df, _ = cargar_fuente("matriz_documental")
    df["cedula_norm"] = df["CÉDULA"].apply(normalizar_cedula)
    df["% CUMPLIMIENTO_num"] = (
        df["% CUMPLIMIENTO"].astype(str).str.replace("%", "", regex=False).str.strip()
    )
    df["% CUMPLIMIENTO_num"] = pd.to_numeric(df["% CUMPLIMIENTO_num"], errors="coerce")
    return df


def resumen_cumplimiento_documental(matriz: pd.DataFrame) -> dict:
    total = len(matriz)
    completos = (matriz["% CUMPLIMIENTO_num"] == 100).sum()
    incompletos = total - completos
    promedio = round(matriz["% CUMPLIMIENTO_num"].mean(), 1) if total else 0

    distribucion = matriz["% CUMPLIMIENTO_num"].value_counts().sort_index().reset_index()
    distribucion.columns = ["% Cumplimiento", "Cantidad"]

    return {
        "total": total, "completos": completos, "incompletos": incompletos,
        "promedio": promedio, "distribucion": distribucion,
    }


def resumen_estado_remision(matriz: pd.DataFrame) -> pd.DataFrame:
    conteo = matriz["CONTROL DE REMISIÓN"].value_counts(dropna=False).reset_index()
    conteo.columns = ["Estado", "Cantidad"]
    conteo["Estado"] = conteo["Estado"].fillna("Sin estado registrado")
    return conteo


def lista_pendientes_por_responsable(matriz: pd.DataFrame) -> pd.DataFrame:
    tiene_observacion = matriz["OBSERVACIÓN GENERAL"].notna() & (matriz["OBSERVACIÓN GENERAL"].astype(str).str.strip() != "")
    pendientes = matriz[tiene_observacion].copy()

    def extraer_correo(texto):
        import re
        match = re.search(r"[\w\.-]+@[\w\.-]+", str(texto))
        return match.group(0) if match else "Sin correo identificado"

    pendientes["Responsable (correo)"] = pendientes["OBSERVACIÓN GENERAL"].apply(extraer_correo)
    columnas = ["CÉDULA", "NOMBRE COMPLETO", "PAQUETE", "% CUMPLIMIENTO", "CONTROL DE REMISIÓN", "OBSERVACIÓN GENERAL", "Responsable (correo)"]
    return pendientes[columnas].sort_values("Responsable (correo)")


def detectar_inconsistencias_documentales(matriz: pd.DataFrame) -> pd.DataFrame:
    """100% de cumplimiento pero con observación general pendiente = contradicción."""
    tiene_observacion = matriz["OBSERVACIÓN GENERAL"].notna() & (matriz["OBSERVACIÓN GENERAL"].astype(str).str.strip() != "")
    es_100 = matriz["% CUMPLIMIENTO_num"] == 100
    inconsistentes = matriz[tiene_observacion & es_100].copy()
    columnas = ["CÉDULA", "NOMBRE COMPLETO", "PAQUETE", "% CUMPLIMIENTO", "CONTROL DE REMISIÓN", "OBSERVACIÓN GENERAL"]
    return inconsistentes[columnas]


def buscar_persona_matriz(matriz: pd.DataFrame, cedula_norm: str) -> pd.DataFrame:
    return matriz[matriz["cedula_norm"] == cedula_norm]

def cargar_matriz_documental_con_filas():
    """Igual que cargar_matriz_documental pero conserva la fila real de la hoja para poder escribir."""
    df, fila_header = cargar_fuente("matriz_documental")
    df["cedula_norm"] = df["CÉDULA"].apply(normalizar_cedula)
    df["% CUMPLIMIENTO_num"] = pd.to_numeric(
        df["% CUMPLIMIENTO"].astype(str).str.replace("%", "", regex=False).str.strip(), errors="coerce"
    )
    df["fila_sheet"] = fila_header + 2 + df.index  # fila real 1-indexed en Google Sheets
    return df


def filtrar_por_documento_y_estado(matriz: pd.DataFrame, columna_documento: str, estado: str = None) -> pd.DataFrame:
    resultado = matriz.copy()
    resultado = resultado[resultado["CÉDULA"].notna() & (resultado["CÉDULA"].astype(str).str.strip() != "")]
    if estado and estado != "Todos":
        resultado = resultado[resultado[columna_documento].astype(str).str.strip() == estado]
    return resultado

def es_valor_verdadero(valor) -> bool:
    return str(valor).strip().upper() in ("TRUE", "VERDADERO", "SI", "SÍ", "1")

def datos_grafica_documentos(matriz: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for col in COLUMNAS_REQUISITOS:
        valores = matriz[col].apply(es_valor_verdadero)
        cargados = int(valores.sum())
        no_cargados = int(len(matriz) - cargados)
        nombre_doc = col.replace(" ✓", "")
        filas.append({"Documento": nombre_doc, "Estado": "Cargado", "Cantidad": cargados})
        filas.append({"Documento": nombre_doc, "Estado": "No cargado", "Cantidad": no_cargados})
    return pd.DataFrame(filas)


def tabla_editable_documentos(matriz: pd.DataFrame) -> pd.DataFrame:
    columnas_base = ["fila_sheet", "CÉDULA", "NOMBRE COMPLETO", "PAQUETE"]
    df = matriz[columnas_base].copy()
    for col in COLUMNAS_REQUISITOS:
        df[col.replace(" ✓", "")] = matriz[col].apply(es_valor_verdadero)
    return df.reset_index(drop=True)

def datos_formacion_apilada(general: pd.DataFrame) -> pd.DataFrame:
    estado_form = general["Estado de la formación"].astype(str).str.strip().str.upper()
    conteo = estado_form[estado_form.isin(["FINALIZADO", "CERTIFICADO", "EN CURSO"])].value_counts()
    df = pd.DataFrame([{"Formación": "Formación", "Estado": estado, "Cantidad": int(cant)} for estado, cant in conteo.items()])
    return df

def serie_orientacion_filtrada(general: pd.DataFrame, granularidad: str = "Semanal") -> pd.DataFrame:
    """Solo cuenta fechas de personas cuyo Reporte es FINALIZADO/FINALIZADO PENDIENTE X REMISIÓN (mismo criterio del KPI)."""
    reporte = general["Reporte"].astype(str).str.strip()
    filtrado = general[reporte.isin(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"])]
    return serie_temporal(filtrado, "Fecha Orientación", granularidad)

# =========================================================
# Seguimiento Individual
# =========================================================

META_VERIFICACION_LINEA = 17   
META_ORIENTACION_LINEA = 8   
META_FORMACION_LINEA = 20      

@st.cache_data(ttl=600)
def cargar_formacion_consolidado_cache():
    df, _ = cargar_fuente("formacion_consolidado")
    return df


def serie_lineal_por_grupo(df: pd.DataFrame, columna_grupo: str, columna_fecha: str, granularidad: str = "Semanal") -> pd.DataFrame:
    temp = df.copy()
    temp["_fecha_parsed"] = pd.to_datetime(temp[columna_fecha], format="mixed", dayfirst=True, errors="coerce")
    temp = temp.dropna(subset=["_fecha_parsed"])
    temp = temp[temp[columna_grupo].notna() & (temp[columna_grupo].astype(str).str.strip() != "")]

    if granularidad == "Semanal":
        temp["Periodo"] = (temp["_fecha_parsed"] - pd.to_timedelta(temp["_fecha_parsed"].dt.weekday, unit="D")).dt.date
    else:
        temp["Periodo"] = temp["_fecha_parsed"].dt.date

    resultado = temp.groupby(["Periodo", columna_grupo]).size().reset_index(name="Cantidad")
    return resultado


def tabla_resumen_calidad(df: pd.DataFrame, columna_grupo: str, serie_calidad: pd.Series) -> pd.DataFrame:
    temp = df.copy()
    temp["_calidad"] = serie_calidad.values
    resumen = temp.groupby(columna_grupo)["_calidad"].agg(["sum", "count"]).reset_index()
    resumen.columns = [columna_grupo, "Verificado por calidad", "Total"]
    resumen["Sin verificar por calidad"] = resumen["Total"] - resumen["Verificado por calidad"]
    return resumen[[columna_grupo, "Verificado por calidad", "Sin verificar por calidad"]].sort_values(columna_grupo)


def tabla_resumen_formacion(df: pd.DataFrame) -> pd.DataFrame:
    estado = df["ESTADO DE LA FORMACIÓN"].astype(str).str.strip().str.upper()
    temp = df.copy()
    temp["_inscrito"] = (estado == "INSCRITO").astype(int)
    temp["_en_curso"] = (estado == "EN CURSO").astype(int)
    temp["_finalizado"] = estado.isin(["FINALIZADO", "CERTIFICADO"]).astype(int)
    resumen = temp.groupby("Responsable")[["_inscrito", "_en_curso", "_finalizado"]].sum().reset_index()
    resumen.columns = ["Responsable", "Inscritos", "En curso", "Finalizados/Certificados"]
    return resumen.sort_values("Responsable")


def datos_barras_estado_formacion(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    temp["Estado"] = temp["ESTADO DE LA FORMACIÓN"].fillna("Sin estado")
    temp = temp[temp["Responsable"].notna() & (temp["Responsable"].astype(str).str.strip() != "")]
    return temp.groupby(["Responsable", "Estado"]).size().reset_index(name="Cantidad")


def _clasificar_cuartil(valor) -> str:
    try:
        v = float(str(valor).replace("%", "").replace(",", ".").strip())
    except (ValueError, TypeError):
        return None
    if pd.isna(v):
        return None
    if v <= 25:
        return "0% - 25%"
    elif v <= 50:
        return "25% - 50%"
    elif v <= 75:
        return "50% - 75%"
    else:
        return "75% - 100%"


def datos_barras_cuartiles(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    temp["Cuartil"] = temp["% AVANCE PLAT"].apply(_clasificar_cuartil)
    temp = temp.dropna(subset=["Cuartil"])
    temp = temp[temp["Responsable"].notna() & (temp["Responsable"].astype(str).str.strip() != "")]
    return temp.groupby(["Responsable", "Cuartil"]).size().reset_index(name="Cantidad")