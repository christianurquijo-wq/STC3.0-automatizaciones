"""Motor del CONSOLIDADO de «Seguimiento Formación STC 3.0»: calcula en pandas las columnas que antes eran
ARRAYFORMULA (MAP/LAMBDA/XLOOKUP sobre G2:G2013) y devuelve los valores listos para escribir.

Entradas (todas como DataFrame):
  * Pestañas que vienen de BigQuery (mismas columnas y nombres que dejaba el flujo de n8n): LOGS, ASISTENCIAS,
    LOG_ACCESS, USER_STATISTICS, NOTAS PUBLICADAS, SESIONES, REPORTE CRM, REPORTE SIS → columnas por NOMBRE.
  * Pestañas del mismo archivo que diligencia el equipo (CERTIFICADOS, Descargables, Respuestas de formulario 1,
    Hoja 31, Matriz Documental, Respuestas Encuestas de Cierre) el SEGUIMIENTO GENERAL (SG) y el archivo de tipo de documento
    → columnas por LETRA (A, B, …), como las leen las fórmulas.

Reglas: las mismas de las fórmulas de nov-2026. Donde la fórmula tenía un error evidente se corrige y se marca
«CORRIGE» (ver README_FORMACION.md):
  * P/Q/R (sesión de hoy): la fórmula usaba AND() dentro de ARRAYFORMULA (evalúa TODA la columna), así que a
    certificados o «SIN INSCRIBIR» también les buscaba sesión. Ahora solo a INSCRITO / EN CURSO.
  * AQ (cantidad de logs): la consulta trae una fila vacía por usuario sin ingresos; contaba como 1 log. Ahora solo
    cuenta filas con LOG_ID.
  * L/M/N: si el usuario tiene varias filas en el SIS (básico + especializado), se toma la del especializado (antes
    la primera que apareciera, que podía ser la del básico y dejarlo como «SIN INSCRIBIR»).
  * E: «NO TIENE» / «NO APLICA» en el segundo apellido se omiten (la expresión regular tenía un «r'» de más).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Seguimiento_general"))
from motor_seguimiento import get_column_letter, letra, norm_doc  # noqa: E402

ZONA = "America/Bogota"

# Encabezados de la fila 1 de CONSOLIDADO (A:BI). El script escribe por posición: si alguien mueve una columna, se
# detiene antes de escribir.
ENCABEZADOS = [
    " ", "Adnetwork", "ID CRM", "ID SIS", "NOMBRE Y APELLIDO", "TIPO DE DOCUMENTO", "No. DOCUMENTO",
    "NÚMERO DE CONTACTO", "CORREO ELECTRONICO", "USUARIO PLATAFORMA LMS", "CONTRASEÑA LMS", "GROUP_ID",
    "NOMBRE DEL CURSO", "PROGRAMA", "ESTADO DE LA FORMACIÓN", "SESSION_ID", "NÚMERO SESIÓN", "PRÓXIMA SESIÓN",
    "RECORDATORIO 1 TEMPORAL", "RECORDATORIO 2 TEMPORAL", "RECORDATORIO SESSION ID", "CURSO SEGÚN FCS", "VERF FCS",
    "FECHA DE INICIO (DD/MM/AAAA)", "FECHA DE FINALIZACIÓN (DD/MM/AAAA)", "VERF DATE", "% ASISTENCIA",
    "CANTIDAD DE REGISTROS DE ASISTENCIA (Forms)", "FECHA ASISTENCIA A CLASE", "% AVANCE PLAT",
    "Asistencia publicada", "Progreso publicado", "Nota final publicada", "VERIF", "Responsable", "",
    "N° VECES CONTACTADO", "ULTIMO ESTADO GESTIÓN", "OBSERVACIONES", "FECHA DE CERTIFICACIÓN", "CERTIFICADO",
    "CONSOLIDADO DE FORMACIÓN", "CANTIDAD DE LOGS", "TIEMPO DE LOGUEO", "TIEMPO SINCRÓNICO", "TOTAL TIEMPO CURSO",
    "PAQUETE DE PAGO", "OBSERVACION EVIDENCIA PAQUETE", "CARRIL", "NOTA PUBLICADA", "ESTADO PUBLICACIÓN CARRIL",
    "ALERTA PUBLICACIÓN", "ESTADO PAQUETE", "PAQUETE", "COMUNICADO FINALIZACIÓN RUTA", "ENVÍO CERTIFICADO", "",
    "ESTADO MATRIZ DOCUMENTAL", "ENCUESTA DE CIERRE ENVIADA", "ENCUESTA DE CIERRE DILIGENCIADA",
    "CANTIDAD DE CORREOS ENVIADOS", "OBSERVACIÓN SEGUIMIENTO GENERAL",
]
TERMINADOS = ("FINALIZADO", "CERTIFICADO")  # terminaron formación: nunca se retiran de CONSOLIDADO
COLUMNAS = [get_column_letter(i + 1) for i in range(len(ENCABEZADOS))]  # A … BI
# Columnas que diligencia el equipo (o que escribe otro proceso): el script nunca las toca. G es la llave: solo se
# escriben las cédulas nuevas al final.
MANUALES = ["G", "S", "T", "AI", "AK", "AL", "AM", "BC", "BD", "BG", "BI"]
CALCULADAS = [c for c in COLUMNAS if c not in MANUALES]

# Listas que estaban escritas dentro de las fórmulas (para cambiarlas, editar aquí).
INSUBSANABLES = {"1025530422", "1000595525", "1028820625", "1031178978", "1007101659", "1025324147", "1027524945"}
FECHA_FIN_FIJA = {"1024460134": "04/11/2026", "1000786870": "04/11/2026", "1028480350": "04/11/2026"}
MESES_PAQUETE = [("julio", "1"), ("agosto", "2"), ("septiembre", "3"), ("octubre", "3.1"), ("noviembre", "4")]


# ------------------------------------------------------------------ utilidades
def vacio(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and v.strip() == "")


def numero(v):
    """Número de la celda o None (acepta coma decimal)."""
    if vacio(v) or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


def sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def plano(v) -> str:
    """Mayúsculas, sin tildes, sin espacios dobles."""
    return " ".join(sin_tildes(str(v or "")).upper().split())


def limpiar(t) -> str:
    """TRIM de Sheets: sin saltos/tabulaciones/espacios duros y con un solo espacio entre palabras."""
    t = str(t or "")
    for ch in ("\n", "\r", " ", "\t"):
        t = t.replace(ch, " ")
    return " ".join(t.split())


def fecha(v):
    """Fecha (sin hora) de lo que haya en la celda: texto ISO («2026-11-05T16:22:58-05:00» → la parte antes de la
    T, como hacía la fórmula), «dd/mm/aaaa», serial de Sheets o datetime. None si no se puede leer."""
    if vacio(v) or isinstance(v, bool):
        return None
    if isinstance(v, pd.Timestamp) or hasattr(v, "year"):
        t = pd.Timestamp(v)
        if t.tzinfo is not None:
            t = t.tz_convert(ZONA).tz_localize(None)
        return t.normalize()
    if isinstance(v, (int, float)):
        if v <= 0:
            return None
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
    s = str(v).strip().lstrip("'")
    if "T" in s:
        s = s[: s.find("T")]
    try:
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", s):
            return pd.Timestamp(s)
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", s):
            return pd.to_datetime(s, dayfirst=True)
    except (ValueError, OverflowError):
        return None
    return None


def ddmmaaaa(t) -> str:
    return t.strftime("%d/%m/%Y") if t is not None else "--"


def primero(llaves, valores) -> dict:
    """{llave: valor de la PRIMERA fila con esa llave} (como XLOOKUP)."""
    d = {}
    for k, v in zip(llaves, valores):
        if k and k not in d:
            d[k] = v
    return d


def ultimo(llaves, valores) -> dict:
    """{llave: valor de la ÚLTIMA fila} (XLOOKUP con búsqueda desde el final, -1)."""
    d = {}
    for k, v in zip(llaves, valores):
        if k:
            d[k] = v
    return d


def col(df: pd.DataFrame | None, c: str) -> pd.Series:
    if df is None or df.empty or c not in df:
        return pd.Series([], dtype=object)
    return df[c]


def llaves(df, c) -> list[str]:
    return [norm_doc(v) for v in col(df, c)]


def entero_si_numero(v):
    """«3109» o 3109.0 → 3109 (las fórmulas devolvían el número de la pestaña); el resto, igual."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and not pd.isna(v) and v.is_integer():
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"\d{1,15}", v.strip()):
        return int(v.strip())
    return v


