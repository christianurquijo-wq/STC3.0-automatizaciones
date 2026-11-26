"""Panel / programación: reconstruye «SEGUIMIENTO GENERAL» en la hoja real y, al terminar:
  1. carga la tabla de BigQuery STC_3_0_V2_2026 (Upload_STC3.0/upload_STC3.0_BQ.py), que es la que lee el Streamlit;
  2. actualiza «Seguimiento Formación STC 3.0» (Formacion_STC/actualizar_formacion.py): especializados nuevos,
     asistencia, logs y avance de plataforma en CONSOLIDADO (reemplaza el flujo de n8n LOGSSTC3.0-FORMACIÓN).
Si alguno de los dos falla, el proceso termina con error para que el Panel/ops_logger lo alerte (el otro igual corre).
Variables para omitir pasos: SEGUIMIENTO_SIN_BQ=1, SEGUIMIENTO_SIN_FORMACION=1."""
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from reconstruir_seguimiento import main  # noqa: E402


def omitido(var: str) -> bool:
    return os.getenv(var, "").strip().lower() in ("1", "true", "si")


if __name__ == "__main__":
    main(destino="real")
    errores = []

    carga = AQUI.parent / "Upload_STC3.0" / "upload_STC3.0_BQ.py"
    if omitido("SEGUIMIENTO_SIN_BQ"):
        print("[seguimiento] Carga a BigQuery omitida (SEGUIMIENTO_SIN_BQ)", flush=True)
    else:
        print(f"[seguimiento] Cargando BigQuery con {carga.relative_to(AQUI.parent)} …", flush=True)
        r = subprocess.run([sys.executable, str(carga)], cwd=str(carga.parent))
        if r.returncode != 0:
            errores.append(f"la carga a BigQuery falló (código {r.returncode}); la hoja sí quedó actualizada")
        else:
            print("[seguimiento] BigQuery actualizado: el Streamlit verá los datos nuevos (caché de 10 min)", flush=True)

    formacion = AQUI.parent / "Formacion_STC" / "actualizar_formacion.py"
    if omitido("SEGUIMIENTO_SIN_FORMACION"):
        print("[seguimiento] Formación omitida (SEGUIMIENTO_SIN_FORMACION)", flush=True)
    else:
        print(f"[seguimiento] Actualizando formación con {formacion.relative_to(AQUI.parent)} …", flush=True)
        r = subprocess.run([sys.executable, str(formacion)], cwd=str(formacion.parent))
        if r.returncode != 0:
            errores.append(f"la actualización de formación falló (código {r.returncode})")

    if errores:
        sys.exit("[seguimiento] " + " · ".join(errores))
