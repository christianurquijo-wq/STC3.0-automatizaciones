# STC 3.0 — Revisión documental (versión Python, sin Apps Script)

Puerto 1:1 de la lógica que hoy corre en Apps Script (`AuditorCalidad`), para
poder usar el SDK oficial de Python del agente IA (`google-genai`) en vez de
llamar a Gemini por REST a mano. Misma lógica de negocio exacta: filtro por
Seguimiento General ("En ruta"), cruce con el FCS, catálogo de observaciones
SDDE, presupuesto de tokens/llamadas por corrida y techo mensual.

Qué cambia frente a la versión de Apps Script:

- Ya no hay menú en la Sheet — el disparador es un botón en tu app de
  Streamlit (`app_streamlit_ejemplo.py`, cópialo/adáptalo a tu app existente).
- Ya no hay autorización automática de Google (la que Apps Script te daba
  gratis por correr dentro de su contenedor) — hace falta una **cuenta de
  servicio** de Google Cloud, compartida explícitamente con las carpetas y
  Sheets que el script necesita leer/escribir.
- El reporte (Resumen/Hallazgos/Consumo) sigue viviendo en un Google Sheet —
  solo que ahora hay que decirle explícitamente CUÁL, con
  `REPORT_SPREADSHEET_ID` (antes era implícito: "la Sheet donde vive el script").

## 1. Instalar dependencias

```bash
cd python_agente
pip install -r requirements.txt
```

## 2. Crear la cuenta de servicio (una sola vez)