# ------------------------------------------------------------------ cálculo
def calcular(base: pd.DataFrame, f: dict[str, pd.DataFrame], hoy: pd.Timestamp,
             tipo_doc: pd.DataFrame | None = None, observaciones: dict[str, str] | None = None) -> pd.DataFrame:
    """base: CONSOLIDADO actual con columnas por letra (A … BI). Devuelve la tabla completa (mismas letras) con las
    columnas calculadas llenas; las manuales se devuelven tal como estaban."""
    hoy = pd.Timestamp(hoy).normalize()
    out = base.copy()
    for c in COLUMNAS:
        if c not in out:
            out[c] = ""
    n = len(out)
    g_raw = out["G"].tolist()
    doc = [norm_doc(v) for v in g_raw]
    hay = [d != "" for d in doc]

    def serie(valores):
        return pd.Series(list(valores), index=out.index, dtype=object)

    # A · veces que aparece la cédula en G
    cuenta = pd.Series([d for d in doc if d]).value_counts().to_dict()
    out["A"] = serie(cuenta.get(d, "") if d else "" for d in doc)

    # B, C, H, I · REPORTE CRM por documento
    crm = f.get("REPORTE CRM")
    kc = llaves(crm, "Documento")
    for destino, origen in (("B", "Adnetwork"), ("C", "ID CRM"), ("H", "Telefono"), ("I", "Correo")):
        m = primero(kc, col(crm, origen))
        out[destino] = serie((entero_si_numero(m.get(d, "--")) if d else "") for d in doc)
    out["J"] = out["I"]
    out["K"] = serie(entero_si_numero(v) if h else "" for v, h in zip(g_raw, hay))

    # D · ID SIS: por ID CRM y, si no, por cédula
    sis = f.get("REPORTE SIS")
    sis_por_crm = primero(llaves(sis, "ID CRM"), col(sis, "ID"))
    sis_por_doc = primero(llaves(sis, "Cedula"), col(sis, "ID"))
    out["D"] = serie(
        "" if not d else entero_si_numero(sis_por_crm.get(norm_doc(c), sis_por_doc.get(d, "--")))
        for d, c in zip(doc, out["C"]))
    id_sis = [norm_doc(v) if h and v != "--" else "" for v, h in zip(out["D"], hay)]

    # L, M, N · grupo, programa y paquete del SIS (CORRIGE: se prefiere la fila del especializado)
    s_sis = pd.DataFrame({"k": llaves(sis, "ID"), "grupo": col(sis, "Group_id").tolist(),
                          "prog": col(sis, "Programa").tolist(), "paq": col(sis, "Paquete").tolist()})
    if not s_sis.empty:
        s_sis["esp"] = s_sis["paq"].map(lambda p: "ESPECIALIZADO" in plano(p))
        s_sis = s_sis[s_sis["k"] != ""].sort_values("esp", ascending=False, kind="stable").drop_duplicates("k")
    fila_sis = s_sis.set_index("k").to_dict("index") if not s_sis.empty else {}

    def programa(p):
        p = str(p or "").upper().replace("40H", "").replace("20H", "").strip()
        for a, b in zip("ÁÉÍÓÚ", "AEIOU"):
            p = p.replace(a, b)
        return p

    out["L"] = serie((fila_sis[s]["grupo"] if s in fila_sis else "--") if h else "" for s, h in zip(id_sis, hay))
    out["M"] = serie((programa(fila_sis[s]["prog"]) if s in fila_sis else "--") if h else ""
                     for s, h in zip(id_sis, hay))
    out["N"] = serie((str(fila_sis[s]["paq"] or "").upper() if s in fila_sis else "--") if h else ""
                     for s, h in zip(id_sis, hay))
    grupo = [str(g) if h and g not in ("", "--") else "" for g, h in zip(out["L"], hay)]

    # SEGUIMIENTO GENERAL (columnas por letra, una fila por cédula F): es la ÚNICA fuente de orientación. Ya trae lo
    # del Consolidado FCS: AA nombre, AG fecha de orientación (= fecha de atención), AT curso según FCS, BI mes de
    # entrega. Q (nombre del CRM) y el REPORTE CRM son el respaldo del nombre.
    sg = f.get("SG")
    ks = llaves(sg, "F")
    nom_sg, nom_q = primero(ks, col(sg, "AA")), primero(ks, col(sg, "Q"))
    nombre_crm = primero(kc, col(crm, "Estudiante"))

    def nombre(d):
        # AA del SG trae nombre + primer apellido (orientación); Q (CRM) suele traer el nombre completo. Se usa el
        # que tenga más palabras (en empate, el de orientación); si no hay ninguno, el REPORTE CRM.
        opciones = [limpiar(x.get(d, "")).upper() for x in (nom_sg, nom_q)]
        opciones = [o for o in opciones if o and o != "--"]
        if opciones:
            return max(opciones, key=lambda o: len(o.split()))
        return limpiar(nombre_crm.get(d, "")).upper() or "--"

    out["E"] = serie(nombre(d) if d else "" for d in doc)

    # F · tipo de documento (archivo 1DG2xGi…, K por L, el mismo que usaba la fórmula; el SG no lo trae)
    tipo = primero(llaves(tipo_doc, "L"), col(tipo_doc, "K")) if tipo_doc is not None else {}
    out["F"] = serie((tipo.get(d) or "") if d else "" for d in doc)

    curso_sg = primero(ks, col(sg, "AT"))
    out["V"] = serie(str(curso_sg.get(d, "") or "").replace("_", " ") if d else "" for d in doc)
    out["W"] = serie((plano(m) == plano(v)) if d else "" for d, m, v in zip(doc, out["M"], out["V"]))

    # X · fecha de inicio = fecha de orientación del SG (col. AG, que es la fecha de atención del FCS)
    atencion = primero(ks, col(sg, "AG"))
    out["X"] = serie(ddmmaaaa(fecha(atencion.get(d))) if d else "" for d in doc)

    # AA · asistencia: 1 si tiene al menos una sesión con estado 100
    asis = f.get("ASISTENCIAS")
    a_k = llaves(asis, "ID_SIS")
    a_st = [numero(v) or 0 for v in col(asis, "ATTENDANCE_STATUS")]
    a_fe = [fecha(v) for v in col(asis, "FECHA_ASISTENCIA")]
    asistio = {k for k, s in zip(a_k, a_st) if k and s == 100}
    out["AA"] = serie((1 if s in asistio else 0) if h else "" for s, h in zip(id_sis, hay))

    # Fecha más temprana en que cada fuente llegó al 100 % (PRIMERA_FECHA de la fórmula de Y)
    def primera_fecha(claves, progresos, fechas) -> dict:
        d = {}
        for k, p, t in zip(claves, progresos, fechas):
            p = numero(p)
            if k and p is not None and p >= 99.99:
                t = t if t is not None else None
                if k not in d or (t is not None and (d[k] is None or t < d[k])):
                    d[k] = t
        return d

    logs = f.get("LOGS")
    l_k = llaves(logs, "ID_SIS")
    f_logs = primera_fecha(l_k, col(logs, "PROGRESO_PROGRAMA"), [fecha(v) for v in col(logs, "FECHA_LOG_PROGRAMA")])
    f_asis = primera_fecha(a_k, a_st, a_fe)
    us = f.get("USER_STATISTICS")
    u_k = llaves(us, "ID_SIS")
    f_user = primera_fecha(u_k, col(us, "PROGRESO"),
                           [fecha(v) for v in col(us, "FECHA_FINALIZACION_ASINCRONICA")])

    # AD / AH · avance en plataforma
    u_g = [str(v or "") for v in col(us, "GROUP_ID")]
    prog_us = primero([f"{k}|{g}" for k, g in zip(u_k, u_g)], col(us, "PROGRESO"))
    # LOGS viene ordenado por FECHA_LOG_PROGRAMA descendente: la primera fila por usuario es su último log
    prog_log = primero(l_k, col(logs, "PROGRESO_PROGRAMA"))
    ad, ah = [], []
    for s, g, h in zip(id_sis, grupo, out["L"]):
        if not h or h == "" or not s:
            ad.append("")
            ah.append("")
            continue
        q = numero(prog_us.get(f"{s}|{g}")) if g else None
        w = numero(prog_log.get(s))
        ad.append("" if q is None and w is None else max(q or 0, w or 0) / 100)
        ah.append("" if q is None else q / 100)
    out["AD"] = serie(ad)
    out["AH"] = serie(ah)
    out["AJ"] = serie((a == b) if d else "" for d, a, b in zip(doc, out["AD"], out["AH"]))

    # CERTIFICADOS (por letra): H fecha, K enlace, N fecha fin, P paquete, Q estado paquete, U subido STC
    cert = f.get("CERTIFICADOS")
    kcert = llaves(cert, "C")
    c_h, c_k, c_n, c_p, c_q, c_u = (primero(kcert, col(cert, x)) for x in ("H", "K", "N", "P", "Q", "U"))
    out["AN"] = serie((c_h.get(d, "") if d else "") for d in doc)
    out["AO"] = serie((c_k.get(d, "") if d else "") for d in doc)
    out["BA"] = serie((c_q.get(d, "") if d else "") for d in doc)
    out["BB"] = serie((c_p.get(d, "") if d else "") for d in doc)

    def consolidado(d):
        if not d:
            return ""
        subido = c_u.get(d, False)
        if subido is True or str(subido).strip().upper() == "TRUE":
            return "Subido STC"
        p = c_p.get(d, "--")
        return "Generado" if not vacio(p) and p != "--" else "Sin Generar"

    out["AP"] = serie(consolidado(d) for d in doc)

    # O · estado de la formación
    def estado(d, n_, aa, ad_, ah_, cert_, x):
        if not vacio(cert_):
            return "CERTIFICADO"
        if not d:
            return ""
        if "ESPECIALIZADO" not in str(n_):
            return "SIN INSCRIBIR"
        if vacio(x):
            return "SIN INSCRIBIR"
        aa_, ad_n, ah_n = numero(aa) or 0, numero(ad_) or 0, numero(ah_) or 0
        if aa_ == 0 and ad_n == 0:
            return "INSCRITO"
        if aa_ == 1 and (ad_n == 1 or ah_n == 1):
            return "FINALIZADO"
        if aa_ > 0 or ad_n > 0:
            return "EN CURSO"
        return ""

    out["O"] = serie(estado(*t) for t in zip(doc, out["N"], out["AA"], out["AD"], out["AH"], out["AO"], out["X"]))

    # P, Q, R · sesión de hoy del grupo (SESIONES con fecha = hoy, programa distinto de Básico) y U · recordatorio
    ses = f.get("SESIONES")
    hoy_ses = {}
    enviado = primero([str(v or "") for v in col(ses, "CLASS_SESSION_ID")], col(ses, "ENVIADO"))
    if ses is not None and not ses.empty:
        for _, r in ses.iterrows():
            if fecha(r.get("STAR_DATE")) == hoy and str(r.get("PROGRAMA") or "") != "Básico":
                gid = str(r.get("STRUCTURE_ID") or "")
                if gid and gid not in hoy_ses:
                    hoy_ses[gid] = (r.get("CLASS_SESSION_ID"), r.get("NUMBER_SESSION"), r.get("MEET_LINK"))
    p, q, r_ = [], [], []
    for d, aa, est, g in zip(doc, out["AA"], out["O"], grupo):
        if not d:
            vals = ("", "", "")
        elif aa == 1:
            vals = ("FINALIZADO",) * 3
        elif est not in ("INSCRITO", "EN CURSO"):  # CORRIGE (ver encabezado)
            vals = ("--",) * 3
        else:
            vals = tuple(entero_si_numero(v) if not vacio(v) else "--" for v in hoy_ses.get(g, ("--",) * 3))
        p.append(vals[0])
        q.append(vals[1])
        r_.append(vals[2])
    out["P"], out["Q"], out["R"] = serie(p), serie(q), serie(r_)

    def bandera(v):
        return v is True or str(v).strip().upper() == "TRUE"

    out["U"] = serie((bandera(enviado[str(s)]) if str(s) in enviado else False) if d else ""
                     for d, s in zip(doc, out["P"]))

    # Y · fecha de finalización
    def fin(d, s, est):
        if not s:
            return "" if not d else "--"
        if d in FECHA_FIN_FIJA:
            return FECHA_FIN_FIJA[d]
        cands = [f_asis.get(s), f_user.get(s)]
        if est in ("FINALIZADO", "CERTIFICADO"):
            cands.append(f_logs.get(s))
        if est == "CERTIFICADO":
            cands.append(fecha(c_n.get(d)))
        cands = [c for c in cands if c is not None]
        return ddmmaaaa(max(cands)) if cands else "--"

    out["Y"] = serie(fin(d, s, e) for d, s, e in zip(doc, id_sis, out["O"]))

    # Z · verificación de fechas (deserción si lleva más días que el promedio)
    ini = [fecha(x) if x not in ("", "--") else None for x in out["X"]]
    ffin = [fecha(y) if y not in ("", "--") else None for y in out["Y"]]
    difs = [(b - a).days for a, b in zip(ini, ffin) if a is not None and b is not None and b > a]
    prom = sum(difs) / len(difs) if difs else 0

    def verf(est, x, y, a):
        if vacio(est) or x == "--":
            return ""
        if est in ("CERTIFICADO", "FINALIZADO"):
            return "*"
        if y == "" and a is not None:
            return "Deserción" if max(0, (hoy - a).days) > prom else "OK"
        return "*"

    out["Z"] = serie(verf(e, x, y, a) for e, x, y, a in zip(out["O"], out["X"], out["Y"], ini))

    # AB / AC · formulario de asistencia
    forms = f.get("Respuestas de formulario 1")
    kfo = llaves(forms, "C")
    n_forms = pd.Series([k for k in kfo if k]).value_counts().to_dict()
    out["AB"] = serie((n_forms.get(d, 0) if d else "") for d in doc)
    ult_form = ultimo(kfo, col(forms, "A"))
    asis_ord = sorted(((t, k) for k, s, t in zip(a_k, a_st, a_fe) if k and s == 100),
                      key=lambda x: (x[0] is None, x[0] or pd.Timestamp.min))
    prim_asis = {}
    for t, k in asis_ord:
        prim_asis.setdefault(k, t)

    def fecha_clase(d, s, aa):
        if not d:
            return ""
        if aa == 1:
            return ddmmaaaa(prim_asis.get(s))
        t = fecha(ult_form.get(d))
        return t.strftime("%d/%m/%Y") if t is not None else ""

    out["AC"] = serie(fecha_clase(d, s, aa) for d, s, aa in zip(doc, id_sis, out["AA"]))

    # AE, AF, AG · Descargables por ID SIS (última fila)
    desc = f.get("Descargables")
    kd = llaves(desc, "B")
    for destino, origen in (("AE", "C"), ("AF", "D"), ("AG", "E")):
        m = ultimo(kd, col(desc, origen))
        out[destino] = serie((m.get(s, "") if s else "") for s in id_sis)

    # AQ, AR, AS, AT · logs de acceso (CORRIGE: solo filas con LOG_ID) y tiempos
    la = f.get("LOG_ACCESS")
    if la is not None and not la.empty:
        lad = pd.DataFrame({"k": llaves(la, "PROFILE_DOC_NUMBER"), "id": col(la, "LOG_ID").tolist(),
                            "t": [numero(v) or 0 for v in col(la, "TIME_VIEW")]})
        lad = lad[lad["k"] != ""]
        n_logs = lad[~lad["id"].map(vacio)].groupby("k").size().to_dict()
        t_logs = lad.groupby("k")["t"].sum().to_dict()
    else:
        n_logs, t_logs = {}, {}
    out["AQ"] = serie((int(n_logs.get(d, 0)) if d else "") for d in doc)
    out["AR"] = serie((round(float(t_logs.get(d, 0)), 3) if d else "") for d in doc)
    out["AS"] = serie(((6 if aa == 1 else 0) if d else "") for d, aa in zip(doc, out["AA"]))
    out["AT"] = serie((round(ar + as_, 3) if d else "") for d, ar, as_ in zip(doc, out["AR"], out["AS"]))

    # AU · paquete de pago, desde el mes de entrega del SG (col. BI): julio → 1, agosto → 2, septiembre → 3,
    # octubre → 3.1, noviembre → 4 (las mismas equivalencias de la fórmula)
    mes_sg = primero(ks, col(sg, "BI"))
    nombres_mes = {7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}

    def paquete_pago(d):
        v = mes_sg.get(d, "") if d else ""
        if vacio(v):
            return ""
        t = fecha(v)
        x = nombres_mes.get(t.month, "") if t is not None else str(v).lower()
        if not x or "ruta" in x:
            return ""
        for mes, num in MESES_PAQUETE:
            if mes in x:
                return f"PAQUETE {num}"
        return f"PAQUETE {v}"

    out["AU"] = serie(paquete_pago(d) for d in doc)

    # AV · evidencia de paquete (Hoja 31, col. I)
    h31 = pd.Series([k for k in llaves(f.get("Hoja 31"), "I") if k]).value_counts().to_dict()
    out["AV"] = serie((h31.get(d, 0) if d else "") for d in doc)

    # AW, AX · carril y nota por (ID SIS, grupo); AY · estado de publicación del grupo
    notas = f.get("NOTAS PUBLICADAS")
    kn = [f"{s}|{str(g or '')}" for s, g in zip(llaves(notas, "ID_SIS"), col(notas, "GROUP_ID"))]
    carril, nota = primero(kn, col(notas, "CARRIL")), primero(kn, col(notas, "NOTA"))
    pub_grupo = primero([str(g or "") for g in col(notas, "GROUP_ID")], col(notas, "ESTADO_PUBLICACION"))
    out["AW"] = serie((carril.get(f"{s}|{g}", "") if s else "") if d else "" for d, s, g in zip(doc, id_sis, grupo))
    out["AX"] = serie((nota.get(f"{s}|{g}", "") if s else "") if d else "" for d, s, g in zip(doc, id_sis, grupo))
    out["AY"] = serie((pub_grupo.get(g, "") if g else "") if d else "" for d, g in zip(doc, grupo))

    def alerta(d, e, nt):
        if not d:
            return ""
        if e in ("CERTIFICADO", "FINALIZADO"):
            return "CONCUERDA NOTA" if numero(nt) == 5 else "ALERTA - REPUBLICAR NOTA"
        return ""

    out["AZ"] = serie(alerta(d, e, nt) for d, e, nt in zip(doc, out["O"], out["AX"]))

    # BE · insubsanables · BF · matriz documental · BH · encuesta de cierre
    out["BE"] = serie(("INSUBSANABLE" if d in INSUBSANABLES else "") if d else "" for d in doc)
    mat = primero(llaves(f.get("Matriz Documental"), "D"), col(f.get("Matriz Documental"), "AX"))
    out["BF"] = serie((mat.get(d, "") if d else "") for d in doc)
    enc = set(llaves(f.get("Respuestas Encuestas de Cierre"), "J"))
    out["BH"] = serie(("SI" if (str(bg).strip().upper() == "SI" and d in enc) else "") if d else ""
                      for d, bg in zip(doc, out["BG"]))

    # BJ · observación: por qué la persona no es especializado vigente en el SG (vacío si lo es)
    obs = observaciones or {}
    out["BJ"] = serie((obs.get(d, "") if d else "") for d in doc)

    # Filas sin cédula: todo lo calculado en blanco
    vacias = [i for i, h in zip(out.index, hay) if not h]
    if vacias:
        out.loc[vacias, CALCULADAS] = ""
    return out[COLUMNAS]


