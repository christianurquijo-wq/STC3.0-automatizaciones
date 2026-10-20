# reportes.py
import os
import smtplib
import streamlit as st
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

def _credenciales_gmail():
    try:
        usuario = st.secrets["GMAIL_USER"]
        clave = st.secrets["GMAIL_APP_PASSWORD"]
    except Exception:
        usuario = os.getenv("GMAIL_USER")
        clave = os.getenv("GMAIL_APP_PASSWORD")
    return usuario, clave


def _fila_kpi(etiqueta, valor, destacado=False):
    color_valor = "#FD531E" if destacado else "#292929"
    return f'''
        <tr>
            <td style="padding:8px; border-bottom:1px solid #eee; color:#656A71;">{etiqueta}</td>
            <td style="padding:8px; border-bottom:1px solid #eee; font-weight:bold; color:{color_valor};">{valor}</td>
        </tr>
    '''


def _barra_horizontal(etiqueta, valor, maximo, color="#FD531E"):
    ancho = round((valor / maximo) * 100, 1) if maximo else 0
    return f'''
        <tr>
            <td style="padding:6px 10px 6px 0; font-size:12px; color:#656A71; width:180px; white-space:nowrap;">{etiqueta}</td>
            <td style="padding:6px 0;">
                <table style="width:100%; border-collapse:collapse;"><tr>
                    <td style="background-color:{color}; width:{ancho}%; height:14px; border-radius:3px;"></td>
                    <td style="width:{100-ancho}%;"></td>
                </tr></table>
            </td>
            <td style="padding:6px 0 6px 10px; font-size:12px; font-weight:bold; color:#292929; text-align:right; width:50px;">{valor}</td>
        </tr>
    '''


def _tabla_barras(titulo, df: pd.DataFrame, col_etiqueta: str, col_valor: str, color="#FD531E") -> str:
    if df.empty:
        return f'<h3 style="color:#292929; margin-top:24px;">{titulo}</h3><p style="color:#656A71; font-size:13px;">Sin datos disponibles.</p>'
    maximo = df[col_valor].max()
    filas = "".join(_barra_horizontal(str(row[col_etiqueta]), row[col_valor], maximo, color) for _, row in df.iterrows())
    return f'''
        <h3 style="color:#292929; margin-top:24px;">{titulo}</h3>
        <table style="width:100%; border-collapse:collapse;">{filas}</table>
    '''


def _tabla_estados_html(tabla: pd.DataFrame) -> str:
    encabezados = "".join(f'<th style="padding:8px; text-align:left; border-bottom:2px solid #292929; font-size:12px; color:#656A71;">{c}</th>' for c in tabla.columns)
    filas = ""
    for _, row in tabla.iterrows():
        def _fmt(v):
            if pd.isna(v):
                return ""
            if isinstance(v, float) and v.is_integer():
                return int(v)
            return v
        celdas = "".join(f'<td style="padding:8px; border-bottom:1px solid #eee; font-size:13px;">{_fmt(v)}</td>' for v in row)
        filas += f"<tr>{celdas}</tr>"
    return f'''
        <h3 style="color:#292929; margin-top:24px;">Tabla de procesos por etapa</h3>
        <table style="width:100%; border-collapse:collapse;">
            <tr>{encabezados}</tr>
            {filas}
        </table>
    '''


def construir_html_completo(r: dict, tabla_estados_df: pd.DataFrame, conteo_momento_df: pd.DataFrame, series: dict, pred: dict, formacion_estado_df: pd.DataFrame, filtros_texto: str = "") -> str:
    kpis = "".join([
        _fila_kpi("Leads en CRM", r["leads"]),
        _fila_kpi("Matriculados CRM", r["matriculados"]),
        _fila_kpi("En proceso (Verificación)", r["en_proceso"]),
        _fila_kpi("Verificados por Monitoreo", r["verificados_monitoreo"]),
        _fila_kpi("Avance a la fecha (Verificación)", f"{r['avance_fecha_verificacion']}%", destacado=True),
        _fila_kpi("Orientados (Total)", r["orientados"]),
        _fila_kpi("Orientados Básicos", r["orientados_basicos"]),
        _fila_kpi("Orientados Especializados", r["orientados_especializados"]),
        _fila_kpi("Revisados Calidad Orientación", r["revisados_calidad_orientacion"]),
        _fila_kpi("Avance Orientación (meta total 5102)", f"{r['avance_general_orientacion']}%", destacado=True),
        _fila_kpi("Formación en curso", r["formados_en_curso"]),
        _fila_kpi("Formación finalizada", r["finalizados_formacion"]),
        _fila_kpi("Avance Formación (meta Especializado)", f"{r['avance_general_formacion']}%", destacado=True),
        _fila_kpi("Cantidad entregados", r["cantidad_entregados"]),
        _fila_kpi("Avance Entregas (meta total 5102)", f"{r['avance_entregas']}%", destacado=True),
    ])

    tabla_html = _tabla_estados_html(tabla_estados_df)
    prediccion_html = _tabla_prediccion_html(pred)
    momento_html = _tabla_barras("Momento del proceso (Back UP)", conteo_momento_df, "Etapa", "Cantidad", color="#292929")

    verificacion_html = _tabla_barras("Evolución — Verificación (por semana)", series["verificacion"], "Fecha", "Cantidad", color="#FD531E")
    orientacion_html = _tabla_barras("Evolución — Orientación (por semana)", series["orientacion"], "Fecha", "Cantidad", color="#821F0D")
    formacion_html = _tabla_barras("Evolución — Formación (por semana)", series["formacion"], "Fecha", "Cantidad", color="#656A71")
    formacion_estado_html = _tabla_barras("Formación por estado (Finalizado / Certificado / En curso)", formacion_estado_df, "Estado", "Cantidad", color="#c32e13")

    return f'''
    <html><body style="font-family: Arial, sans-serif; color:#292929; max-width:700px; margin:0 auto;">
        <h2 style="color:#FD531E; border-bottom:3px solid #FD531E; padding-bottom:8px;">Avance STC 3.0</h2>
        {f'<p style="color:#656A71; font-size:12px; margin-top:-4px;">Filtros aplicados: {filtros_texto}</p>' if filtros_texto else ''}

        <table style="width:100%; border-collapse:collapse; margin-top:12px;">{kpis}</table>

        {tabla_html}
        {prediccion_html}
        {momento_html}
        {verificacion_html}
        {orientacion_html}
        {formacion_html}
        {formacion_estado_html}

        <p style="color:#656A71; font-size:11px; margin-top:30px; border-top:1px solid #eee; padding-top:12px;">
            Generado automáticamente desde el Dashboard de Control de Calidad STC 3.0.
        </p>
    </body></html>
    '''


