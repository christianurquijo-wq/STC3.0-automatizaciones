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

    faltan = set(columnas_bq) - set(columnas_df)
    sobran = set(columnas_df) - set(columnas_bq)

    # nov-2026: una columna NUEVA en la hoja (p. ej. «Último registro en CRM») no detiene la carga: la tabla se
    # reemplaza (WRITE_TRUNCATE + autodetect) y la columna se agrega. Lo que sí detiene es que FALTE una columna que
    # BigQuery tiene, porque el tablero de Streamlit la puede estar leyendo.
    if sobran:
        print(f"Columnas nuevas en {nombre_base_sheets} que se agregarán a BigQuery: {sorted(sobran)}")
    if faltan:
        print(f"La base de datos de Google Sheets ({nombre_base_sheets}) no tiene las siguientes columnas: {list(faltan)}")
        errores = True

    if errores:
        print("Ejecución detenida")
        sys.exit(1)

    print(f"Coincidencia total. Haciendo el upload de la tabla: {table_ref}")
    return True