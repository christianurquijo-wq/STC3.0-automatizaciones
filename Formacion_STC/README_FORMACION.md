# Formación STC 3.0 · actualización automática

`actualizar_formacion.py` reemplaza el flujo de n8n **LOGSSTC3.0-FORMACIÓN** y las fórmulas de la pestaña
**CONSOLIDADO** del archivo «Seguimiento Formación STC 3.0» (`SHEET_ID_FORMACION`).

## Qué hace en cada ejecución

1. Consulta BigQuery: las 6 consultas del flujo (`sql/*.sql`) + Reporte CRM y Reporte SIS.
2. El SEGUIMIENTO GENERAL es la única fuente de quién va en formación (y de nombre, curso, fecha de orientación y
   mes de entrega). Se agregan al final de CONSOLIDADO sus especializados vigentes que falten (paquete ESPECIALIZADO,
   orientación FINALIZADO / FINALIZADO PENDIENTE X REMISIÓN, sin «6.Baja», cédula bien escrita). La ejecución normal
   **nunca borra ni mueve filas**; quien ya no cumple solo se informa en «Control script».
   Limpieza única: `--limpiar` retira a quien no cumple y lo guarda completo en «Retirados de CONSOLIDADO».
   **Nunca se retira a quien terminó formación (FINALIZADO o CERTIFICADO)**: se queda y la columna BJ
   «OBSERVACIÓN SEGUIMIENTO GENERAL» dice por qué no es especializado vigente (baja, otro paquete…).
3. Calcula las columnas de CONSOLIDADO (`motor_formacion.py`) y las escribe como **valores**. Las columnas del
   equipo (S, T, AI, AK, AL, AM, BC, BD, BG, BI) viajan con su cédula.
4. Reescribe las pestañas fuente (LOGS, ASISTENCIAS, LOG_ACCESS, USER_STATISTICS, NOTAS PUBLICADAS, SESIONES,
   REPORTE CRM, REPORTE SIS) **una vez al día** (`FORMACION_PESTANAS=auto`). En SESIONES conserva la columna K
   «ENVIADO» por CLASS_SESSION_ID y deja J1 (HABILITADO) como fórmula.
5. Escribe un resumen en la pestaña **Control script**.

Corre encadenado a `Seguimiento_general/reconstruir_seguimiento_real.py` (L-V 6 a. m.–6 p. m.) y desde el Panel.

## Correcciones respecto a las fórmulas

| Col. | Antes | Ahora |
|---|---|---|
| P/Q/R | `AND()` dentro de ARRAYFORMULA evaluaba toda la columna: buscaba sesión también a certificados y «SIN INSCRIBIR» | Solo INSCRITO / EN CURSO |
| AQ | Contaba como 1 log la fila vacía de usuarios sin ingresos (cuentas duplicadas del SIS) | Solo filas con LOG_ID |
| L/M/N | Primera fila del SIS (podía ser la del básico → «SIN INSCRIBIR») | Se prefiere la fila del especializado |
| AC | Primera fila con asistencia en el orden en que llegaba de BigQuery (sin orden) | Primera fecha de asistencia |
| BF | No cruzaba cédulas guardadas como texto en la Matriz Documental | Cruza texto y número |
| E | «NO TIENE» en el segundo apellido se pegaba al nombre | Se omite |

Listas que estaban dentro de fórmulas (BE insubsanables, Y fechas fijas, AU ya no: ver abajo): constantes al inicio de
`motor_formacion.py`.

## Uso manual

```
python Formacion_STC/actualizar_formacion.py --prueba        # solo escribe «CONSOLIDADO (script)»
python Formacion_STC/actualizar_formacion.py --limpiar --prueba   # vista previa de la limpieza única
python Formacion_STC/actualizar_formacion.py --limpiar             # limpieza única (una sola vez)
python Formacion_STC/actualizar_formacion.py                 # real
python Formacion_STC/actualizar_formacion.py --pestanas si   # fuerza reescribir pestañas fuente
python -m pytest Formacion_STC                               # pruebas
```

**AU «PAQUETE DE PAGO»** (nov-2026): es el «Hito» del Seguimiento General (col. BH): «Pago 1», «Pago 2.1»… si la SDDE
ya aprobó a la persona en una entrega, «En ruta» si va en el proceso, vacío si es baja o no está en el SG. Antes se
estimaba por el mes de entrega (julio → PAQUETE 1, agosto → 2…). Como el cron corre formación antes que el SG, AU
toma el Hito de la reconstrucción anterior (un pago nuevo aparece en formación en la corrida siguiente).
