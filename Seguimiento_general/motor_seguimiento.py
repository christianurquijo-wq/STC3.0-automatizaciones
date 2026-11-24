"""Motor del SEGUIMIENTO GENERAL STC 3.0: reemplaza las fórmulas (ARRAYFORMULA + MAP/LAMBDA/XLOOKUP) de la hoja
por un cálculo en pandas. Recibe las pestañas fuente como listas de filas (tal como las devuelve gspread o
openpyxl) y devuelve la tabla final con las mismas columnas A:BT de la hoja.

Reglas (las mismas de las fórmulas de nov-2026, con las correcciones marcadas «CORRIGE»):
  * La llave es la cédula (col. F «CC Prospecto»), normalizada: sin espacios, saltos de línea, puntos ni «.0».
  * Si una cédula aparece varias veces en una fuente, se toma la primera fila (igual que XLOOKUP).
"""
from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

def get_column_letter(n: int) -> str:
    """1 → A, 27 → AA (sin depender de openpyxl)."""
    letras = ""
    while n:
        n, r = divmod(n - 1, 26)
        letras = chr(65 + r) + letras
    return letras


def column_index_from_string(c: str) -> int:
    """A → 1, AA → 27."""
    n = 0
    for ch in c.upper():
        n = n * 26 + ord(ch) - 64
    return n


# ------------------------------------------------------------------ encabezados de la hoja (fila 4, A:BT)
ENCABEZADOS = [
    ".", "#", "Fecha", "Pre verificador", "Evento/Base", "CC Prospecto", "Documento de Identidad",
    "Pantallazo Preelegido", "Hoja de Vida", "RNEC", "Declaración Juramentada", "ADRES o Certificado de residencia",
    "ACJ", "Verificador", "ID CRM", "Fecha de alta", "Nombre completo", "Correo", "Teléfono", "Ad Network",
    "Estado CRM", "Cumple Requisitos", "Validación Documentos", "Verificación Calidad", "Orientador", "ID SIS",
    "Nombre", "Correo Electrónico", "Teléfono1", "JCO", "Reporte", "Fecha Calidad Orientación", "Fecha Orientación",
    "Paquete", "FCS", "Remitido", "CANTIDAD DE LOGS", "TIEMPO DE LOGUEO", "TIEMPO SINCRÓNICO", "TOTAL TIEMPO CURSO",
    "Análisis de deserción Esp", "Fecha calidad", "Fecha de inicio", "Fecha de terminación", "Número de horas",
    "Curso según FCS", "Curso certificado", "Revisión Formación", "¿Es JCO?", "Estado de la formación",
    "Fecha clases", "Fecha finalización", "Progreso", "Certificado", "Paquete de pantallazos", "Bono enviado",
    "Momento del proceso", "Plataforma STC", "Resultado del VRD", "Hito", "Mes de entrega", "Encuesta",
    "Tipo de paquete reportado", "Sexo Asignado al nacer", "Edad", "Sin gestión", "En verificación", "Verificado",
    "Orientado", "Formado", "Certificado (1)", "Momento del proceso (Back UP)",
]
# Columnas que diligencia el equipo a mano: el script nunca las sobrescribe.
MANUALES = ["A", "D", "F", "AI", "AP", "AQ", "AR", "AV", "BD", "BG", "BL", "BM"]

DOCS_BASICOS = ["G", "H", "I", "J", "K", "L", "M"]  # evidencias de verificación (J:P de Verificación IMPORT)


# ------------------------------------------------------------------ utilidades
def letra(c: str) -> int:
    return column_index_from_string(c) - 1


def norm_doc(v) -> str:
    """Cédula comparable: «1.023.034.451», «1023034451.0», « 1023034451\\n» → «1023034451». Pasaportes/PPT en
    mayúsculas sin espacios. Una cédula corta con formato de fecha en la hoja (38075 → 29/03/2004) vuelve a número."""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return str((pd.Timestamp(v) - pd.Timestamp("1899-12-30")).days)
    if isinstance(v, float):
        if pd.isna(v):
            return ""
        if v.is_integer():
            return str(int(v))
    s = str(v).strip().replace("\n", "").replace("\r", "")
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    s = re.sub(r"[\s.,]", "", s).upper()
    return s


