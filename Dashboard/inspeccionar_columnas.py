# inspeccionar_columnas.py
from cargar_datos import cargar_fuente

def inspeccionar_todo():
    for nombre in ["general", "formacion", "orientacion_consolidado", "remisiones", "verificacion"]:
        df, _ = cargar_fuente(nombre)
        print(f"\n{'='*60}\n{nombre.upper()} — {df.shape[1]} columnas\n{'='*60}")
        for i, col in enumerate(df.columns):
            print(f"  [{i}] {col}")

if __name__ == "__main__":
    inspeccionar_todo()