def especializados_sg(sg: pd.DataFrame) -> list[str]:
    """Cédulas del SEGUIMIENTO GENERAL (columnas por letra, desde la fila 5) que deben estar en formación: paquete
    ESPECIALIZADO (AH), orientación finalizada (AE = FINALIZADO / FINALIZADO PENDIENTE X REMISIÓN) y sin baja (BT ≠
    6.Baja). En el orden del seguimiento, sin repetidas."""
    vistos, salida = set(), []
    for d, paq, rep, bt in zip(col(sg, "F"), col(sg, "AH"), col(sg, "AE"), col(sg, "BT")):
        k = norm_doc(d)
        if not k or k in vistos:
            continue
        if plano(paq) != "ESPECIALIZADO":
            continue
        if plano(rep) not in ("FINALIZADO", "FINALIZADO PENDIENTE X REMISION"):
            continue
        if str(bt).strip().startswith("6"):
            continue
        vistos.add(k)
        salida.append(k)
    return salida


def situacion_sg(sg: pd.DataFrame) -> dict[str, str]:
    """{cédula: por qué no es especializado vigente} para explicar en «Control script» a quien está en formación
    pero ya no cumple el criterio del Seguimiento General."""
    d = {}
    for doc_, paq, rep, bt in zip(col(sg, "F"), col(sg, "AH"), col(sg, "AE"), col(sg, "BT")):
        k = norm_doc(doc_)
        if not k or k in d:
            continue
        if str(bt).strip().startswith("6"):
            d[k] = "Baja en el CRM (6.Baja)"
        elif plano(paq) != "ESPECIALIZADO":
            d[k] = f"Paquete en orientación: {paq or 'vacío'}"
        elif plano(rep) not in ("FINALIZADO", "FINALIZADO PENDIENTE X REMISION"):
            d[k] = f"Orientación sin finalizar (Reporte: {rep or 'vacío'})"
        else:
            d[k] = ""
    return d


