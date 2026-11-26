"""
Actualiza «Seguimiento Formación STC 3.0» (SHEET_ID_FORMACION) desde BigQuery, sin n8n y sin fórmulas.

Reemplaza el flujo de n8n «LOGSSTC3.0-FORMACIÓN». En cada ejecución:
  1. Consulta BigQuery (proyecto del SIS/CRM): LOGS, ASISTENCIAS, LOG_ACCESS, USER_STATISTICS, NOTAS PUBLICADAS,
     SESIONES (las mismas consultas del flujo, en sql/*.sql) + Reporte CRM y Reporte SIS (las del Seguimiento General).
  2. El SEGUIMIENTO GENERAL es la ÚNICA fuente de quién va en formación (y de nombre, curso, fecha de orientación y
     mes de entrega; ya trae lo del Consolidado FCS). Se agregan al final de CONSOLIDADO sus especializados vigentes
     que falten —paquete ESPECIALIZADO, orientación FINALIZADO / FINALIZADO PENDIENTE X REMISIÓN, sin baja (Back UP ≠
     6.Baja) y cédula bien escrita—. En la ejecución normal NUNCA se borran ni se mueven filas.
     Limpieza única (--limpiar): retira a quien no cumple y lo guarda completo en «Retirados de CONSOLIDADO» (si
     saldría más del 30 %, se detiene sin escribir).
  3. Calcula todas las columnas de CONSOLIDADO con motor_formacion.py (mismas reglas de las fórmulas) y las escribe
     como VALORES. No toca las columnas del equipo (S, T, AI, AK, AL, AM, BC, BD, BG, BI); en la limpieza, viajan
     con su cédula.
  4. Reescribe las pestañas fuente con lo traído de BigQuery (para consulta y para los procesos que las leen:
     recordatorios de SESIONES, CLASES…). Por defecto UNA vez al día (primera ejecución del día), porque son ~1,3
     millones de celdas; el CONSOLIDADO sí se calcula con datos frescos en cada ejecución.
     SESIONES: se reescribe A:I; la columna K «ENVIADO» se conserva por CLASS_SESSION_ID y J1 (HABILITADO) queda
     como fórmula.
  5. Deja un resumen en la pestaña «Control script» (cédulas nuevas, cédulas que ya no son especializado vigente…).

Uso:
    python actualizar_formacion.py                    # real
    python actualizar_formacion.py --prueba           # escribe «CONSOLIDADO (script)», «SIS sin seguimiento» y
                                                      # «Control script»; no toca CONSOLIDADO ni las pestañas fuente
    python actualizar_formacion.py --limpiar --prueba # cómo quedaría la limpieza única (no toca CONSOLIDADO)
    python actualizar_formacion.py --limpiar          # LIMPIEZA ÚNICA: retira a quien no es especializado vigente
                                                      # (nunca a FINALIZADO / CERTIFICADO: quedan con observación en BJ)
    python actualizar_formacion.py --pestanas si      # fuerza reescribir las pestañas fuente (auto | si | no)
    python actualizar_formacion.py --sin-nuevas       # no agrega cédulas del Seguimiento General
Encadenado: Seguimiento_general/reconstruir_seguimiento_real.py lo corre al terminar cada reconstrucción.

Configuración (STC/.env): SHEET_ID_FORMACION, SHEET_ID_GENERAL,
SHEET_ID_TIPO_DOCUMENTO (opcional; por defecto el archivo 1DG2xGi… que usaba la fórmula de la col. F),
FORMACION_PESTANAS (auto | si | no). Credenciales: credenciales.json (Sheets, EDITOR del archivo de formación) y la
llave de BigQuery que usa reportes_bigquery.py.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(RAIZ / "Seguimiento_general"))
import motor_formacion as F  # noqa: E402
import reconstruir_seguimiento as R  # noqa: E402  (carga el .env, cliente de Sheets, reintentos)
import reportes_bigquery as RB  # noqa: E402
from motor_seguimiento import get_column_letter, tabla  # noqa: E402

HOJA = "CONSOLIDADO"
HOJA_PRUEBA = "CONSOLIDADO (script)"
HOJA_CONTROL = "Control script"
HOJA_SIS_SIN = "SIS sin seguimiento"
HOJA_RETIRADOS = "Retirados de CONSOLIDADO"
HOJA_RETIRADOS_PRUEBA = "Retirados (prueba)"
MAX_RETIRO = 0.30  # si saldría más del 30 % de CONSOLIDADO, se detiene (seguramente falló la lectura del SG)
# Fechas como número de serie: una cédula escrita en una celda con formato de fecha llega como número (38075) y no
# como «29/03/2004» (que es como se escribía en la prueba).
LEER_SERIAL = {"valueRenderOption": "UNFORMATTED_VALUE", "dateTimeRenderOption": "SERIAL_NUMBER"}
TIPO_DOC_DEFECTO = "1DG2xGi7xZmijrkwOEHfA2e_uguA5MU-fJ6Zx6wEAP9k"
SQL = {  # pestaña → archivo de consulta (las mismas del flujo de n8n)
    "LOGS": "logs.sql", "ASISTENCIAS": "asistencias.sql", "LOG_ACCESS": "log_access.sql",
    "USER_STATISTICS": "user_statistics.sql", "NOTAS PUBLICADAS": "notas.sql", "SESIONES": "sesiones.sql",
}
# Pestañas del mismo archivo que diligencia el equipo (se leen por letra, como las fórmulas)
MANUALES = {
    "CERTIFICADOS": "CERTIFICADOS!A1:U", "Descargables": "Descargables!A1:E",
    "Respuestas de formulario 1": "'Respuestas de formulario 1'!A1:C", "Hoja 31": "'Hoja 31'!A1:I",
    "Matriz Documental": "'Matriz Documental'!A1:AX",
    "Respuestas Encuestas de Cierre": "'Respuestas Encuestas de Cierre'!A1:J",
}
FORMULA_HABILITADO = ('=MAP(F1:F,LAMBDA(X,IFERROR(IF(X="",,IF(TODAY()=INT(SUBSTITUTE(X,"\'","")),'
                      '"HABILITADO","BLOQUEADO")),"HABILITADO")))')
FILAS_LOTE = 5000


def log(msg: str) -> None:
    print(f"[formacion] {msg}", flush=True)


def hoy_bogota() -> pd.Timestamp:
    return pd.Timestamp.now(tz=F.ZONA).tz_localize(None).normalize()


# ------------------------------------------------------------------ BigQuery
def _celda_bq(v):
    """Valor de BigQuery → celda con el mismo formato que dejaba n8n (fechas ISO en hora de Colombia)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        t = pd.Timestamp(v)
        t = t.tz_convert(F.ZONA) if t.tzinfo is not None else t
        s = t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}"
        return s + (t.strftime("%z")[:3] + ":" + t.strftime("%z")[3:] if t.tzinfo is not None else "")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (int, float, str)):
        return v
    return str(v)


