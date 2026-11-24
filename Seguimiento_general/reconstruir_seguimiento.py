"""
Reconstruye «SEGUIMIENTO GENERAL» (Seguimiento General STC 3.0) con Python, sin fórmulas.

Por qué (nov-2026): la hoja tenía ~60 ARRAYFORMULA con MAP/LAMBDA/XLOOKUP sobre 8.300 filas, cada una buscando en
columnas completas de pestañas que a su vez son IMPORTRANGE de otros 4 archivos (Orientación A6:DH = 112 columnas).
Google no alcanzaba a recalcular: «Cargando…», #REF! y valores viejos.

Qué hace:
  1. Lee las fuentes DIRECTO de sus archivos (no de las pestañas IMPORT): Verificación, Consolidado FCS
     (orientación), Consolidado de formación y Modelo n8n (remisiones). Si la cuenta de servicio no tiene acceso a
     alguno, usa la pestaña IMPORT equivalente del mismo Seguimiento y lo avisa.
  2. Reporte CRM y Reporte SIS: consulta BigQuery (reportes_bigquery.py) y, en modo real, reescribe esas pestañas.
     Lee del Seguimiento: Reporte Atendidos/Pendientes STC, Parámetros y Base JCO.
  3. Calcula todas las columnas con motor_seguimiento.calcular() (mismas reglas que las fórmulas).
  4. Agrega al final las cédulas de Orientación/Verificación que faltaban (antes: CONTROL DE FALTANTES).
  5. Escribe SOLO valores:
       --destino prueba (por defecto): la tabla completa en la pestaña «SEGUIMIENTO GENERAL (script)» para
         compararla con la actual sin tocar nada.
       --destino real: reescribe las columnas calculadas de «SEGUIMIENTO GENERAL» desde la fila 5 (las columnas
         manuales —A, D, F, AI, AP, AQ, AR, AV, BD, BG, BL, BM— no se tocan). Al escribir sobre las celdas ancla,
         las ARRAYFORMULA desaparecen. Para volver atrás: Archivo › Historial de versiones.

Uso:
    python reconstruir_seguimiento.py                 # prueba
    python reconstruir_seguimiento.py --destino real
    python reconstruir_seguimiento.py --sin-nuevas    # no agrega cédulas faltantes
Panel: reconstruir_seguimiento_real.py corre el modo real (para el botón del Panel / programación diaria).

Configuración (STC/.env, viaja en SECRETS_BUNDLE): SHEET_ID_GENERAL, SHEET_ID_VERIFICACION,
SHEET_ID_CONSOLIDADO_FCS, SHEET_ID_FORMACION, SHEET_ID_REMISIONES. Credenciales: credenciales.json (raíz del repo).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import gspread
import pandas as pd
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound

sys.path.insert(0, str(Path(__file__).resolve().parent))
import motor_seguimiento as M  # noqa: E402

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
load_dotenv(RAIZ / ".env", override=True)

HOJA = "SEGUIMIENTO GENERAL"
HOJA_PRUEBA = "SEGUIMIENTO GENERAL (script)"
FILA_DATOS = 5  # los datos empiezan en la fila 5 (fila 4 = encabezados)
LEER = {"valueRenderOption": "UNFORMATTED_VALUE", "dateTimeRenderOption": "FORMATTED_STRING"}

# Fuentes externas: (variable del .env, rango en el archivo de origen, pestaña IMPORT de respaldo en el Seguimiento)
EXTERNAS = {
    "Verificación IMPORT": ("SHEET_ID_VERIFICACION", "General!A2:AX", "Verificación IMPORT!A1:AX"),
    "Orientación IMPORT": ("SHEET_ID_CONSOLIDADO_FCS", "CONSOLIDADO!A6:DH", "Orientación IMPORT!A1:DH"),
    "Formación Import": ("SHEET_ID_FORMACION", "CONSOLIDADO!A1:BB", "Formación Import!A1:AP"),
}
INTERNAS = {"Reporte CRM": "Reporte CRM!A1:Z", "Reporte SIS": "Reporte SIS!A1:Z",
            "Reporte Atendidos STC": "Reporte Atendidos STC!A1:Z",
            "Reporte Pendientes STC": "Reporte Pendientes STC!A1:Z", "Parámetros": "Parámetros!A1:O",
            "Base JCO": "Base JCO!A1:K"}
HOJA_AUDITORIA = "AUDITORÍA JCO"


def log(msg: str) -> None:
    print(f"[seguimiento] {msg}", flush=True)


def reintentos(funcion, intentos: int = 5):
    """Google responde 429/5xx con hojas grandes: espera creciente (15, 30, 60, 120 s)."""
    for n in range(intentos):
        try:
            return funcion()
        except APIError as e:
            codigo = getattr(e.response, "status_code", 0)
            if codigo not in (429, 500, 502, 503, 504) or n == intentos - 1:
                raise
            espera = 15 * 2 ** n
            log(f"Google respondió {codigo}; reintento {n + 1} en {espera} s")
            time.sleep(espera)


def cliente() -> gspread.Client:
    ruta = next((p for p in (AQUI / "credenciales.json", RAIZ / "credenciales.json") if p.exists()), None)
    if ruta is None:
        sys.exit("No encuentro credenciales.json (raíz del repo STC).")
    cred = Credentials.from_service_account_file(str(ruta), scopes=[
        "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.readonly"])
    global CREDENCIALES
    CREDENCIALES = cred
    return gspread.authorize(cred)


CREDENCIALES = None


def hitos_de_pago(gc: gspread.Client, avisos: list[str]):
    """Lee la carpeta «5.4 Entregas Mensuales» (FOLDER_ENTREGAS_MENSUALES en .env, o la carpeta conocida).
    Para probar con una copia local: ENTREGAS_LOCAL=<ruta de la carpeta descargada>."""
    import entregas_pago as E
    from google.auth.transport.requests import AuthorizedSession
    local = os.getenv("ENTREGAS_LOCAL", "").strip() or None
    carpeta = os.getenv("FOLDER_ENTREGAS_MENSUALES", "").strip() or E.CARPETA_ENTREGAS
    log("Entregas mensuales: " + (f"copia local {local}" if local else f"carpeta de Drive {carpeta}"))
    try:
        archivos = E.leer_archivos(M.norm_doc, sesion=None if local else AuthorizedSession(CREDENCIALES),
                                   carpeta=carpeta, local=local, log=lambda m: log(m))
    except Exception as e:  # noqa: BLE001 -- sin la carpeta, BH se deja como estaba
        avisos.append(f"Entregas mensuales: no se pudo leer la carpeta ({type(e).__name__}: {str(e)[:160]}); "
                      "la columna BH «Hito» no se actualizó")
        return None, {}, []
    if not any(a.tipo == "APROBADOS" for a in archivos):
        avisos.append("Entregas mensuales: no encontré archivos «Aprobados»; BH no se actualizó")
        return None, {}, archivos
    aprob, elim = E.hitos(archivos)
    log(f"Aprobados por pago: {pd.Series(list(aprob.values())).value_counts().sort_index().to_dict()}")
    return aprob, elim, archivos


def leer_rangos(libro: gspread.Spreadsheet, rangos: list[str]) -> list[list[list]]:
    r = reintentos(lambda: libro.values_batch_get(rangos, params=LEER))
    return [v.get("values", []) for v in r.get("valueRanges", [])]


def formacion_como_import(filas: list[list]) -> list[list]:
    """El Seguimiento importaba del consolidado de formación A:AH + AP:AT (→ AJ:AN) + AO (→ AO) + BB (→ AP).
    Se arma la misma forma para que el motor use las mismas letras que las fórmulas."""
    def col(r, letra):
        i = M.letra(letra)
        return r[i] if i < len(r) else ""
    salida = []
    for r in filas:
        base = list(r[:34]) + [""] * (34 - len(r[:34]))            # A:AH
        base += [""]                                                # AI (era un conteo de control)
        base += [col(r, c) for c in ("AP", "AQ", "AR", "AS", "AT")]  # AJ:AN
        base += [col(r, "AO"), col(r, "BB")]                        # AO, AP
        salida.append(base)
    return salida


def leer_fuentes(gc: gspread.Client, seg: gspread.Spreadsheet) -> tuple[dict, pd.DataFrame | None, list[str], dict]:
    fuentes, avisos = {}, []
    # Reporte CRM y Reporte SIS: directo de BigQuery (antes los pegaba un flujo de n8n). Si falla, se usan las
    # pestañas tal como estén y se avisa.
    import reportes_bigquery as RB
    reportes = {}
    try:
        reportes = RB.consultar(RAIZ, log=log)
        for nombre, filas in reportes.items():
            fuentes[nombre] = M.tabla(filas)
            log(f"{nombre}: {len(filas) - 1} filas desde BigQuery")
    except Exception as e:  # noqa: BLE001
        avisos.append(f"BigQuery: {type(e).__name__}: {str(e)[:200]} · se usaron las pestañas Reporte CRM/SIS")
        reportes = {}
    for nombre, (var, rango, respaldo) in EXTERNAS.items():
        filas = None
        sid = os.getenv(var, "").strip()
        if sid:
            try:
                filas = leer_rangos(reintentos(lambda: gc.open_by_key(sid)), [rango])[0]
                if nombre == "Formación Import":
                    filas = formacion_como_import(filas)
                log(f"{nombre}: {len(filas) - 1} filas desde el archivo de origen")
            except (APIError, SpreadsheetNotFound, PermissionError) as e:
                avisos.append(f"{nombre}: sin acceso al origen ({type(e).__name__}); se usó la pestaña IMPORT")
        if filas is None:
            filas = leer_rangos(seg, [respaldo])[0]
            log(f"{nombre}: {len(filas) - 1} filas desde la pestaña IMPORT del Seguimiento")
        fuentes[nombre] = M.tabla(filas)
    internas = {n: r for n, r in INTERNAS.items() if n not in fuentes}
    for nombre, filas in zip(internas, leer_rangos(seg, list(internas.values()))):
        fuentes[nombre] = M.tabla(filas)
        log(f"{nombre}: {len(filas) - 1} filas")
    # Fórmulas de Parámetros (col. M): dicen qué hitos cuenta cada fila para el factor de la col. BK.
    r = reintentos(lambda: seg.values_batch_get([INTERNAS["Parámetros"]], params={"valueRenderOption": "FORMULA"}))
    fuentes["Parámetros fórmulas"] = M.tabla(r["valueRanges"][0].get("values", []))
    remisiones = None
    sid = os.getenv("SHEET_ID_REMISIONES", "").strip()
    if sid:
        try:
            remisiones = M.tabla(leer_rangos(reintentos(lambda: gc.open_by_key(sid)), ["Modelo n8n!A1:W"])[0])
            log(f"Remisiones (Modelo n8n): {len(remisiones)} filas")
        except (APIError, SpreadsheetNotFound, PermissionError) as e:
            avisos.append(f"Remisiones: sin acceso a «Modelo n8n» ({type(e).__name__}); la columna Remitido no se "
                          "actualiza")
    return fuentes, remisiones, avisos, reportes


def leer_base(seg: gspread.Spreadsheet) -> pd.DataFrame:
    ancho = len(M.ENCABEZADOS)
    ultima = M.get_column_letter(ancho)
    filas = leer_rangos(seg, [f"{HOJA}!A{FILA_DATOS}:{ultima}"])[0]
    df = pd.DataFrame([list(r[:ancho]) + [""] * (ancho - len(r[:ancho])) for r in filas],
                      columns=[M.get_column_letter(i + 1) for i in range(ancho)]).fillna("")
    # Las filas sin cédula al final de la hoja se descartan; las de en medio se conservan (no se mueve nada).
    con_doc = df.index[df["F"].map(M.norm_doc) != ""]
    return df.loc[: con_doc.max()] if len(con_doc) else df.iloc[0:0]


def celda(v):
    """Valor listo para la API: números como número, fechas/textos como texto (USER_ENTERED los interpreta como
    lo haría una persona que escribe en la hoja). Nunca se escribe una fórmula."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else float(v)
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    s = str(v)
    return "'" + s if s[:1] in ("=", "+") else s