def enviar_reporte(destinatarios: list, r: dict, tabla_estados_df: pd.DataFrame, conteo_momento_df: pd.DataFrame, series: dict, pred: dict, formacion_estado_df: pd.DataFrame, filtros_texto: str = "") -> tuple:
    """Envía el reporte HTML completo (sin adjuntos). Retorna (exito: bool, mensaje: str)."""
    usuario, clave = _credenciales_gmail()
    if not usuario or not clave:
        return False, "Faltan las credenciales de Gmail (GMAIL_USER / GMAIL_APP_PASSWORD)."

    msg = MIMEMultipart("alternative")
    msg["From"] = usuario
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = f"Avance STC 3.0"
    msg.attach(MIMEText(construir_html_completo(r, tabla_estados_df, conteo_momento_df, series, pred, formacion_estado_df, filtros_texto), "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(usuario, clave)
            server.sendmail(usuario, destinatarios, msg.as_string())
        return True, f"Reporte enviado a {len(destinatarios)} destinatario(s)."
    except Exception as e:
        return False, f"Error al enviar: {e}"

def enviar_tabla_generica(destinatarios: list, titulo: str, tabla: pd.DataFrame) -> tuple:
    usuario, clave = _credenciales_gmail()
    if not usuario or not clave:
        return False, "Faltan las credenciales de Gmail."

    from email.mime.application import MIMEApplication
    msg = MIMEMultipart()
    msg["From"] = usuario
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = titulo

    cuerpo = f'''
        <html><body style="font-family: Arial, sans-serif; color:#292929;">
            <h3 style="color:#FD531E;">{titulo}</h3>
            <p style="color:#656A71;">Se adjunta el detalle en formato CSV — {len(tabla)} registros.</p>
        </body></html>
    '''
    msg.attach(MIMEText(construir_html_completo(r, tabla_estados_df, conteo_momento_df, series, pred, formacion_estado_df, filtros_texto), "html"))

    import io
    buffer = io.StringIO()
    tabla.to_csv(buffer, index=False, encoding="utf-8-sig")
    adjunto = MIMEApplication(buffer.getvalue().encode("utf-8-sig"), Name="detalle.csv")
    adjunto["Content-Disposition"] = 'attachment; filename="detalle.csv"'
    msg.attach(adjunto)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(usuario, clave)
            server.sendmail(usuario, destinatarios, msg.as_string())
        return True, f"Tabla enviada a {len(destinatarios)} destinatario(s)."
    except Exception as e:
        return False, f"Error al enviar: {e}"

def _tabla_prediccion_html(pred: dict) -> str:
    def fila_paquete(etiqueta, datos):
        color = "#1E8E3E" if datos["diferencia_num"] >= 0 else "#821F0D"
        texto_dif = f"+{datos['diferencia_num']}" if datos["diferencia_num"] >= 0 else f"{datos['diferencia_num']}"
        return (
            f'<tr>'
            f'<td style="padding:8px; border-bottom:1px solid #eee; color:#656A71;">{etiqueta}</td>'
            f'<td style="padding:8px; border-bottom:1px solid #eee; font-weight:bold;">{datos["real"]}/{datos["meta"]} ({datos["pct_real"]}%)</td>'
            f'<td style="padding:8px; border-bottom:1px solid #eee; font-weight:bold; color:{color};">{texto_dif} vs esperado</td>'
            f'<td style="padding:8px; border-bottom:1px solid #eee;">{datos["ritmo_diario_necesario"]}/día hábil</td>'
            f'</tr>'
        )

    filas = fila_paquete("Básico", pred["basico"]) + fila_paquete("Especializado", pred["especializado"]) + fila_paquete("Total", pred["total"])

    return (
        f'<h3 style="color:#292929; margin-top:24px;">Avance general del proyecto</h3>'
        f'<p style="font-size:12px; color:#656A71;">Proyecto: 10/07/2026 — 30/11/2026 · Hoy: {pred["hoy"]} · '
        f'{pred["dias_restantes"]} días restantes ({pred["pct_tiempo"]}% del tiempo transcurrido)</p>'
        f'<table style="width:100%; border-collapse:collapse;">'
        f'<tr><th style="padding:8px; text-align:left; border-bottom:2px solid #292929; font-size:12px; color:#656A71;">Paquete</th>'
        f'<th style="padding:8px; text-align:left; border-bottom:2px solid #292929; font-size:12px; color:#656A71;">Real/Meta</th>'
        f'<th style="padding:8px; text-align:left; border-bottom:2px solid #292929; font-size:12px; color:#656A71;">vs. Ritmo esperado</th>'
        f'<th style="padding:8px; text-align:left; border-bottom:2px solid #292929; font-size:12px; color:#656A71;">Ritmo necesario</th></tr>'
        f'{filas}'
        f'</table>'
    )