def consultar_bigquery() -> dict[str, list[list]]:
    """{pestaña: [encabezados, fila, …]} para las 6 consultas del flujo + Reporte CRM/SIS."""
    from google.cloud import bigquery
    from google.oauth2.service_account import Credentials
    llave = RB.buscar_llave(RAIZ)
    if llave is None:
        raise FileNotFoundError(f"no encontré la llave de BigQuery. {RB.diagnostico(RAIZ)}")
    cred = Credentials.from_service_account_file(str(llave), scopes=["https://www.googleapis.com/auth/bigquery"])
    bq = bigquery.Client(credentials=cred, project=os.getenv("BQ_PROJECT", "").strip() or cred.project_id)
    log(f"BigQuery: {cred.service_account_email} · proyecto {bq.project}")
    consultas = {n: (AQUI / "sql" / a).read_text(encoding="utf-8") for n, a in SQL.items()}
    consultas["REPORTE CRM"] = RB.SQL_CRM
    consultas["REPORTE SIS"] = RB.SQL_SIS

    def una(nombre: str) -> list[list]:
        t0 = time.time()
        res = bq.query(consultas[nombre]).result()
        if nombre in ("REPORTE CRM", "REPORTE SIS"):
            orden = RB.COLUMNAS["Reporte CRM" if nombre == "REPORTE CRM" else "Reporte SIS"]
        else:
            orden = [c.name for c in res.schema]
        filas = [[_celda_bq(f.get(c)) for c in orden] for f in res]
        log(f"  {nombre}: {len(filas)} filas ({time.time() - t0:.0f} s)")
        return [orden] + filas

    with ThreadPoolExecutor(max_workers=4) as ex:
        futuros = {n: ex.submit(una, n) for n in consultas}
        return {n: fu.result() for n, fu in futuros.items()}


def por_nombre(filas: list[list]) -> pd.DataFrame:
    return pd.DataFrame(filas[1:], columns=filas[0]) if filas else pd.DataFrame()