def bloques_calculados() -> list[tuple[str, str]]:
    """Rangos contiguos de columnas calculadas (se saltan las manuales)."""
    letras = [M.get_column_letter(i + 1) for i in range(len(M.ENCABEZADOS))]
    bloques, actual = [], []
    for c in letras:
        if c in M.MANUALES:
            if actual:
                bloques.append((actual[0], actual[-1]))
            actual = []
        else:
            actual.append(c)
    if actual:
        bloques.append((actual[0], actual[-1]))
    return bloques


def escribir_prueba(seg: gspread.Spreadsheet, tabla: pd.DataFrame) -> None:
    ancho = len(M.ENCABEZADOS)
    try:
        ws = seg.worksheet(HOJA_PRUEBA)
        reintentos(lambda: ws.clear())
    except gspread.WorksheetNotFound:
        ws = reintentos(lambda: seg.add_worksheet(HOJA_PRUEBA, rows=len(tabla) + 10, cols=ancho))
    if ws.row_count < len(tabla) + 5:
        reintentos(lambda: ws.resize(rows=len(tabla) + 10))
    valores = [M.ENCABEZADOS] + [[celda(v) for v in fila] for fila in tabla.itertuples(index=False)]
    reintentos(lambda: ws.update(range_name="A1", values=valores, value_input_option="USER_ENTERED"))
    log(f"Escrito en «{HOJA_PRUEBA}»: {len(tabla)} filas × {ancho} columnas")