def tabla(filas: list[list], fila_encabezado: int = 0) -> pd.DataFrame:
    """Filas crudas → DataFrame con columnas por LETRA (A, B, …), sin las filas de encabezado."""
    datos = filas[fila_encabezado + 1:]
    ancho = max((len(r) for r in filas), default=0)
    df = pd.DataFrame([list(r) + [""] * (ancho - len(r)) for r in datos],
                      columns=[get_column_letter(i + 1) for i in range(ancho)])
    return df.fillna("")


def indice(df: pd.DataFrame, col_llave: str, normalizar=norm_doc) -> pd.DataFrame:
    """Primera fila por llave (como XLOOKUP), con la llave normalizada en el índice."""
    if df.empty or col_llave not in df:
        return pd.DataFrame()
    llave = df[col_llave].map(normalizar)
    d = df.assign(_k=llave)
    d = d[d["_k"] != ""].drop_duplicates("_k", keep="first")
    return d.set_index("_k")


def buscar(llaves: pd.Series, idx: pd.DataFrame, col: str, defecto="") -> pd.Series:
    if idx.empty or col not in idx:
        return pd.Series([defecto] * len(llaves), index=llaves.index, dtype=object)
    m = idx[col].to_dict()
    return pd.Series([m.get(k, defecto) if k else "" for k in llaves], index=llaves.index, dtype=object)