# ------------------------------------------------------------------ lecturas de Sheets
def leer(libro, rangos: list[str], serial: bool = False) -> list[list[list]]:
    if not serial:
        return R.leer_rangos(libro, rangos)
    r = R.reintentos(lambda: libro.values_batch_get(rangos, params=LEER_SERIAL))
    return [v.get("values", []) for v in r.get("valueRanges", [])]


def leer_externo(gc, var: str, defecto: str, rango: str, avisos: list[str], nombre: str, encabezado: int = 0):
    sid = os.getenv(var, "").strip() or defecto
    if not sid:
        avisos.append(f"{nombre}: falta {var} en el .env")
        return None
    try:
        filas = leer(R.reintentos(lambda: gc.open_by_key(sid)), [rango])[0]
        log(f"{nombre}: {max(len(filas) - 1 - encabezado, 0)} filas")
        return tabla(filas, encabezado)
    except Exception as e:  # noqa: BLE001 -- sin acceso: se sigue con lo demás y se avisa
        avisos.append(f"{nombre}: sin acceso ({type(e).__name__}: {str(e)[:120]}). Comparte el archivo con la "
                      "cuenta de servicio de credenciales.json")
        return None


def especializados(gc, avisos: list[str]):
    """(cédulas vigentes, {cédula: situación en el SG}, tabla del SG). (None, {}, None) si no se pudo leer."""
    sid = os.getenv("SHEET_ID_GENERAL", "").strip()
    if not sid:
        avisos.append("Falta SHEET_ID_GENERAL: no se agregaron cédulas nuevas")
        return None, {}, None
    filas = leer(R.reintentos(lambda: gc.open_by_key(sid)), [f"{R.HOJA}!A{R.FILA_DATOS}:BT"], serial=True)[0]
    sg = tabla([[]] + filas)
    cedulas = F.especializados_sg(sg)
    log(f"Seguimiento General: {len(cedulas)} especializados vigentes (orientación finalizada, sin baja)")
    return cedulas, F.situacion_sg(sg), sg