def _plano(t) -> str:
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s*\(\d+\)$", "", re.sub(r"\s+", " ", t)).strip()


def validar_encabezados(seg: gspread.Spreadsheet) -> None:
    """Modo real: el script escribe por POSICIÓN (columna B, C, …). Si alguien insertó o movió una columna, la fila
    4 ya no coincide y se detiene antes de escribir, para no poner datos en la columna equivocada."""
    fila4 = leer_rangos(seg, [f"{HOJA}!A4:{M.get_column_letter(len(M.ENCABEZADOS))}4"])[0]
    actual = (fila4[0] if fila4 else []) + [""] * len(M.ENCABEZADOS)
    distintos = [f"{M.get_column_letter(i + 1)}: hoja «{a}» ≠ esperado «{e}»"
                 for i, (a, e) in enumerate(zip(actual, M.ENCABEZADOS)) if _plano(a) != _plano(e)]
    if distintos:
        sys.exit("Los encabezados de la fila 4 no coinciden con las columnas que escribe el script; no se escribió "
                 "nada.\n  " + "\n  ".join(distintos[:15]))
    log("Encabezados de la fila 4 verificados (A:BT)")


def escribir_auditoria(seg: gspread.Spreadsheet, aud: pd.DataFrame) -> None:
    try:
        ws = seg.worksheet(HOJA_AUDITORIA)
        reintentos(lambda: ws.clear())
    except gspread.WorksheetNotFound:
        ws = reintentos(lambda: seg.add_worksheet(HOJA_AUDITORIA, rows=max(len(aud) + 10, 50), cols=len(aud.columns)))
    if ws.row_count < len(aud) + 5:
        reintentos(lambda: ws.resize(rows=len(aud) + 10))
    valores = [list(aud.columns)] + [[celda(v) for v in fila] for fila in aud.itertuples(index=False)]
    reintentos(lambda: ws.update(range_name="A1", values=valores, value_input_option="USER_ENTERED"))
    log(f"Auditoría JCO: {len(aud)} hallazgos en «{HOJA_AUDITORIA}» · {aud['Hallazgo'].value_counts().to_dict()}")


