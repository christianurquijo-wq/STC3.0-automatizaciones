"""«Reporte CRM» y «Reporte SIS» del Seguimiento General, directo de BigQuery (reemplaza el flujo de n8n que pegaba
estas consultas en la hoja).

Credencial: la llave JSON de n8n-bigquery-reader@potent-poetry-284019.iam.gserviceaccount.com. Se busca en este
orden: BQ_SA_FILE en el .env (ruta relativa a la raíz del repo o absoluta) → cualquier .json de la raíz del repo o de
CONFIG_SEGURIDAD cuyo client_email sea esa cuenta (o BQ_SA_EMAIL si se define). Las consultas corren en el proyecto
de la cuenta (potent-poetry-284019), salvo que BQ_PROJECT diga otro.

Las pestañas se reescriben con el MISMO orden de columnas que ya usan (las fórmulas de control que tienen a la
derecha —Reporte CRM M:P— no se tocan).
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CUENTA_BQ = "n8n-bigquery-reader@potent-poetry-284019.iam.gserviceaccount.com"

SQL_CRM = """
SELECT
FORMAT_DATE('%Y-%m-%d',DATE(TIMESTAMP(CREATED_AT))) AS `Fecha de Alta`,
CONTACT_DATA_FULL_NAME AS `Estudiante`,
CONTACT_DATA_DOCUMENT_ID AS Documento,
CONTACT_DATA_MOBILE_PHONE AS Telefono,
CONTACT_DATA_EMAIL AS Correo,
PROGRAM_DATA_NAME AS Programa,
CAST(CONTACT_DATA_INCREMENTAL_CONTACT_CODE AS STRING) AS `ID CRM`,
SALES_ADVISOR_DATA_FIRST_NAME AS Asesor,
CONTACT_DATA_ADNETWORK_NAME AS Adnetwork,
LEAD_STATUS_DATA_NAME AS Estado,
CAMPAIGN_DATA_NAME AS `Campaña`,
UNSUBSCRIBED_DATA_IS_UNSUBSCRIBED AS Baja
FROM `potent-poetry-284019.DSS3_CRM.ES3200060_lead`
ORDER BY CREATED_AT DESC
"""

SQL_SIS = """
SELECT
  FORMAT_DATE('%Y-%m-%d',DATE(TIMESTAMP(A.CREATED_AT))) AS `Fecha de Matrícula`,
  A.INCREMENTAL_USER_CODE AS ID,
  A.PROFILE_DOC_NUMBER AS Cedula,
  B.INCREMENTAL_CONTACT_CODE AS `ID CRM`,
  A.PROFILE_FULL_NAME AS Estudiante,
  A.PROFILE_EMAIL AS Correo,
  A.PROFILE_PHONE AS Telefono,
  D.NAME AS Paquete,
  GP.NAME AS `Programa`,
  GP._ID AS `Group_id`,
  G.NAME AS `Estado Académico`,
  PARENT.NAME AS `Principal`,
  A._ID AS USER_ID
