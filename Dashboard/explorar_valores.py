# explorar_valores.py
from cargar_datos import cargar_fuente

COLUMNAS_A_REVISAR = {
    "general": ["Momento del proceso", "Reporte", "Sin gestión", "En verificación",
                "Verificado", "Orientado", "Formado", "Paquete",
                "Tipo de paquete reportado", "Resultado del VRD", "JCO", "¿Es JCO?",
                "Estado CRM", "Estado de la formación"],
    "verificacion": ["Estado CRM", "Confirmación del verificador", "Validación",
                     "Verificación", "Población"],
    "formacion": ["Estado Académico", "Paquete", "Principal"],
    "orientacion_consolidado": ["RESULTADO DEL VRD", "TIPO DE PAQUETE DE SERVICIO",
                                "EN RUTA DEL PROGRAMA JÓVENES CON OPORTUNIDADES",
                                "REPORTE", "PAQUETE JCO"],
    "remisiones": ["REPORTE", "TIPO DE PAQUETE DE SERVICIO", "JCO"],
}

def explorar():
    for nombre, columnas in COLUMNAS_A_REVISAR.items():
        df, _ = cargar_fuente(nombre)
        print(f"\n{'='*60}\n{nombre.upper()}\n{'='*60}")
        for col in columnas:
            if col not in df.columns:
                print(f"  [{col}] -> NO EXISTE en esta fuente")
                continue
            conteo = df[col].value_counts(dropna=False)
            print(f"\n  [{col}]")
            for valor, n in conteo.items():
                print(f"    {repr(valor)}: {n}")

if __name__ == "__main__":
    explorar()