def auditoria_pagos(tabla: pd.DataFrame, aprob: dict, elim: dict) -> pd.DataFrame:
    """Casos para revisar del Hito: eliminados sin aprobación posterior y aprobados que no están en el seguimiento."""
    seg = tabla.assign(_k=tabla["F"].map(M.norm_doc)).drop_duplicates("_k").set_index("_k")
    filas = []
    for d, pagos in elim.items():
        s = seg.loc[d] if d in seg.index else None
        filas.append((d, "" if s is None else (s.get("Q", "") or s.get("AA", "")),
                      f"Eliminado en {pagos} y sin aprobación posterior", "" if s is None else s.get("BH", ""),
                      "" if s is None else s.get("BT", "")))
    for d, p in aprob.items():
        if d not in seg.index:
            filas.append((d, "", f"Aprobado en {p} pero no está en el seguimiento", "", ""))
    return pd.DataFrame(filas, columns=["Cédula", "Nombre", "Hallazgo", "Hito en el seguimiento",
                                        "Momento del proceso (Back UP)"])


def escribir_auditoria_pagos(seg: gspread.Spreadsheet, aud: pd.DataFrame) -> None:
    escribir_tabla(seg, "AUDITORÍA PAGOS", aud)
    log(f"Auditoría pagos: {len(aud)} casos · {aud['Hallazgo'].str.split(' en ').str[0].value_counts().to_dict()}")


