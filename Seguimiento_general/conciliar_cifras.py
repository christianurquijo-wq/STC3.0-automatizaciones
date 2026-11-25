"""
Conciliación de cifras de avance STC 3.0 sobre la tabla de BigQuery que leen el Streamlit y el Looker
(sustained-edge-465417-m3.EFE_2026.STC_3_0_V2_2026).

Por qué (nov-2026): con el mismo origen, la cabecera del Streamlit decía Básico 1.956 / Especializado 1.144 / Total
3.100 y el Looker mostraba en las barras 2.058 / 1.139 / 3.197 (pero sus tarjetas de % usaban 1.956 y 1.144). Este
script calcula cada definición posible sobre la MISMA tabla y lista a las personas que explican cada diferencia.

Uso (desde STC, con el entorno activo):
    python Seguimiento_general\\conciliar_cifras.py
Deja «conciliacion_cifras_STC_<fecha>.xlsx» en la carpeta Seguimiento_general (no se sube al repo: datos personales).
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
TABLA = "sustained-edge-465417-m3.EFE_2026.STC_3_0_V2_2026"
FINALIZADOS = {"FINALIZADO", "FINALIZADO PENDIENTE X REMISIÓN"}


def leer_bq() -> pd.DataFrame:
    from google.cloud import bigquery
    from google.oauth2.service_account import Credentials
    llave = next((p for p in (AQUI / "credenciales.json", RAIZ / "credenciales.json") if p.exists()), None)
    if llave is None:
        sys.exit("No encuentro credenciales.json en la raíz de STC.")
    try:
        from dotenv import load_dotenv
        load_dotenv(RAIZ / ".env")
    except ImportError:
        pass
    cred = Credentials.from_service_account_file(str(llave), scopes=["https://www.googleapis.com/auth/bigquery"])
    cliente = bigquery.Client(credentials=cred, project=os.getenv("PROJECT_ID") or cred.project_id)
    filas = cliente.query(f"SELECT * FROM `{TABLA}`").result()
    return pd.DataFrame([dict(f) for f in filas])


def txt(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series([""] * len(df), index=df.index)
    return df[col].astype("string").fillna("").str.strip()


def definiciones(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    paq = txt(df, "paquete").str.upper()
    rep = txt(df, "reporte").str.upper()
    est = txt(df, "estado_de_la_formacion").str.upper()
    bt = txt(df, "momento_del_proceso_back_up")
    fin = rep.isin(FINALIZADOS)
    basico, esp = paq.eq("BÁSICO"), paq.eq("ESPECIALIZADO")
    form_ok = est.isin(["FINALIZADO", "CERTIFICADO"])
    baja = bt.str.startswith("6")
    hito = txt(df, "hito")

    def flag(col: str) -> pd.Series:
        return pd.to_numeric(txt(df, col), errors="coerce").fillna(0).gt(0)

    filas = [
        # (indicador, definición, conteo, dónde se usa)
        ("Básico", "Paquete BÁSICO y Reporte FINALIZADO / PENDIENTE X REMISIÓN", fin & basico,
         "Streamlit (cabecera) y Looker (% Básicos)"),
        ("Básico", "Paquete BÁSICO (cualquier Reporte)", basico, "candidato barras Looker"),
        ("Básico", "Paquete BÁSICO con Reporte no vacío", basico & rep.ne(""), "candidato barras Looker"),
        ("Básico", "Paquete BÁSICO, Reporte finalizado, sin bajas", fin & basico & ~baja, "referencia"),
        ("Básico", "Paquete BÁSICO con Hito «Pago N» o «En ruta»", basico & hito.ne(""), "referencia"),
        ("Básico", "Columna «Orientado» = 1 y paquete BÁSICO", basico & flag("orientado"), "referencia"),
        ("Especializado", "Estado formación FINALIZADO o CERTIFICADO (cualquier paquete)", form_ok,
         "Streamlit (cabecera) y Looker (% Especializados)"),
        ("Especializado", "Ídem, solo paquete ESPECIALIZADO", form_ok & esp, "candidato barras Looker"),
        ("Especializado", "Estado formación CERTIFICADO", est.eq("CERTIFICADO"), "candidato barras Looker"),
        ("Especializado", "Momento (Back UP) = 5.Certificado", bt.eq("5.Certificado"), "candidato barras Looker"),
        ("Especializado", "Columna «Certificado (1)» = 1", flag("certificado_1"), "candidato barras Looker"),
    ]
    cc = txt(df, "cc_prospecto")
    resumen = pd.DataFrame([{"Indicador": i, "Definición": d, "Filas": int(m.sum()),
                             "Personas únicas (CC)": int(cc[m].nunique()), "Uso": u} for i, d, m, u in filas])

    cols = [c for c in ("cc_prospecto", "nombre_completo", "paquete", "reporte", "estado_de_la_formacion",
                        "momento_del_proceso_back_up", "hito", "eventobase", "orientador") if c in df]
    listas = {
        "Básico sin reporte finalizado": df.loc[basico & ~fin, cols],
        "Formación OK sin paquete Esp": df.loc[form_ok & ~esp, cols],
        "Formación FINALIZADO (no cert)": df.loc[est.eq("FINALIZADO"), cols],
        "Reporte finalizado sin paquete": df.loc[fin & paq.eq(""), cols],
    }
    cruces = {
        "Paquete x Reporte": pd.crosstab(paq.replace("", "(vacío)"), rep.replace("", "(vacío)"), margins=True,
                                         margins_name="Total").reset_index(),
        "Paquete x Estado formación": pd.crosstab(paq.replace("", "(vacío)"), est.replace("", "(vacío)"),
                                                  margins=True, margins_name="Total").reset_index(),
    }
    return resumen, {**listas, **cruces}


def main() -> None:
    df = leer_bq()
    print(f"Tabla {TABLA}: {len(df)} filas")
    resumen, hojas = definiciones(df)
    pd.set_option("display.width", 200)
    print(resumen.to_string(index=False))
    salida = AQUI / f"conciliacion_cifras_STC_{date.today():%Y%m%d}.xlsx"
    with pd.ExcelWriter(salida) as xw:
        resumen.to_excel(xw, sheet_name="Resumen", index=False)
        for nombre, t in hojas.items():
            t.to_excel(xw, sheet_name=nombre[:31], index=False)
    print(f"\nDetalle en {salida}")


if __name__ == "__main__":
    main()
