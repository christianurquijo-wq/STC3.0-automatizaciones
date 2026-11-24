"""Panel / programación: reconstruye «SEGUIMIENTO GENERAL» y escribe en la hoja real (ver reconstruir_seguimiento.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconstruir_seguimiento import main  # noqa: E402

if __name__ == "__main__":
    main(destino="real")