1. Entra a [Google Cloud Console](https://console.cloud.google.com/) con la
   cuenta que administre esto (puede ser un proyecto nuevo, gratis).
2. Crea un proyecto (o usa uno existente) → **APIs y servicios → Biblioteca**
   → habilita **Google Drive API** y **Google Sheets API**.
3. **APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio**.
   Dale un nombre (ej. `stc3-revision-bot`), no hace falta darle ningún rol
   de proyecto.
4. Entra a la cuenta de servicio recién creada → pestaña **Claves** → **Agregar
   clave → Crear clave nueva → JSON**. Se descarga un archivo `.json` — esa es
   tu credencial. **No la subas a GitHub.**
5. Copia el email de la cuenta de servicio (algo como
   `stc3-revision-bot@tu-proyecto.iam.gserviceaccount.com`).

## 3. Compartir el acceso (una sola vez)

Comparte estos 4 recursos con el email de la cuenta de servicio, igual que
compartirías con una persona más:

| Recurso | Dónde | Permiso |
|---|---|---|
| Carpeta raíz de Drive (`ROOT_FOLDER_ID`) | Google Drive | Lector alcanza (el script no escribe en Drive) |
| Sheet del FCS (`FCS_SPREADSHEET_ID`) | Google Sheets | Lector |
| Sheet de Seguimiento General (`SEGUIMIENTO_SPREADSHEET_ID`) | Google Sheets | Lector |
| Sheet del reporte (`REPORT_SPREADSHEET_ID`) — donde quieres ver Resumen/Hallazgos/Consumo | Google Sheets | **Editor** (el script sí escribe aquí) |

Si el reporte va en una Sheet nueva, créala primero, cópiale el ID de la URL,
y ponlo en `REPORT_SPREADSHEET_ID`.

## 4. Variables de entorno

Copia `.env.example` a `.env` y complétalo:

```bash
cp .env.example .env
```

- `GEMINI_API_KEY`: gratis, sin tarjeta, en https://aistudio.google.com/apikey
- `GOOGLE_SERVICE_ACCOUNT_FILE`: ruta al `.json` del paso 2 (o usa
  `GOOGLE_SERVICE_ACCOUNT_JSON` con el contenido pegado, si prefieres no tener
  el archivo en disco — más cómodo si vas a desplegar en Streamlit Cloud y
  usar Secrets en vez de un archivo).
- `REPORT_SPREADSHEET_ID`: el ID del Sheet del paso 3.

**Nunca subas `.env` ni el `.json` de la cuenta de servicio a GitHub** —
agrégalos a `.gitignore` si no lo están ya.

## 5. Correr los tests (sin credenciales reales — todo mockeado)

```bash
cd python_agente
python3 -m pytest -v
```

Deben pasar 13 tests: normalización de nombres/documentos, resolución del
catálogo de observaciones, búsqueda de encabezados en FCS/Seguimiento
General, y el flujo completo de `ejecutar_revision()` (filtro "En ruta"
cruzando meses, columna de estado Verificado/Con novedad/No encontrado,
participante sin carpeta reportado como hallazgo).

## 6. Correr la app

```bash
streamlit run app_streamlit_ejemplo.py
```

Esto es un ejemplo mínimo — para integrarlo a tu app de Streamlit ya
existente en el Codespace, copia el `import revision` + el botón + el manejo
del resultado a donde tenga sentido en tu UI actual.

## 7. Ajustar `agente_config.py`

Los valores por defecto en `agente_config.py` son los mismos que ya tenías en
`Config.gs` (misma carpeta raíz, mismo modelo, mismos techos de tokens).
Ajusta ahí si necesitas cambiar algo — es el único archivo que deberías tocar
para un ajuste normal de uso, igual que antes.

**Nota:** el archivo se llama `agente_config.py` (no `config.py` a secas) a
propósito — si integras esta carpeta dentro de otra app de Streamlit que ya
tenga su propio `config.py`, evita que los dos se pisen entre sí por el orden
de `sys.path`.

## Diccionario de siglas y sugerencias con IA

El mapeo de nombre de archivo -> campo oficial (`CC` -> documento de
identidad, `DJ` -> declaración juramentada, etc.) ya no vive fijo en
`agente_config.py` — vive en una pestaña **"Diccionario"** del mismo Sheet
de reporte, para poder ampliarlo sin tocar código ni hacer un deploy. Se
crea y se siembra sola (con lo que antes vivía en `agente_config.py`) la
primera vez que corre una revisión, o la primera vez que se usa el barrido
de Drive de abajo.

Desde la pestaña "🔍 Auditoría de calidad" en Streamlit, expander **"🧾
Diccionario de nombres de archivo (con ayuda de IA)"**:

1. **Escanear Drive** — barrido completo de la carpeta raíz (no solo "En
   ruta"), agrupa por nombre de archivo (sin cédula ni extensión) y muestra
   cuáles todavía no calzan con el Diccionario.
2. **Pedir sugerencia a Gemini** — una sola llamada de texto (no abre
   ningún PDF, así que es barata) que propone a qué campo corresponde cada
   nombre nuevo, con nivel de confianza y justificación.
3. **Revisar y aprobar** — tabla editable donde confirmas/corriges cada
   sugerencia antes de guardarla. Nada se escribe en el Diccionario sin
   aprobación humana.

Recomendado correr este barrido periódicamente (ej. mensual) para mantener
el Diccionario al día conforme el equipo de campo varía cómo nombra los
archivos.

## Notas de costo / infraestructura (Datágil)

- Google Drive API / Sheets API: gratis, dentro de cuotas muy generosas para
  este volumen.
- Gemini API (nivel gratuito): mismas condiciones y mismo riesgo de privacidad
  ya aceptado con Christian el 2026-08-24 para el piloto — los datos del nivel
  gratuito pueden ser usados por Google para mejorar sus productos. Revisar
  antes de escalar a producción con todos los participantes.
- Cuenta de servicio de Google Cloud: gratis, no tiene costo de uso para esto.
- Disparador vía Streamlit en tu Codespace: gratis mientras corra ahí. Si más
  adelante quieres que quede disponible sin tener el Codespace abierto, la
  opción de bajo costo es Streamlit Community Cloud (gratis, con la misma
  limitación de "se duerme por inactividad" que Render free tier) o Render
  (desde ~$7/mes si necesitas que responda al instante siempre) — decisión
  aparte, cuando haga falta.
