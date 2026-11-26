"""Registro original del CRM (nov-2026): fecha de alta más antigua y datos del registro «Matriculado»."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import motor_seguimiento as M  # noqa: E402


def test_registro_original_y_ultimo():
    crm = M.tabla([["Fecha de Alta", "Estudiante", "Documento", "Telefono", "Correo", "Programa", "ID CRM", "Asesor",
                    "Adnetwork", "Estado", "Campaña", "Baja"],
                   ["2026-11-26", "Ana", "1000111", "", "", "Básico", "3259", "", "JCO", "Prospecto", "V2", False],
                   ["2026-07-09", "Ana", "1000111", "", "", "Básico", "3259", "Laura", "JCO", "Matriculado", "V2", False],
                   ["2026-07-01", "Ana", "1000111", "", "", "Básico", "3001", "", "JCO", "Prospecto", "V1", False],
                   ["2026-08-01", "Luis", "1000222", "", "", "Básico", "4000", "", "Ad", "Prospecto", "V1", False]])
    i = M.indice_crm(crm)
    a, b = i.loc["1000111"], i.loc["1000222"]
    assert a["J"] == "Matriculado" and a["H"] == "Laura" and a["G"] == "3259"   # datos del registro matriculado
    assert a["A"] == "2026-07-01"                                               # fecha de alta = la más antigua
    assert a["_ultima"] == "2026-11-26"                                         # último registro (BU)
    assert b["A"] == "2026-08-01" and b["_ultima"] == ""                        # un solo registro
