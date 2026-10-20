# normalizador.py
import pandas as pd
import re

def normalizar_cedula(valor) -> str | None:
    """
    Deja la cédula solo con dígitos, sin puntos/espacios/decimales.
    Devuelve None si no es un número válido (ej. 'NO APLICA', vacío, texto).
    """
    if pd.isna(valor):
        return None
    texto = str(valor).strip()
    texto = re.sub(r"\.0$", "", texto)          
    solo_digitos = re.sub(r"\D", "", texto)     
    if len(solo_digitos) < 6:                   
        return None
    return solo_digitos

def normalizar_columna_cedula(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    df = df.copy()
    df["cedula_norm"] = df[columna].apply(normalizar_cedula)
    return df