# auditoria.py
import pandas as pd
from cargar_datos import cargar_fuente
from normalizador import normalizar_columna_cedula
from normalizador_texto import normalizar_texto
from column_mapping import (
    MAPEO_CEDULA, CAMPO_JCO_GENERAL, CAMPO_FORMADO_GENERAL,
    VALOR_FORMADO, CAMPO_PAQUETE_GENERAL,
)

def cargar_todo_normalizado():
    fuentes = {}
    for nombre, columna in MAPEO_CEDULA.items():
        df, _ = cargar_fuente(nombre)
        df = normalizar_columna_cedula(df, columna)
        fuentes[nombre] = df
    return fuentes

def construir_lookup(df: pd.DataFrame) -> dict:
    lookup = {}
    for _, fila in df.iterrows():
        ced = fila["cedula_norm"]
        if ced is None:
            continue
        lookup.setdefault(ced, []).append(fila)
    return lookup

def auditar():
    fuentes = cargar_todo_normalizado()
    general = fuentes["general"]
    lookup_verificacion = construir_lookup(fuentes["verificacion"])
    lookup_formacion = construir_lookup(fuentes["formacion"])
    lookup_orientacion = construir_lookup(fuentes["orientacion_consolidado"])
    lookup_remisiones = construir_lookup(fuentes["remisiones"])

    errores = []

    for _, persona in general.iterrows():
        ced = persona["cedula_norm"]
        if ced is None:
            errores.append({"cedula": None, "tipo_error": "CEDULA_INVALIDA_EN_GENERAL", "detalle": str(persona.get("CC Prospecto"))})
            continue

        jco_general = normalizar_texto(persona.get(CAMPO_JCO_GENERAL))
        formado_general = str(persona.get(CAMPO_FORMADO_GENERAL, "")).strip() == VALOR_FORMADO
        paquete_general = normalizar_texto(persona.get(CAMPO_PAQUETE_GENERAL))

        # --- Regla 1: JCO pendiente de clasificar (solo si ya avanzó en el proceso) ---
        momento = str(persona.get("Momento del proceso", "")).strip()
        ya_avanzo = momento not in ("0.Sin gestión", "1.En verificación", "")

        if jco_general is None and ya_avanzo:
            errores.append({
                "cedula": ced,
                "tipo_error": "JCO_PENDIENTE_CLASIFICAR_ATRASADO",
                "detalle": f"Sin JCO en General pero ya está en etapa: {momento}"
            })

        # --- Regla 2: JCO inconsistente con Verificación ---
        if ced in lookup_verificacion:
            poblaciones = {normalizar_texto(f.get("Población")) for f in lookup_verificacion[ced]}
            es_jco_verificacion = "JCO" in poblaciones
            if jco_general == "SI" and not es_jco_verificacion:
                errores.append({"cedula": ced, "tipo_error": "JCO_INCONSISTENTE", "detalle": f"General=SI, Verificación Población={poblaciones}"})
            if jco_general == "NO" and es_jco_verificacion:
                errores.append({"cedula": ced, "tipo_error": "JCO_INCONSISTENTE", "detalle": f"General=NO, Verificación Población={poblaciones}"})

        # --- Regla 3: Formado=FINALIZADO pero no existe en hoja Formación ---
        if formado_general and ced not in lookup_formacion:
            errores.append({"cedula": ced, "tipo_error": "FORMADO_SIN_REGISTRO_FORMACION", "detalle": "Marcado FINALIZADO en General pero no aparece en hoja Formación"})

        # --- Regla 4: Paquete inconsistente entre General y Remisiones ---
        if ced in lookup_remisiones:
            paquetes_remision = {normalizar_texto(f.get("TIPO DE PAQUETE DE SERVICIO")) for f in lookup_remisiones[ced]}
            paquetes_remision.discard(None)
            paquetes_remision.discard("NO APLICA")
            if paquete_general and paquetes_remision and paquete_general not in paquetes_remision:
                errores.append({"cedula": ced, "tipo_error": "PAQUETE_INCONSISTENTE_REMISION", "detalle": f"General={paquete_general}, Remisión={paquetes_remision}"})

    df_errores = pd.DataFrame(errores)
    return df_errores

if __name__ == "__main__":
    df_errores = auditar()
    print(f"\nTotal de inconsistencias encontradas: {len(df_errores)}\n")
    print(df_errores["tipo_error"].value_counts())
    inconsistentes = df_errores[df_errores["tipo_error"] == "JCO_INCONSISTENTE"]
    if len(inconsistentes) > 0:
        print("\n--- Casos JCO_INCONSISTENTE (revisar manualmente) ---")
        print(inconsistentes.to_string(index=False))
    df_errores.to_csv("reporte_errores_qa.csv", index=False, encoding="utf-8-sig")
    print("\n✅ Guardado en reporte_errores_qa.csv")