def cedula_rara(k: str) -> str:
    """Motivo para revisar una cédula (vacío si se ve bien). Cédulas colombianas: 6 a 10 dígitos; pasaportes / PPT
    pueden traer letras. Una cédula con formato de fecha en la hoja llega como «29/03/2004» o como un número corto."""
    if not k:
        return ""
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}.*", k):
        return "Parece una fecha: la celda tiene formato de fecha en la hoja de origen"
    if k.isdigit() and len(k) < 6:
        return "Muy corta (menos de 6 dígitos): revisar si la celda tenía formato de fecha"
    if k.isdigit() and len(k) > 11:
        return "Muy larga (más de 11 dígitos)"
    return ""


COLUMNAS_SIS_SIN = ["ID SIS", "ID CRM", "Cédula", "Estudiante", "Correo", "Teléfono", "Paquete", "Programa",
                    "Group_id", "Fecha de Matrícula", "Estado Académico", "Principal"]


def sis_sin_seguimiento(sis: pd.DataFrame, sg: pd.DataFrame | None, base: pd.DataFrame) -> pd.DataFrame:
    """Usuarios del SIS con paquete Especializado que no están NI en el Seguimiento General NI en CONSOLIDADO.
    Se cruza por cédula, ID SIS e ID CRM (si coincide cualquiera de las tres, la persona sí está), para que una
    cédula mal digitada no la haga aparecer como faltante. Una fila por ID SIS."""
    docs, sis_ids, crms = set(), set(), set()
    for df_, c_doc, c_sis, c_crm in ((sg, "F", "Z", "O"), (base, "G", "D", "C")):
        if df_ is None or df_.empty:
            continue
        docs |= {k for k in llaves(df_, c_doc) if k}
        sis_ids |= {k for k in llaves(df_, c_sis) if k and k != "--"}
        crms |= {k for k in llaves(df_, c_crm) if k and k != "--"}
    filas, vistos = [], set()
    if sis is None or sis.empty:
        return pd.DataFrame(columns=COLUMNAS_SIS_SIN)
    for _, r in sis.iterrows():
        if "ESPECIALIZADO" not in plano(r.get("Paquete")):
            continue
        s, c, d = norm_doc(r.get("ID")), norm_doc(r.get("ID CRM")), norm_doc(r.get("Cedula"))
        if not s or s in vistos:
            continue
        vistos.add(s)
        if s in sis_ids or (c and c in crms) or (d and d in docs):
            continue
        filas.append([entero_si_numero(r.get("ID")), entero_si_numero(r.get("ID CRM")), entero_si_numero(r.get("Cedula")),
                      r.get("Estudiante"), r.get("Correo"), r.get("Telefono"), r.get("Paquete"), r.get("Programa"),
                      r.get("Group_id"), r.get("Fecha de Matrícula"), r.get("Estado Académico"), r.get("Principal")])
    return pd.DataFrame(filas, columns=COLUMNAS_SIS_SIN)


