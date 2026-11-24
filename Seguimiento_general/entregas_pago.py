"""Pago en el que la SDDE aprobó a cada persona (columna BH «Hito» del Seguimiento General).

Lee la carpeta de Drive «5.4 Entregas Mensuales» (o una copia local, para pruebas) y clasifica los archivos por
nombre:
  * carpeta «Pago N» (y sus subcarpetas) → pago N;
  * archivo con «Aprobados» → personas aprobadas por la SDDE en ese pago;
  * archivo con «Eliminados» → personas eliminadas en ese pago (solo para la auditoría);
  * archivo «Formato de Clasificación y Seguimiento» cuyo NOMBRE dice «Pago N.1» / «Pago. N.1» / «Entrega N.1» →
    personas reportadas en la sub-entrega N.1.
Las copias («(1)», «(2) (2)») se suman: una persona aprobada en cualquiera de los archivos del pago queda aprobada.

Regla de BH (nov-2026, definida por Christian):
  * Aprobada → «Pago N», o «Pago N.1» si fue reportada en la sub-entrega N.1. Si aparece aprobada en varios pagos,
    vale el último (quien fue eliminado y luego aprobado en otro pago queda con ese pago).
  * Sin aprobación (incluye eliminados que no se han vuelto a aprobar) → vacío; el motor luego pone «En ruta» si su
    «Momento del proceso (Back UP)» es mayor que 0 (y no es Baja).
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

CARPETA_ENTREGAS = "1mxh_zYG5FiWAfIpVMQedExvCqn2Y5FIx"  # «5.4 Entregas Mensuales» en Drive
MIME_CARPETA = "application/vnd.google-apps.folder"
MIME_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ENCABEZADOS_DOC = {"numero de documento", "cc", "no. documento", "numero documento", "documento", "cedula"}


def plano(t) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class Archivo:
    ruta: str          # «Pago 2/Aprobados SDDE/2.2. STC 3.0_Formato Atendidos Aprobados Pago 2 Kuepa.xlsx»
    pago: int | None
    tipo: str          # APROBADOS | ELIMINADOS | FCS | otro
    sub: str = ""      # «2.1» si el nombre es de una sub-entrega
    docs: set = field(default_factory=set)


def clasificar(ruta: str) -> Archivo:
    partes = [p.strip() for p in ruta.replace("\\", "/").split("/") if p.strip()]
    nombre = plano(partes[-1]) if partes else ""
    pago = None
    for p in partes[:-1]:
        m = re.match(r"^pago\s*(\d+)\b", plano(p))
        if m:
            pago = int(m.group(1))
            break
    sub = ""
    m = re.search(r"(?:pago|entrega)[\s.]*(\d+\.\d+)", nombre)
    if m:
        sub = m.group(1)
    if "eliminad" in nombre:
        tipo = "ELIMINADOS"
    elif "aprobad" in nombre:
        tipo = "APROBADOS"
    elif "clasificaci" in nombre and "seguimiento" in nombre:
        tipo = "FCS"
    else:
        tipo = "otro"
    return Archivo(ruta=ruta, pago=pago, tipo=tipo, sub=sub)


def documentos_xlsx(contenido: bytes, norm_doc) -> set[str]:
    """Cédulas de la primera hoja: busca en las primeras 15 filas el encabezado «NÚMERO DE DOCUMENTO» (o «CC»)."""
    import warnings

    import openpyxl
    warnings.filterwarnings("ignore", module="openpyxl")  # fechas fuera de rango y extensiones: no afectan cédulas
    wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    filas = ws.iter_rows(values_only=True)
    col = None
    docs = set()
    for i, fila in enumerate(filas):
        if col is None:
            if i > 15:
                break
            for j, c in enumerate(fila):
                if c is not None and plano(c) in ENCABEZADOS_DOC:
                    col = j
                    break
            continue
        if col < len(fila):
            k = norm_doc(fila[col])
            if k:
                docs.add(k)
    wb.close()
    return docs


# ------------------------------------------------------------------ lectura: Drive o carpeta local
def listar_drive(sesion, carpeta: str, ruta: str = "") -> list[dict]:
    """Recorre la carpeta (y subcarpetas) con la API de Drive v3."""
    salida, token = [], None
    while True:
        r = sesion.get("https://www.googleapis.com/drive/v3/files", params={
            "q": f"'{carpeta}' in parents and trashed = false", "pageSize": 1000, "pageToken": token,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime)",
            "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}, timeout=60)
        r.raise_for_status()
        datos = r.json()
        for f in datos.get("files", []):
            sub_ruta = f"{ruta}/{f['name']}" if ruta else f["name"]
            if f["mimeType"] == MIME_CARPETA:
                salida += listar_drive(sesion, f["id"], sub_ruta)
            else:
                salida.append({**f, "ruta": sub_ruta})
        token = datos.get("nextPageToken")
        if not token:
            return salida


def descargar_drive(sesion, f: dict) -> bytes:
    base = f"https://www.googleapis.com/drive/v3/files/{f['id']}"
    if f["mimeType"] == MIME_SHEET:
        r = sesion.get(base + "/export", params={"mimeType": MIME_XLSX}, timeout=180)
    else:
        r = sesion.get(base, params={"alt": "media", "supportsAllDrives": "true"}, timeout=180)
    r.raise_for_status()
    return r.content


def leer_archivos(norm_doc, sesion=None, carpeta: str = CARPETA_ENTREGAS, local: str | None = None,
                  log=print) -> list[Archivo]:
    """Clasifica y lee SOLO los archivos útiles (aprobados, eliminados y FCS de sub-entregas)."""
    if local:
        base = Path(local)
        entradas = [{"ruta": str(p.relative_to(base)).replace("\\", "/"), "local": p}
                    for p in base.rglob("*") if p.is_file() and p.suffix.lower() == ".xlsx"]
    else:
        entradas = [f for f in listar_drive(sesion, carpeta)
                    if f["mimeType"] in (MIME_SHEET, MIME_XLSX) or f["name"].lower().endswith(".xlsx")]
    archivos = []
    for e in sorted(entradas, key=lambda x: x["ruta"]):
        a = clasificar(e["ruta"])
        util = a.pago is not None and (a.tipo in ("APROBADOS", "ELIMINADOS") or (a.tipo == "FCS" and a.sub))
        if not util:
            continue
        contenido = e["local"].read_bytes() if local else descargar_drive(sesion, e)
        a.docs = documentos_xlsx(contenido, norm_doc)
        log(f"  Pago {a.pago}{' (' + a.sub + ')' if a.sub else ''} · {a.tipo:10} · {len(a.docs):5} cédulas · {a.ruta}")
        archivos.append(a)
    return archivos


# ------------------------------------------------------------------ regla
def _orden(etiqueta: str) -> tuple:
    n = re.findall(r"\d+", etiqueta)
    return tuple(int(x) for x in n) if n else (0,)


def hitos(archivos: list[Archivo]) -> tuple[dict[str, str], dict[str, str]]:
    """(cédula → «Pago N»/«Pago N.1» aprobado, cédula → pagos en que fue eliminada sin aprobación posterior)."""
    sub_de: dict[tuple[int, str], str] = {}
    for a in archivos:
        if a.tipo == "FCS" and a.sub:
            for d in a.docs:
                sub_de[(a.pago, d)] = a.sub
    aprob: dict[str, str] = {}
    for a in archivos:
        if a.tipo != "APROBADOS":
            continue
        for d in a.docs:
            etiqueta = f"Pago {sub_de.get((a.pago, d), a.pago)}"
            if d not in aprob or _orden(etiqueta) > _orden(aprob[d]):
                aprob[d] = etiqueta
    elim: dict[str, str] = {}
    for a in archivos:
        if a.tipo != "ELIMINADOS":
            continue
        for d in a.docs:
            if d in aprob and _orden(aprob[d]) >= (a.pago,):
                continue  # eliminado y luego aprobado (en ese mismo pago o en uno posterior)
            elim[d] = ", ".join(sorted({*elim.get(d, "").split(", "), f"Pago {a.pago}"} - {""}, key=_orden))
    return aprob, elim
