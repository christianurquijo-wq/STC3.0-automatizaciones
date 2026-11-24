"""Panel / programación: reconstruye «SEGUIMIENTO GENERAL» en la hoja real y, al terminar, carga la tabla de
BigQuery STC_3_0_V2_2026 (Upload_STC3.0/upload_STC3.0_BQ.py), que es la que lee el Streamlit de STC.
Si la carga a BigQuery falla, el proceso termina con error para que el Panel/ops_logger lo alerte."""
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from reconstruir_seguimiento import main  # noqa: E402

if __name__ == "__main__":
    main(destino="real")
    carga = AQUI.parent / "Upload_STC3.0" / "upload_STC3.0_BQ.py"
    if os.getenv("SEGUIMIENTO_SIN_BQ", "").strip() in ("1", "true", "si"):
        print("[seguimiento] Carga a BigQuery omitida (SEGUIMIENTO_SIN_BQ)", flush=True)
        sys.exit(0)
    print(f"[seguimiento] Cargando BigQuery con {carga.relative_to(AQUI.parent)} …", flush=True)
    r = subprocess.run([sys.executable, str(carga)], cwd=str(carga.parent))
    if r.returncode != 0:
        sys.exit(f"[seguimiento] La carga a BigQuery falló (código {r.returncode}); la hoja sí quedó actualizada.")
    print("[seguimiento] BigQuery actualizado: el Streamlit verá los datos nuevos (caché de 10 min)", flush=True)