def vacio(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def num(v) -> float:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ cálculo
def calcular(base: pd.DataFrame, fuentes: dict[str, pd.DataFrame], remisiones: pd.DataFrame | None,
             hitos_pago: dict[str, str] | None = None) -> pd.DataFrame:
    """base: SEGUIMIENTO GENERAL actual (columnas por letra, desde la fila 5). Devuelve la misma tabla con las
    columnas calculadas reescritas y las manuales intactas."""
    out = base.copy()
    for c in [get_column_letter(i + 1) for i in range(len(ENCABEZADOS))]:
        if c not in out:
            out[c] = ""
    doc = out["F"].map(norm_doc)

    ver = indice(fuentes["Verificación IMPORT"], "G")
    crm = indice(fuentes["Reporte CRM"], "C")
    ori = indice(fuentes["Orientación IMPORT"], "L")
    form = indice(fuentes["Formación Import"], "G")
    sis = indice(fuentes["Reporte SIS"], "C", normalizar=norm_doc)          # llave: ID CRM
    aten = indice(fuentes["Reporte Atendidos STC"], "B")
    pend = indice(fuentes["Reporte Pendientes STC"], "B")
    par = fuentes["Parámetros"]

    # B · veces que aparece la cédula hasta esa fila (control de repetidas)
    cuenta = doc.groupby(doc).cumcount() + 1
    out["B"] = [("" if not k else int(n)) for k, n in zip(doc, cuenta)]

    # C · fecha de verificación
    out["C"] = buscar(doc, ver, "C")

    # N:U · CRM  (Verificador=Asesor, ID CRM, Fecha de alta, Nombre, Correo, Teléfono, Ad Network, Estado)
    for destino, origen in zip("N O P Q R S T U".split(), "H G A B E D I J".split()):
        out[destino] = buscar(doc, crm, origen)

    # E · tipo de base. CORRIGE (nov-2026): quien está en «Base JCO» toma su cohorte de esa pestaña (JCO, JCO_II,
    # JCO_3, JCO_4), sin importar el Ad Network del CRM. Antes salía en blanco para 698 personas de JCO_II (el CRM
    # dice «JCO_2», que no está en Parámetros) y como Bases/Pauta para quienes el CRM tenía otra campaña.
    jco = docs_jco(fuentes)
    adn = dict(zip(par["A"].astype(str).str.strip(), par["B"]))
    out["E"] = [tipo_base(k, a, adn, jco) for k, a in zip(doc, out["T"])]

    # G:M · evidencias cargadas en Drive (Verificación IMPORT J:P)
    for destino, origen in zip(DOCS_BASICOS, "J K L M N O P".split()):
        v = buscar(doc, ver, origen)
        out[destino] = ["" if not k else ("NO CARGADO" if vacio(x) else "CARGADO EN DRIVE") for k, x in zip(doc, v)]

    # V:X · verificación
    out["V"] = buscar(doc, ver, "I")
    out["W"] = buscar(doc, ver, "T")
    x = buscar(doc, ver, "U", defecto="--")
    out["X"] = x

    # Y:AH · orientación (CONSOLIDADO FCS)
    out["Y"] = buscar(doc, ori, "CY")
    id_crm = out["O"].map(norm_doc)
    out["Z"] = buscar(id_crm, sis, "B")
    nombres, apellidos = buscar(doc, ori, "O"), buscar(doc, ori, "P")
    out["AA"] = [("" if vacio(n) else f"{n} {a}".strip()) for n, a in zip(nombres, apellidos)]
    out["AB"] = buscar(doc, ori, "AB")
    out["AC"] = buscar(doc, ori, "AA")
    out["AD"] = buscar(doc, ori, "E")
    out["AE"] = buscar(doc, ori, "CK")
    out["AF"] = buscar(doc, ori, "CP")
    out["AG"] = buscar(doc, ori, "F")
    out["AH"] = buscar(doc, ori, "J")

    # AJ · remitido (Modelo n8n: col A cédula, col W URL de la evidencia)
    if remisiones is not None and not remisiones.empty:
        rem = indice(remisiones, "A")
        url = buscar(doc, rem, "W")
        out["AJ"] = ["" if not k else ("Remitido" if not vacio(u) else "Sin Remitir") for k, u in zip(doc, url)]

    # AK:AO · formación (CONSOLIDADO de formación)
    for destino, origen in zip(["AK", "AL", "AM", "AN", "AO"], ["AK", "AL", "AM", "AN", "Z"]):
        out[destino] = buscar(doc, form, origen)
    out["AT"] = buscar(doc, ori, "BC")
    out["AU"] = buscar(doc, form, "M")
    out["AW"] = buscar(doc, form, "AJ")
    estado_f = buscar(doc, form, "O")
    reporte = out["AE"].astype(str).str.strip()
    # «SIN INSCRIBIR» solo aplica si la orientación terminó (col. AE = FINALIZADO o FINALIZADO PENDIENTE X
    # REMISIÓN); si no, queda vacío. Los demás estados pasan tal como vienen del consolidado de formación.
    fin_ori_ax = reporte.isin(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"])
    out["AX"] = ["" if not k else ("" if str(e).strip().upper() == "SIN INSCRIBIR" and not f else e)
                 for k, e, f in zip(doc, estado_f, fin_ori_ax)]
    out["AS"] = ["" if (a in ("BÁSICO", "") or vacio(a)) else (40 if j == "SI" else 20)
                 for a, j in zip(out["AX"], out["AD"])]
    out["AY"] = buscar(doc, form, "AC")
    out["AZ"] = buscar(doc, form, "Y")
    p1, p2 = buscar(doc, form, "AD"), buscar(doc, form, "AH")
    out["BA"] = ["" if not k else (a if num(a) > num(b) else b) for k, a, b in zip(doc, p1, p2)]
    out["BB"] = buscar(doc, form, "Y")
    out["BC"] = buscar(doc, form, "AP")

    # BF · estado en la plataforma STC (primero Pendientes, si no Atendidos)
    pv, av = buscar(doc, pend, "T"), buscar(doc, aten, "V")
    out["BF"] = [p if not vacio(p) else a for p, a in zip(pv, av)]

    # BI:BK · mes de entrega, encuesta y tipo de paquete reportado. BI y BK siguen saliendo del hito que reporta el
    # Consolidado FCS («Reportado Julio/Agosto/…», col. DB) con Parámetros, como antes; BH se calcula al final.
    hito_reporte = buscar(doc, ori, "DB")
    mes = dict(zip(par["I"].astype(str).str.strip(), par["J"]))
    out["BI"] = [mes.get(str(h).strip(), "") if not vacio(h) else "" for h in hito_reporte]
    out["BJ"] = buscar(doc, ori, "DC")
    tipo = dict(zip(par["H"].astype(str).str.strip(), par["N"]))
    out["BK"] = [tipo.get(f"{h}{a}".strip(), "") if not vacio(h) else "" for h, a in zip(hito_reporte, out["AH"])]

    # BE · momento del proceso
    paquete = out["AH"].astype(str).str.strip()
    w = out["W"].astype(str).str.strip()
    id_sis = out["Z"].map(num)
    sin_docs = w.isin(["", "Sin Documentos"])
    formado = out["AX"].astype(str).str.strip().eq("FINALIZADO")
    fin_ori = reporte.isin(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"])
    momento = []
    for pq, sd, s, fo, fm in zip(paquete, sin_docs, id_sis, fin_ori, formado):
        if sd:
            momento.append("0.Sin gestión")
        elif s <= 0:
            momento.append("1.En verificación")
        elif pq == "BÁSICO":
            momento.append("3.Orientado" if fo else "2.Verificado")
        elif pq == "ESPECIALIZADO":
            momento.append(("4.Formado" if fm else "3.Orientado") if fo else "2.Verificado")
        else:
            momento.append("2.Verificado")
    out["BE"] = momento

    # BN:BS · banderas por etapa y BT · momento (Back UP), con la baja del CRM
    out["BN"] = sin_docs.astype(int).tolist()
    out["BO"] = ((~sin_docs) & (id_sis == 0)).astype(int)
    out["BP"] = (id_sis > 0).astype(int)
    out["BQ"] = ((id_sis > 0) & reporte.isin(["FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"])).astype(int)
    out["BR"] = out["AX"].astype(str).str.strip().eq("FINALIZADO").astype(int)
    out["BS"] = out["AX"].astype(str).str.strip().eq("CERTIFICADO").astype(int)
    baja = buscar(doc, crm, "L")
    es_baja = baja.map(lambda v: v is True or str(v).strip().upper() == "TRUE")
    out["BT"] = [
        "6.Baja" if b else "5.Certificado" if s_ else "4.Formado" if r else "3.Orientado" if q else
        "2.Verificado" if p else "1.En verificación" if o else "0.Sin gestión"
        for b, s_, r, q, p, o in zip(es_baja, out["BS"], out["BR"], out["BQ"], out["BP"], out["BO"])]
    # BH · Hito = pago en que la SDDE aprobó a la persona («Pago 1», «Pago 2.1», …; ver entregas_pago.py). Sin
    # aprobación: «En ruta» si va en el proceso (Back UP entre 1 y 5) o vacío (0.Sin gestión o 6.Baja). Si no se
    # pudo leer la carpeta de entregas (hitos_pago=None), BH queda como estaba.
    if hitos_pago is not None:
        out["BH"] = [hitos_pago.get(k) or ("En ruta" if str(m)[:1] in "12345" and m else "")
                     for k, m in zip(doc, out["BT"])]

    # Filas sin cédula: todo lo calculado en blanco (las fórmulas llenaban «0.Sin gestión» en filas vacías).
    calculadas = [c for c in out.columns if c not in MANUALES]
    out[calculadas] = out[calculadas].astype(object)
    out.loc[doc == "", calculadas] = ""
    return out


COHORTES_JCO = {"": "JCO", "1": "JCO", "I": "JCO", "2": "JCO_II", "II": "JCO_II", "3": "JCO_3", "III": "JCO_3",
                "4": "JCO_4", "IV": "JCO_4"}


def es_jco(texto) -> bool:
    return str(texto).strip().upper().startswith("JCO")


def cohorte_jco(texto) -> str:
    """Nombre único de cohorte: «JCO» → JCO · «JCO_2», «JCO II», «JCO-II» → JCO_II · «JCO_3»/«JCO III» → JCO_3 ·
    «JCO_4»/«JCO IV» → JCO_4. Un texto que no es de JCO devuelve ""."""
    t = str(texto).strip().upper()
    if not t.startswith("JCO"):
        return ""
    sufijo = re.sub(r"[\s_\-]+", "", t[3:])
    return COHORTES_JCO.get(sufijo, "JCO_" + sufijo)


def docs_jco(fuentes: dict[str, pd.DataFrame]) -> dict[str, str]:
    """Cédula → cohorte según la pestaña «Base JCO» (col. D «Id de documento», col. K «Ad-Network*»)."""
    t = fuentes.get("Base JCO")
    if t is None or t.empty or "D" not in t:
        return {}
    salida = {}
    for d, adn in zip(t["D"], t["K"] if "K" in t else [""] * len(t)):
        k = norm_doc(d)
        if k and k not in salida:
            salida[k] = cohorte_jco(adn) or "JCO"
    return salida


def tipo_base(doc: str, ad_network, adn: dict, jco: dict) -> str:
    """Evento/Base (col. E): la cohorte de Base JCO (JCO, JCO_II, JCO_3, JCO_4) si la persona está ahí; «Revisar» si
    el CRM la tiene en una campaña JCO pero no está en Base JCO; si no, el tipo de Parámetros según el Ad Network."""
    if not doc:
        return ""
    if doc in jco:
        return jco[doc]
    tipo = adn.get(str(ad_network).strip(), "") if not vacio(ad_network) else ""
    if es_jco(ad_network) or es_jco(tipo):
        return "Revisar"  # campaña JCO en el CRM pero no está en Base JCO: lo valida el equipo
    return tipo


def auditoria_jco(tabla: pd.DataFrame, fuentes: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Casos para revisar: personas de Base JCO y su identificación en el seguimiento, el CRM y la orientación."""
    base = fuentes.get("Base JCO", pd.DataFrame())
    if base.empty or "D" not in base:
        return pd.DataFrame(columns=["Cédula", "Nombre", "Hallazgo", "Ad Network Base JCO", "Ad Network CRM",
                                     "JCO en orientación"])
    seg = tabla.assign(_k=tabla["F"].map(norm_doc)).drop_duplicates("_k").set_index("_k")
    filas = []
    vistos = set()
    for _, r in base.iterrows():
        k = norm_doc(r.get("D", ""))
        if not k:
            continue
        nombre = f"{r.get('A', '')} {r.get('B', '')}".strip()
        adn_b = r.get("K", "")
        if k in vistos:
            filas.append((k, nombre, "Cédula repetida en Base JCO", adn_b, "", ""))
            continue
        vistos.add(k)
        if k not in seg.index:
            filas.append((k, nombre, "No está en el seguimiento (se agrega al final)", adn_b, "", ""))
            continue
        s = seg.loc[k]
        adn_c, ori = s.get("T", ""), s.get("AD", "")
        if vacio(adn_c):
            filas.append((k, nombre, "Sin registro en el CRM", adn_b, adn_c, ori))
        elif not es_jco(adn_c):
            filas.append((k, nombre, "En Base JCO pero el CRM tiene otra campaña", adn_b, adn_c, ori))
        elif cohorte_jco(adn_c) != (cohorte_jco(adn_b) or "JCO"):
            filas.append((k, nombre, "Cohorte distinta en Base JCO y en el CRM (vale la de Base JCO)", adn_b, adn_c,
                          ori))
        if str(ori).strip().upper() == "NO":
            filas.append((k, nombre, "En Base JCO pero orientación dice JCO = NO", adn_b, adn_c, ori))
    jco = docs_jco(fuentes)
    for k, s in seg.iterrows():
        if not k or k in jco:
            continue
        if str(s.get("AD", "")).strip().upper() == "SI":
            filas.append((k, s.get("Q", "") or s.get("AA", ""), "Orientación dice JCO = SI pero no está en Base JCO",
                          "", s.get("T", ""), "SI"))
        elif es_jco(s.get("T", "")):
            filas.append((k, s.get("Q", ""), "CRM con campaña JCO pero no está en Base JCO", "", s.get("T", ""),
                          s.get("AD", "")))
    return pd.DataFrame(filas, columns=["Cédula", "Nombre", "Hallazgo", "Ad Network Base JCO", "Ad Network CRM",
                                        "JCO en orientación"])


def faltantes(base: pd.DataFrame, fuentes: dict[str, pd.DataFrame]) -> list[str]:
    """Cédulas de Orientación, Verificación o Base JCO que aún no están en el seguimiento (antes: CONTROL DE
    FALTANTES, que no miraba Base JCO)."""
    en_seg = set(base["F"].map(norm_doc))
    nuevas = []
    for t, col in (("Orientación IMPORT", "L"), ("Verificación IMPORT", "G"), ("Base JCO", "D")):
        if t not in fuentes or col not in fuentes[t]:
            continue
        for v in fuentes[t][col]:
            k = norm_doc(v)
            if k and k not in en_seg and k not in nuevas:
                nuevas.append(k)
    return nuevas