def depurar(base: pd.DataFrame, vigentes: set[str], estados: pd.Series | None = None
            ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(filas que se quedan, filas que salen): quedan los especializados vigentes del SG y, pase lo que pase, quien
    terminó formación (estado FINALIZADO o CERTIFICADO, en `estados` alineado con `base`)."""
    k = base["G"].map(norm_doc)
    queda = k.isin(vigentes)
    if estados is not None:
        queda |= estados.reindex(base.index).astype(str).str.strip().str.upper().isin(TERMINADOS)
    return base[queda].reset_index(drop=True), base[~queda & (k != "")].reset_index(drop=True)


def con_nuevas(base: pd.DataFrame, cedulas: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Agrega al final las cédulas que no están en G. Devuelve (tabla, nuevas)."""
    actuales = {norm_doc(v) for v in base["G"]}
    # Cédulas con forma de fecha o de largo imposible NO se agregan (quedan en «Control script» para corregirlas en
    # el Seguimiento General; en la siguiente ejecución, ya corregidas, entran solas).
    nuevas = [c for c in cedulas if c not in actuales and not cedula_rara(c)]
    if not nuevas:
        return base, []
    extra = pd.DataFrame({c: [""] * len(nuevas) for c in base.columns})
    extra["G"] = [entero_si_numero(c) for c in nuevas]
    return pd.concat([base, extra], ignore_index=True), nuevas