FROM `potent-poetry-284019.DSS3_SIS.ES3100010_user` A
LEFT JOIN `potent-poetry-284019.DSS3_CRM.ES3200020_enrollment` B ON A._ID = B.USER_SIS
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100012_programs` C ON A._ID = C.__USER
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100100_structure` D ON C.STRUCTURE = D._ID
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100100_structure` P ON D._ID = P.PARENT
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100100_structure` S ON P._ID = S.PARENT
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100100_structure` GP ON S._ID = GP.PARENT
INNER JOIN `potent-poetry-284019.DSS3_SIS.ES3100101_config_users` CFG ON GP._ID = CFG.__STRUCTURE AND A._ID = CFG.USER
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100145_structure_category` E ON D.STRUCTURE_CATEGORY_ID = E._ID
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100013_business_statuses` F
  ON F.__MODEL = A._ID AND F.CATEGORY = '607e16f2b09b1b7183cccd1e'
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100210_business_status` G ON G._ID = F.BUSINESS_STATUS
LEFT JOIN `potent-poetry-284019.DSS3_SIS.ES3100210_business_status` PARENT ON G.PARENT = PARENT._ID
ORDER BY A.INCREMENTAL_USER_CODE DESC
"""

# Orden de columnas de cada pestaña (el que leen el motor y las fórmulas de la hoja). El SIS se reordena: en la
# consulta la cédula va 3.ª, en la pestaña va al final (col. M) y el ID CRM en la C.
COLUMNAS = {
    "Reporte CRM": ["Fecha de Alta", "Estudiante", "Documento", "Telefono", "Correo", "Programa", "ID CRM", "Asesor",
                    "Adnetwork", "Estado", "Campaña", "Baja"],
    "Reporte SIS": ["Fecha de Matrícula", "ID", "ID CRM", "Estudiante", "Correo", "Telefono", "Paquete", "Programa",
                    "Group_id", "Estado Académico", "Principal", "USER_ID", "Cedula"],
}
CONSULTAS = {"Reporte CRM": SQL_CRM, "Reporte SIS": SQL_SIS}


def buscar_llave(raiz: Path) -> Path | None:
    ruta = os.getenv("BQ_SA_FILE", "").strip()
    if ruta:
        p = Path(ruta) if Path(ruta).is_absolute() else raiz / ruta
        return p if p.exists() else None
    cuenta = os.getenv("BQ_SA_EMAIL", "").strip() or CUENTA_BQ
    for carpeta in (raiz, raiz / "CONFIG_SEGURIDAD"):
        for p in sorted(carpeta.glob("*.json")):
            try:
                if json.loads(p.read_text(encoding="utf-8")).get("client_email") == cuenta:
                    return p
            except (OSError, ValueError):
                continue
    return None


def diagnostico(raiz: Path) -> str:
    """Qué .json hay y de qué cuenta es cada uno (sin mostrar llaves), para saber por qué no se encontró."""
    ruta = os.getenv("BQ_SA_FILE", "").strip()
    if ruta:
        return f"BQ_SA_FILE={ruta} no existe (se busca relativo a {raiz})."
    vistos = []
    for carpeta in (raiz, raiz / "CONFIG_SEGURIDAD"):
        for p in sorted(carpeta.glob("*.json")):
            try:
                correo = json.loads(p.read_text(encoding="utf-8")).get("client_email", "(sin client_email)")
            except (OSError, ValueError):
                correo = "(no se pudo leer)"
            vistos.append(f"{p.relative_to(raiz)} → {correo}")
    return "JSON encontrados: " + ("; ".join(vistos) if vistos else "ninguno") + "."


def _valor(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str)):
        return v
    return str(v)


def consultar(raiz: Path, log=print) -> dict[str, list[list]]:
    """{pestaña: [encabezados, fila1, …]} con el orden de COLUMNAS. Lanza excepción si no hay llave o falla."""
    from google.cloud import bigquery
    from google.oauth2.service_account import Credentials
    llave = buscar_llave(raiz)
    if llave is None:
        raise FileNotFoundError(f"no encontré la llave JSON de {os.getenv('BQ_SA_EMAIL') or CUENTA_BQ} "
                                f"(define BQ_SA_FILE en el .env). {diagnostico(raiz)}")
    cred = Credentials.from_service_account_file(str(llave),
                                                 scopes=["https://www.googleapis.com/auth/bigquery"])
    # «bigquery.readonly» no deja crear trabajos de consulta (403 insufficient authentication scopes); lo que limita
    # a solo lectura son los roles de la cuenta (Data Viewer + Job User), no el scope.
    cliente = bigquery.Client(credentials=cred, project=os.getenv("BQ_PROJECT", "").strip() or cred.project_id)
    log(f"BigQuery: {cred.service_account_email} · proyecto {cliente.project} · llave {llave.name}")

    def una(nombre: str) -> list[list]:
        filas = cliente.query(CONSULTAS[nombre]).result()
        orden = COLUMNAS[nombre]
        datos = [[_valor(f.get(c)) for c in orden] for f in filas]
        return [orden] + datos

    with ThreadPoolExecutor(max_workers=2) as ex:
        futuros = {n: ex.submit(una, n) for n in CONSULTAS}
        return {n: f.result() for n, f in futuros.items()}
