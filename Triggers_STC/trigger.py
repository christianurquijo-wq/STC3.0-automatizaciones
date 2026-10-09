import os
import glob
import subprocess
import sys


scripts_listados = sorted(glob.glob("*.py"))

archivos_excluidos = ['trigger.py',
                      'Append Colsubsidio2026.py',
                      'Formacion InAv Suba2026.py', 
                      'Formacion basico Suba2026.py',
                      'GenerarDashEco.py', 
                      'Limpieza_caracterizacion.py', 
                      'Limpieza_empleabilidad.py', 
                      'Limpieza_satisfaccion.py',
                      'DashEco.py',
                      'validacion_dataframes.py',
                      'Limpieza_seguimiento.py',
                      'Append_DATA_BQ.py',
                      'colsu2.py',
                      'STC_3_0_FCS.py'
                      #'Caracterizacion Colsubsidio2026.py',
                      #'Satisfaccion_Colsubsidio2026.py',
                      #'Upload Colsubsidio2026.py',
                      ]

script_prioridad = 'Mantenimiento_appends.py'

scripts_ejecutables = [script_prioridad]
for script in scripts_listados:
    if script not in archivos_excluidos and script != script_prioridad:
        scripts_ejecutables.append(script)

print(f"Ejecutando los siguientes códigos: {scripts_ejecutables}. Total: {len(scripts_ejecutables)}")

Barra = "="*60
scrpits_fallidos = {}
for script in scripts_ejecutables:
    try:
        if script == script_prioridad:
            print(f"{Barra}\nAPPEND\n{Barra}")

        print(f"\n\nIniciando ejecución: {script}")
        subprocess.run([sys.executable, script], check=True)
        print(f"{script} ejecutado correctamente")
    except subprocess.CalledProcessError as error:
        print(f"Hubo un problema con la ejecución del script '{script}' asociado a {error}")
        scrpits_fallidos[script] = str(error)
        continue

if len(scrpits_fallidos) == 0:
    print("Actualización total de los scripts")
else:
    print(f"Actualización finalizada pero hubo un problema con los siguientes scripts. Total fallas {len(scrpits_fallidos)}") 
    for fallido, detalle in scrpits_fallidos.items():
        print(f" - {fallido}: {detalle}") 