def escribir_tabla(seg: gspread.Spreadsheet, nombre: str, df: pd.DataFrame) -> None:
    try:
        ws = seg.worksheet(nombre)
        reintentos(lambda: ws.clear())
    except gspread.WorksheetNotFound:
        ws = reintentos(lambda: seg.add_worksheet(nombre, rows=max(len(df) + 10, 50), cols=max(len(df.columns), 5)))
    if ws.row_count < len(df) + 5:
        reintentos(lambda: ws.resize(rows=len(df) + 10))
    valores = [list(df.columns)] + [[celda(v) for v in fila] for fila in df.itertuples(index=False)]
    reintentos(lambda: ws.update(range_name="A1", values=valores, value_input_option="USER_ENTERED"))


def escribir_reportes(seg: gspread.Spreadsheet, reportes: dict[str, list[list]]) -> None:
    """Reescribe las columnas de datos de Reporte CRM (A:L) y Reporte SIS (A:M) con lo traído de BigQuery y borra
    las filas sobrantes de esas mismas columnas. Las columnas de la derecha (fórmulas de control) no se tocan."""
    datos, limpiar = [], []
    for nombre, filas in reportes.items():
        ultima = M.get_column_letter(len(filas[0]))
        datos.append({"range": f"'{nombre}'!A1:{ultima}{len(filas)}",
                      "values": [[celda(v) for v in f] for f in filas]})
        limpiar.append(f"'{nombre}'!A{len(filas) + 1}:{ultima}")
    # gspread 6: los rangos van en el cuerpo ({"ranges": [...]}); pasados sueltos no borraban nada.
    reintentos(lambda: seg.values_batch_clear(body={"ranges": limpiar}))
    reintentos(lambda: seg.values_batch_update({"valueInputOption": "USER_ENTERED", "data": datos}))
    log("Pestañas actualizadas desde BigQuery: " + ", ".join(f"{n} ({len(f) - 1} filas)" for n, f in reportes.items()))


