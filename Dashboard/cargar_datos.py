# cargar_datos.py
import pandas as pd
from config import FUENTES
from sheets_api import obtener_valores_crudos

def _hacer_nombres_unicos(columnas: list) -> list:
    vistos = {}
    resultado = []
    for c in columnas:
        if c not in vistos:
            vistos[c] = 0
            resultado.append(c)
        else:
            vistos[c] += 1
            resultado.append(f"{c}.{vistos[c]}")
    return resultado

def _detectar_fila_encabezado(filas: list, ancla: str, max_filas_revisar: int = 20) -> int:
    ancla_norm = ancla.strip().upper()
    limite = min(max_filas_revisar, len(filas))
    for i in range(limite):
        fila_norm = [str(c).strip().upper() for c in filas[i]]
        if ancla_norm in fila_norm:
            return i
    raise ValueError(f"No encontré el ancla '{ancla}' en las primeras {limite} filas.")

def cargar_fuente(nombre: str):
    f = FUENTES[nombre]
    filas = obtener_valores_crudos(f["id"], f["gid"])
    fila_header = _detectar_fila_encabezado(filas, f["ancla"])

    max_cols = max(len(r) for r in filas)

    encabezado_crudo = filas[fila_header] + [""] * (max_cols - len(filas[fila_header]))
    columnas_limpias = [str(c).split("\n")[0].strip() for c in encabezado_crudo]
    columnas = _hacer_nombres_unicos(columnas_limpias)

    datos = filas[fila_header + 1:]
    datos_normalizados = [fila + [""] * (max_cols - len(fila)) for fila in datos]

    df = pd.DataFrame(datos_normalizados, columns=columnas)
    df = df.replace("", pd.NA)
    df = df.dropna(how="all")

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    return df, fila_header