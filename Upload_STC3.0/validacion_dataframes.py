import sys
from google.cloud.exceptions import NotFound

def validar_y_comparar(nombre_base_sheets, df, client_bq, table_ref):
    try:
        tabla_bq = client_bq.get_table(table_ref)
        columnas_bq = [campo.name for campo in tabla_bq.schema]
    except NotFound:
        print(f"la tabla: {table_ref} no existe en el confunto de datos de BQ")
        print(f"saltando la validación y resubiendo la Tabla automáticamente")
        return True
    
    columnas_df = list(df.columns)
    errores = False

    if len(columnas_bq) != len(columnas_df):
        print(f" Diferencia en la CANTIDAD de columnas.")
        print(f" BigQuery tiene: {len(columnas_bq)} columnas")
        print(f" Tu CSV/DataFrame tiene: {len(columnas_df)} columnas")
        errores = True

    if sorted(columnas_bq) != sorted(columnas_df):
        print("Los nombres de las columnas no coinciden con exactitud")
        
        faltan = set(columnas_bq) - set(columnas_df)
        sobran = set(columnas_df) - set(columnas_bq)

        if faltan:
            print(f"La base de datos de Google Sheets ({nombre_base_sheets}) no tiene las siguientes columnas: {list(faltan)}")
        if sobran:
            print(f"La base de datos de Google Sheets ({nombre_base_sheets}) tiene las siguientes columnas que no son de BQ: {list(sobran)}")
        
        errores = True

    if errores:
        print("Ejecución detenida")
        sys.exit(1)

    print(f"Coincidencia total. Haciendo el upload de la tabla: {table_ref}")
    return True