def escribir_real(seg: gspread.Spreadsheet, tabla: pd.DataFrame, n_base: int) -> None:
    ws = seg.worksheet(HOJA)
    ultima_fila = FILA_DATOS + len(tabla) - 1
    if ws.row_count < ultima_fila:
        reintentos(lambda: ws.resize(rows=ultima_fila + 50))
    datos = []
    for ini, fin in bloques_calculados():
        cols = [M.get_column_letter(i) for i in range(M.letra(ini) + 1, M.letra(fin) + 2)]
        datos.append({"range": f"{HOJA}!{ini}{FILA_DATOS}:{fin}{ultima_fila}",
                      "values": [[celda(v) for v in fila] for fila in tabla[cols].itertuples(index=False)]})
    if len(tabla) > n_base:  # cédulas nuevas: también su columna F (manual) para que queden en el seguimiento
        datos.append({"range": f"{HOJA}!F{FILA_DATOS + n_base}:F{ultima_fila}",
                      "values": [[v] for v in tabla["F"].iloc[n_base:]]})
    # gspread 6: values_batch_update(body) con el cuerpo completo de la API (data + valueInputOption).
    reintentos(lambda: seg.values_batch_update({"valueInputOption": "USER_ENTERED", "data": datos}))
    log(f"Actualizado «{HOJA}»: {len(tabla)} filas · {len(bloques_calculados())} bloques de columnas")


def main(destino: str | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--destino", choices=["prueba", "real"], default=destino or "prueba")
    ap.add_argument("--sin-nuevas", action="store_true", help="no agregar cédulas que faltan en el seguimiento")
    args = ap.parse_args([] if destino else None)

    sid = os.getenv("SHEET_ID_GENERAL", "").strip()
    if not sid:
        sys.exit("Falta SHEET_ID_GENERAL en STC/.env.")
    t0 = time.time()
    gc = cliente()
    seg = reintentos(lambda: gc.open_by_key(sid))
    log(f"Seguimiento: {seg.title} · destino: {args.destino}")
    if args.destino == "real":
        validar_encabezados(seg)
    base = leer_base(seg)
    log(f"Filas actuales del seguimiento: {len(base)}")
    fuentes, remisiones, avisos, reportes = leer_fuentes(gc, seg)

    n_base = len(base)
    nuevas = [] if args.sin_nuevas else M.faltantes(base, fuentes)
    if nuevas:
        extra = pd.DataFrame({c: [""] * len(nuevas) for c in base.columns})
        extra["F"] = nuevas
        base = pd.concat([base, extra], ignore_index=True)
        log(f"Cédulas nuevas agregadas al final: {len(nuevas)}")

    aprob, elim, _ = hitos_de_pago(gc, avisos)
    tabla = M.calcular(base, fuentes, remisiones, aprob)
    tabla = tabla[[M.get_column_letter(i + 1) for i in range(len(M.ENCABEZADOS))]]
    repetidas = int((tabla["B"].map(lambda v: isinstance(v, int) and v > 1)).sum())
    resumen = tabla["BT"].value_counts().to_dict()
    log(f"Momento del proceso (Back UP): {resumen}")
    if repetidas:
        log(f"OJO: {repetidas} cédulas repetidas en la columna F")

    log(f"Evento/Base (col. E): {tabla['E'].replace('', '(vacío)').value_counts().to_dict()}")
    log(f"Hito (col. BH): {tabla['BH'].replace('', '(vacío)').value_counts().to_dict()}")
    # Reporte CRM y Reporte SIS son copia directa de BigQuery: se actualizan en ambos modos (también en prueba).
    if reportes:
        escribir_reportes(seg, reportes)
    if args.destino == "real":
        escribir_real(seg, tabla, n_base)
    else:
        escribir_prueba(seg, tabla)
    escribir_auditoria(seg, M.auditoria_jco(tabla, fuentes))
    if aprob is not None:
        escribir_auditoria_pagos(seg, auditoria_pagos(tabla, aprob, elim))
    for a in avisos:
        log(f"AVISO: {a}")
    log(f"Listo en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