# ------------------------------------------------------------------ escritura
def celda(v):
    """RAW: números como número, booleanos como booleano, fechas como texto dd/mm/aaaa (igual que las fórmulas)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() and abs(v) < 1e15 else float(v)
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    return str(v)


def bloques(columnas: list[str]) -> list[tuple[str, str]]:
    salida, actual = [], []
    for c in F.COLUMNAS:
        if c in columnas:
            actual.append(c)
        elif actual:
            salida.append((actual[0], actual[-1]))
            actual = []
    if actual:
        salida.append((actual[0], actual[-1]))
    return salida


def asegurar_filas(ws, filas: int, columnas: int | None = None) -> None:
    if ws.row_count < filas or (columnas and ws.col_count < columnas):
        R.reintentos(lambda: ws.resize(rows=max(ws.row_count, filas + 100),
                                       cols=max(ws.col_count, columnas or 0)))


def validar_encabezados(fila1: list) -> None:
    actual = list(fila1) + [""] * (len(F.ENCABEZADOS) - len(fila1))
    if F.plano(actual[-1]) == "":  # columna BJ nueva (observación): se crea el encabezado al escribir
        actual[-1] = F.ENCABEZADOS[-1]
    distintos = [f"{c}: hoja «{a}» ≠ esperado «{e}»" for c, a, e in zip(F.COLUMNAS, actual, F.ENCABEZADOS)
                 if F.plano(a) != F.plano(e)]
    if distintos:
        sys.exit("Los encabezados de CONSOLIDADO (fila 1) no coinciden con las columnas que escribe el script; no se "
                 "escribió nada.\n  " + "\n  ".join(distintos[:15]))


def escribir_consolidado(libro, out: pd.DataFrame, filas_antes: int) -> None:
    """Reescribe CONSOLIDADO completo (A:BI, desde la fila 2) porque al retirar personas las filas se corren; las
    columnas del equipo viajan con su cédula. Las filas que sobran al final se vacían (solo valores: el formato de
    la hoja no se toca)."""
    ws = libro.worksheet(HOJA)
    ultima = 1 + len(out)
    asegurar_filas(ws, ultima, len(F.COLUMNAS))
    fin = F.COLUMNAS[-1]
    datos = [{"range": f"{HOJA}!A2:{fin}{ultima}",
              "values": [[celda(v) for v in fila] for fila in out[F.COLUMNAS].itertuples(index=False)]},
             {"range": f"{HOJA}!{fin}1", "values": [[F.ENCABEZADOS[-1]]]}]
    R.reintentos(lambda: libro.values_batch_update({"valueInputOption": "RAW", "data": datos}))
    if filas_antes > len(out):
        R.reintentos(lambda: libro.values_batch_clear(body={"ranges": [f"{HOJA}!A{ultima + 1}:{fin}{filas_antes + 1}"]}))
    log(f"CONSOLIDADO: {len(out)} filas escritas" + (f", {filas_antes - len(out)} filas vaciadas al final"
                                                    if filas_antes > len(out) else ""))


def _a1(rango: dict) -> str:
    """GridRange de la API → «B2:F», «A:A» o «toda la pestaña»."""
    if set(rango) <= {"sheetId"}:
        return "toda la pestaña"
    c1, c2 = rango.get("startColumnIndex"), rango.get("endColumnIndex")
    f1, f2 = rango.get("startRowIndex"), rango.get("endRowIndex")
    ini = (get_column_letter(c1 + 1) if c1 is not None else "A") + (str(f1 + 1) if f1 is not None else "")
    fin = (get_column_letter(c2) if c2 is not None else "") + (str(f2) if f2 is not None else "")
    return f"{ini}:{fin}" if fin else ini


def protecciones_bloqueantes(libro, pestanas: set[str]) -> list[str]:
    """Rangos protegidos (no solo de advertencia) que la cuenta de servicio NO puede editar en las pestañas que el
    script va a escribir. Se revisa ANTES de escribir para no dejar la hoja a medias."""
    meta = R.reintentos(lambda: libro.fetch_sheet_metadata(
        {"fields": "sheets(properties(title,sheetId),protectedRanges(range,description,warningOnly,"
                   "requestingUserCanEdit))"}))
    hallazgos = []
    for hoja in meta.get("sheets", []):
        titulo = hoja["properties"]["title"]
        if titulo not in pestanas:
            continue
        for pr in hoja.get("protectedRanges", []):
            if pr.get("warningOnly") or pr.get("requestingUserCanEdit"):
                continue
            desc = f" («{pr['description']}»)" if pr.get("description") else ""
            hallazgos.append(f"{titulo} · {_a1(pr.get('range', {}))}{desc}")
    return hallazgos


def escribir_calculadas(libro, out: pd.DataFrame, n_base: int) -> None:
    """Ejecución normal: las filas no se mueven. Solo se escriben las columnas calculadas y, al final, la columna G
    de las cédulas nuevas; las columnas del equipo no se tocan."""
    ws = libro.worksheet(HOJA)
    ultima = 1 + len(out)
    asegurar_filas(ws, ultima, len(F.COLUMNAS))
    datos = []
    for ini, fin in bloques(F.CALCULADAS):
        cols = F.COLUMNAS[F.COLUMNAS.index(ini): F.COLUMNAS.index(fin) + 1]
        datos.append({"range": f"{HOJA}!{ini}2:{fin}{ultima}",
                      "values": [[celda(v) for v in fila] for fila in out[cols].itertuples(index=False)]})
    if len(out) > n_base:
        datos.append({"range": f"{HOJA}!G{n_base + 2}:G{ultima}",
                      "values": [[celda(v)] for v in out["G"].iloc[n_base:]]})
    datos.append({"range": f"{HOJA}!{F.COLUMNAS[-1]}1", "values": [[F.ENCABEZADOS[-1]]]})
    R.reintentos(lambda: libro.values_batch_update({"valueInputOption": "RAW", "data": datos}))
    log(f"CONSOLIDADO: {len(out)} filas actualizadas ({len(out) - n_base} nuevas al final)")


def guardar_retirados(libro, salen: pd.DataFrame, motivos: list[str], prueba: bool) -> None:
    """Las filas que salen de CONSOLIDADO se guardan completas (con lo que diligenció el equipo) en una pestaña
    aparte; en real se ACUMULAN (fecha + motivo), en prueba se reemplaza la pestaña de prueba."""
    import gspread
    nombre = HOJA_RETIRADOS_PRUEBA if prueba else HOJA_RETIRADOS
    encabezado = ["Retirado el", "Motivo"] + [e or c for c, e in zip(F.COLUMNAS, F.ENCABEZADOS)]
    marca = pd.Timestamp.now(tz=F.ZONA).strftime("%Y-%m-%d %H:%M")
    filas = [[marca, m] + [celda(v) for v in f] for m, f in zip(motivos, salen[F.COLUMNAS].itertuples(index=False))]
    try:
        ws = libro.worksheet(nombre)
        if prueba:
            R.reintentos(lambda: ws.clear())
            previas = 0
        else:
            previas = len(leer(libro, [f"'{nombre}'!A1:A"])[0])
    except gspread.WorksheetNotFound:
        ws = R.reintentos(lambda: libro.add_worksheet(nombre, rows=max(100, len(filas) + 10), cols=len(encabezado)))
        previas = 0
    if previas == 0:
        filas = [encabezado] + filas
    if not filas:
        return
    asegurar_filas(ws, previas + len(filas) + 2, len(encabezado))
    R.reintentos(lambda: ws.update(range_name=f"A{previas + 1}", values=filas, value_input_option="RAW"))
    log(f"«{nombre}»: {len(salen)} filas guardadas")


def escribir_prueba(libro, out: pd.DataFrame) -> None:
    import gspread
    try:
        ws = libro.worksheet(HOJA_PRUEBA)
        R.reintentos(lambda: ws.clear())
    except gspread.WorksheetNotFound:
        ws = R.reintentos(lambda: libro.add_worksheet(HOJA_PRUEBA, rows=len(out) + 10, cols=len(F.COLUMNAS)))
    asegurar_filas(ws, len(out) + 2, len(F.COLUMNAS))
    valores = [F.ENCABEZADOS] + [[celda(v) for v in fila] for fila in out.itertuples(index=False)]
    R.reintentos(lambda: ws.update(range_name="A1", values=valores, value_input_option="RAW"))
    log(f"Prueba: tabla completa en «{HOJA_PRUEBA}» ({len(out)} filas). CONSOLIDADO no se tocó.")


def reescribir_pestana(libro, nombre: str, filas: list[list], ultima_col: str | None = None,
                       empezar: str = "A") -> None:
    """Escribe filas (con encabezado) desde A1 en lotes y borra lo que sobre de esas mismas columnas."""
    ws = libro.worksheet(nombre)
    ancho = len(filas[0])
    fin = ultima_col or get_column_letter(F.letra(empezar) + ancho)
    asegurar_filas(ws, len(filas) + 1, F.letra(fin) + 1)
    for i in range(0, len(filas), FILAS_LOTE):
        lote = filas[i:i + FILAS_LOTE]
        rango = f"'{nombre}'!{empezar}{i + 1}:{fin}{i + len(lote)}"
        R.reintentos(lambda: libro.values_batch_update(
            {"valueInputOption": "RAW", "data": [{"range": rango, "values": [[celda(v) for v in f] for f in lote]}]}))
    if ws.row_count > len(filas):
        R.reintentos(lambda: libro.values_batch_clear(
            body={"ranges": [f"'{nombre}'!{empezar}{len(filas) + 1}:{fin}"]}))


def escribir_pestanas(libro, bq: dict[str, list[list]], enviado: dict) -> None:
    t0 = time.time()
    for nombre in ("LOGS", "ASISTENCIAS", "LOG_ACCESS", "USER_STATISTICS", "NOTAS PUBLICADAS"):
        reescribir_pestana(libro, nombre, bq[nombre])
        log(f"  {nombre}: {len(bq[nombre]) - 1} filas")
    # SESIONES: A:I de BigQuery, J1 = fórmula HABILITADO (rango abierto), K = ENVIADO conservado por sesión
    ses = bq["SESIONES"]
    reescribir_pestana(libro, "SESIONES", ses, "I")
    i_id = ses[0].index("CLASS_SESSION_ID")
    k = [["ENVIADO"]] + [[enviado.get(str(f[i_id]), "")] for f in ses[1:]]
    reescribir_pestana(libro, "SESIONES", k, "K", empezar="K")
    R.reintentos(lambda: libro.values_batch_update(
        {"valueInputOption": "USER_ENTERED", "data": [{"range": "SESIONES!J1", "values": [[FORMULA_HABILITADO]]}]}))
    log(f"  SESIONES: {len(ses) - 1} filas (ENVIADO conservado en {sum(1 for v in enviado.values() if v)} sesiones)")
    # REPORTE CRM (A:K + Baja en N) y REPORTE SIS (A:M), informativas
    crm = bq["REPORTE CRM"]
    reescribir_pestana(libro, "REPORTE CRM", [f[:11] for f in crm], "K")
    reescribir_pestana(libro, "REPORTE CRM", [[f[11]] for f in crm], "N", empezar="N")
    reescribir_pestana(libro, "REPORTE SIS", bq["REPORTE SIS"], "M")
    log(f"Pestañas fuente reescritas en {time.time() - t0:.0f} s")


def escribir_tabla(libro, nombre: str, df: pd.DataFrame, titulo: str) -> None:
    import gspread
    try:
        ws = libro.worksheet(nombre)
        R.reintentos(lambda: ws.clear())
    except gspread.WorksheetNotFound:
        ws = R.reintentos(lambda: libro.add_worksheet(nombre, rows=max(100, len(df) + 10), cols=len(df.columns)))
    asegurar_filas(ws, len(df) + 3, len(df.columns))
    valores = [[titulo] + [""] * (len(df.columns) - 1), list(df.columns)] + \
        [[celda(v) for v in f] for f in df.itertuples(index=False)]
    R.reintentos(lambda: ws.update(range_name="A1", values=valores, value_input_option="RAW"))


def leer_control(libro) -> str:
    try:
        v = leer(libro, [f"'{HOJA_CONTROL}'!B1"])[0]
        return str(v[0][0]) if v and v[0] else ""
    except Exception:  # noqa: BLE001 -- la pestaña aún no existe
        return ""


def escribir_control(libro, marca_pestanas: str, resumen: list[list], casos: list[list]) -> None:
    import gspread
    try:
        ws = libro.worksheet(HOJA_CONTROL)
        R.reintentos(lambda: ws.clear())
    except gspread.WorksheetNotFound:
        ws = R.reintentos(lambda: libro.add_worksheet(HOJA_CONTROL, rows=max(200, len(casos) + 20), cols=4))
    asegurar_filas(ws, len(resumen) + len(casos) + 5)
    filas = [["Pestañas fuente (BigQuery) actualizadas", marca_pestanas, "", ""]] + resumen + [["", "", "", ""],
             ["Cédula", "Situación",
              "Estado de la formación", ""]] + casos
    filas = [list(f) + [""] * (4 - len(f)) for f in filas]
    R.reintentos(lambda: ws.update(range_name="A1", values=[[celda(v) for v in f] for f in filas],
                                   value_input_option="RAW"))


# ------------------------------------------------------------------ principal
def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prueba", action="store_true", help="escribe en «CONSOLIDADO (script)» y no toca nada más")
    ap.add_argument("--pestanas", choices=["auto", "si", "no"],
                    default=os.getenv("FORMACION_PESTANAS", "auto").strip().lower() or "auto")
    ap.add_argument("--sin-nuevas", action="store_true")
    ap.add_argument("--limpiar", action="store_true",
                    help="LIMPIEZA ÚNICA: retira de CONSOLIDADO a quien no es especializado vigente en el SG")
    ap.add_argument("--forzar-retiro", action="store_true",
                    help=f"retirar aunque salga más del {MAX_RETIRO:.0%} de CONSOLIDADO")
    args = ap.parse_args(argv)

    t0 = time.time()
    sid = os.getenv("SHEET_ID_FORMACION", "").strip()
    if not sid:
        sys.exit("Falta SHEET_ID_FORMACION en STC/.env.")
    hoy = hoy_bogota()
    avisos: list[str] = []
    gc = R.cliente()
    libro = R.reintentos(lambda: gc.open_by_key(sid))
    log(f"Archivo: {libro.title} · {'PRUEBA' if args.prueba else 'real'} · hoy {hoy:%d/%m/%Y}")

    # 1. BigQuery (en paralelo con las lecturas de Sheets)
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut_bq = ex.submit(consultar_bigquery)
        rangos = [f"{HOJA}!A1:{F.COLUMNAS[-1]}", "SESIONES!A1:K"] + list(MANUALES.values())
        lecturas = leer(libro, rangos[:1], serial=True) + leer(libro, rangos[1:])
        tipo_doc = leer_externo(gc, "SHEET_ID_TIPO_DOCUMENTO", TIPO_DOC_DEFECTO, "CONSOLIDADO!A1:L", avisos,
                                "Tipo de documento (1DG2xGi…)")
        cedulas, situacion, sg = especializados(gc, avisos)
        bq = fut_bq.result()

    consolidado, sesiones_hoja = lecturas[0], lecturas[1]
    if not consolidado:
        sys.exit("CONSOLIDADO está vacío: no se escribió nada.")
    validar_encabezados(consolidado[0])
    if sg is None or cedulas is None:
        sys.exit("No se pudo leer el SEGUIMIENTO GENERAL (única fuente de quiénes van en formación); no se escribió "
                 "nada.")

    # ENVIADO de SESIONES por CLASS_SESSION_ID (lo escribe el proceso de recordatorios)
    enviado = {}
    if sesiones_hoja:
        enc = sesiones_hoja[0]
        i_id = enc.index("CLASS_SESSION_ID") if "CLASS_SESSION_ID" in enc else 1
        for f in sesiones_hoja[1:]:
            if len(f) > 10 and f[i_id]:
                enviado[str(f[i_id])] = f[10]
    fuentes = {n: por_nombre(filas) for n, filas in bq.items()}
    fuentes["SESIONES"] = fuentes["SESIONES"].assign(
        ENVIADO=[enviado.get(str(v), "") for v in fuentes["SESIONES"].get("CLASS_SESSION_ID", [])])
    for nombre, filas in zip(MANUALES, lecturas[2:]):
        fuentes[nombre] = tabla(filas)
    fuentes["SG"] = sg

    # 2. Cédulas nuevas y 3. cálculo
    base = tabla(consolidado)
    for c in F.COLUMNAS:
        if c not in base:
            base[c] = ""
    base = base[F.COLUMNAS]
    con_doc = base.index[base["G"].map(F.norm_doc) != ""]
    base = base.loc[: con_doc.max()] if len(con_doc) else base.iloc[0:0]
    filas_antes = len(base)
    vigentes = {c for c in cedulas if not F.cedula_rara(c)}

    def motivo(k: str) -> str:
        if k in vigentes:
            return ""
        if F.cedula_rara(k):
            return "Cédula para revisar: " + F.cedula_rara(k)
        return situacion.get(k) or "No está en el Seguimiento General"

    # Estado de formación con los datos de hoy (para no retirar nunca a quien terminó)
    previo = F.calcular(base, fuentes, hoy, tipo_doc)
    _, no_vigentes = F.depurar(base, vigentes)
    salen = base.iloc[0:0]
    if args.limpiar:
        # Limpieza única: quedan los especializados vigentes del SG y TODOS los FINALIZADO / CERTIFICADO
        base, salen = F.depurar(base, vigentes, previo["O"])
    if len(salen) > MAX_RETIRO * max(filas_antes, 1) and not args.forzar_retiro:
        sys.exit(f"Saldrían {len(salen)} de {filas_antes} filas de CONSOLIDADO (más del {MAX_RETIRO:.0%}); parece un "
                 "error de lectura del Seguimiento General. No se escribió nada. Si es correcto: --forzar-retiro")
    estado_previo = dict(zip(previo["G"].map(F.norm_doc), previo["O"]))
    motivos = [motivo(F.norm_doc(d)) for d in salen["G"]]
    terminados = sum(1 for d in no_vigentes["G"] if estado_previo.get(F.norm_doc(d)) in F.TERMINADOS)
    log(f"No vigentes en CONSOLIDADO: {len(no_vigentes)} ({terminados} terminaron formación: se quedan con "
        f"observación) · {'retiradas' if args.limpiar else 'se dejan'}: {len(salen)}"
        + (f" · {pd.Series(motivos).str.split(':').str[0].value_counts().to_dict()}" if motivos else ""))
    nuevas = []
    if not args.sin_nuevas:
        base, nuevas = F.con_nuevas(base, cedulas)
        log(f"Cédulas nuevas desde el Seguimiento General: {len(nuevas)}")
    observaciones = {F.norm_doc(d): motivo(F.norm_doc(d)) for d in base["G"] if F.norm_doc(d)}
    out = F.calcular(base, fuentes, hoy, tipo_doc, observaciones)
    estados = out.loc[out["G"].map(F.norm_doc) != "", "O"].replace("", "(vacío)").value_counts().to_dict()
    log(f"Estado de la formación: {estados}")

    # Antes de escribir: ¿hay rangos protegidos que la cuenta de servicio no puede editar?
    a_escribir = {HOJA_CONTROL, HOJA_SIS_SIN} | ({HOJA_PRUEBA, HOJA_RETIRADOS_PRUEBA} if args.prueba else
                                                 {HOJA, HOJA_RETIRADOS, "SESIONES", "REPORTE CRM", "REPORTE SIS",
                                                  *(n for n in SQL)})
    bloqueos = protecciones_bloqueantes(libro, a_escribir)
    if bloqueos:
        cuenta = getattr(R.CREDENCIALES, "service_account_email", "la cuenta de credenciales.json")
        sys.exit("No se escribió nada: hay rangos protegidos que la cuenta de servicio no puede editar:\n  "
                 + "\n  ".join(bloqueos)
                 + f"\nSolución: en Datos › Proteger hojas y rangos, abre cada protección y agrega como editor a "
                   f"{cuenta} (o cámbiala a «Mostrar una advertencia»). Luego vuelve a correr el script.")

    if args.prueba:
        escribir_prueba(libro, out)
    elif args.limpiar:
        escribir_consolidado(libro, out, filas_antes)
    else:
        escribir_calculadas(libro, out, filas_antes)
    if len(salen):
        guardar_retirados(libro, salen, motivos, args.prueba)

    # 4. Pestañas fuente
    marca = leer_control(libro)
    hoy_txt = hoy.strftime("%Y-%m-%d")
    toca = args.pestanas == "si" or (args.pestanas == "auto" and not marca.startswith(hoy_txt))
    if args.prueba:
        log("Prueba: las pestañas fuente no se reescriben")
    elif toca:
        escribir_pestanas(libro, bq, enviado)
        marca = pd.Timestamp.now(tz=F.ZONA).strftime("%Y-%m-%d %H:%M")
    else:
        log(f"Pestañas fuente: ya se actualizaron hoy ({marca}); se omiten (FORMACION_PESTANAS=si para forzar)")

    # 5. SIS especializados sin seguimiento (pestaña aparte, también en prueba: no toca nada existente)
    sin = F.sis_sin_seguimiento(fuentes.get("REPORTE SIS"), sg, base)
    escribir_tabla(libro, HOJA_SIS_SIN, sin, f"Usuarios del SIS con paquete Especializado que no están ni en el "
                   f"Seguimiento General ni en CONSOLIDADO (cruce por cédula, ID SIS e ID CRM) · "
                   f"{pd.Timestamp.now(tz=F.ZONA):%Y-%m-%d %H:%M} · {len(sin)} personas")
    log(f"{HOJA_SIS_SIN}: {len(sin)} usuarios especializados del SIS sin seguimiento")

    # 6. Control
    casos = [[F.norm_doc(d), ("Se retiraría" if args.prueba else "Retirada") + f" de CONSOLIDADO · {m}",
              estado_previo.get(F.norm_doc(d)) or "—"] for d, m in zip(salen["G"], motivos)]
    retiradas = {F.norm_doc(d) for d in salen["G"]}
    for d in no_vigentes["G"]:
        k = F.norm_doc(d)
        if k in retiradas:
            continue
        e = estado_previo.get(k) or "—"
        nota = "Terminó formación: se queda (ver columna BJ)" if e in F.TERMINADOS else (
            "Se queda (la ejecución normal no retira; usar --limpiar)")
        casos.append([k, f"{nota} · {motivo(k)}", e])
    casos += [[c, "Agregada en esta ejecución desde el Seguimiento General", ""] for c in nuevas]
    actuales = {F.norm_doc(d) for d in out["G"]}
    for k in (cedulas or []):
        if k not in actuales and F.cedula_rara(k):
            casos.append([k, "NO agregada: corregir la cédula en el Seguimiento General · " + F.cedula_rara(k), "—"])
    ahora = pd.Timestamp.now(tz=F.ZONA).strftime("%Y-%m-%d %H:%M")
    resumen = [["CONSOLIDADO actualizado" if not args.prueba else "Prueba generada", ahora],
               ["Personas en CONSOLIDADO", int((out["G"].map(F.norm_doc) != "").sum())],
               ["Cédulas nuevas en esta ejecución", len(nuevas)],
               (["Retiradas en esta limpieza", f"{len(salen)} (pestaña «{HOJA_RETIRADOS_PRUEBA if args.prueba else HOJA_RETIRADOS}»)"]
                if args.limpiar else ["No vigentes en CONSOLIDADO (no se retiran)", len(no_vigentes)]),
               ["No vigentes que terminaron formación (se quedan, observación en BJ)", terminados],
               ["Especializados del SIS sin seguimiento", f"{len(sin)} (pestaña «{HOJA_SIS_SIN}»)"],
               ["Estados", " · ".join(f"{k}: {v}" for k, v in estados.items())],
               ["Avisos", " | ".join(avisos) or "—"]]
    escribir_control(libro, marca, resumen, casos)  # en prueba también: la marca de las pestañas no cambia
    for a in avisos:
        log(f"AVISO: {a}")
    log(f"Listo en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
