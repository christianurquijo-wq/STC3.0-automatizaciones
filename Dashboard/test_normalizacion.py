# test_normalizacion.py
from cargar_datos import cargar_fuente
from normalizador import normalizar_columna_cedula
from column_mapping import MAPEO_CEDULA

def test_todas():
    for nombre, columna in MAPEO_CEDULA.items():
        df, _ = cargar_fuente(nombre)
        df = normalizar_columna_cedula(df, columna)

        total = len(df)
        validas = df["cedula_norm"].notna().sum()
        invalidas = total - validas
        duplicadas = df["cedula_norm"].dropna().duplicated().sum()

        print(f"\n{nombre.upper()}")
        print(f"  Total filas: {total}")
        print(f"  Cédulas válidas: {validas}")
        print(f"  Cédulas inválidas/vacías: {invalidas}")
        print(f"  Cédulas duplicadas (misma persona 2+ veces): {duplicadas}")

        if invalidas > 0:
            print("  Ejemplos de valores que NO se pudieron normalizar:")
            ejemplos = df[df["cedula_norm"].isna()][columna].dropna().unique()[:5]
            for e in ejemplos:
                print(f"    - {repr(e)}")

if __name__ == "__main__":
    test_todas()