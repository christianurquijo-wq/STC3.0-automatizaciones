"""
Puerto a Python de Main.gs — orquesta todo: recorre las carpetas de mes bajo
config.ROOT_FOLDER_ID, filtra por Seguimiento General ("En ruta"), clasifica
archivos, cruza con el FCS, llama al agente IA por documento, y escribe
Resumen/Hallazgos/Consumo en el Sheet de reporte.

Misma lógica que la versión de Apps Script actual (incluye el filtro "En
ruta" cruzando todos los meses, y la columna de estado Verificado / Con
novedad / No encontrado en el resumen).
"""
import time
from datetime import datetime
from typing import List, Optional

import agente
import diccionario
import fichas_documentos
from catalogo import OBSERVACIONES_INTERNAS, obtener_observacion
from agente_config import AREA_SUGERIDA_POR_CATEGORIA, CAMPOS_PLATAFORMA
from consumo import registrar_consumo_de_corrida, verificar_techo_tokens_mensual
from fcs import cargar_fcs
from google_clients import descargar_bytes_archivo, listar_archivos, listar_subcarpetas, obtener_o_crear_hoja
from seguimiento import cargar_cedulas_en_ruta
from utilidades import normalizar_documento, normalizar_nombre

ENCABEZADO_HALLAZGOS = [
    'Fecha de revisión', 'Mes', 'Participante (No. documento)', 'Campo',
    'Código', 'Categoría', 'Responsable sugerido',
    'Observación (texto oficial SDDE / interno Datágil)', 'Detalle',
]
ENCABEZADO_CONSUMO = ['Fecha', 'Tipo', 'Cantidad', 'Detalle']


def fila_hallazgo(ahora: datetime, nombre_mes: str, numero_documento: str, campo: str, obs: dict, detalle: Optional[str]) -> list:
    """Arma una fila de hallazgo con código + categoría + responsable ya resueltos."""
    responsable = AREA_SUGERIDA_POR_CATEGORIA.get(obs['categoria'], '')
    return [ahora.isoformat(), nombre_mes, numero_documento, campo, obs['codigo'], obs['categoria'], responsable, obs['texto'], detalle or '']


def ejecutar_revision(config, drive_service, gc, client_gemini=None, sleep_fn=time.sleep, ahora: Optional[datetime] = None) -> dict:
    avisos: List[tuple] = []
    ahora = ahora or datetime.now()

    report_ss = gc.open_by_key(config.REPORT_SPREADSHEET_ID)
    sh_resumen = obtener_o_crear_hoja(report_ss, config.NOMBRE_HOJA_RESUMEN)
    sh_hallazgos = obtener_o_crear_hoja(report_ss, config.NOMBRE_HOJA_HALLAZGOS)
    sh_consumo = obtener_o_crear_hoja(report_ss, config.NOMBRE_HOJA_CONSUMO)

    # Diccionario de siglas -> campo: vive en la pestaña "Diccionario" del mismo Sheet
    # (se crea y siembra sola la primera vez) en vez de fijo en agente_config.py, para
    # poder ampliarlo sin tocar código — ver diccionario.py.
    dicc, ignorar = diccionario.cargar_diccionario(report_ss, avisos)

    sh_resumen.clear()
    sh_hallazgos.clear()
    if not sh_consumo.get_all_values():
        sh_consumo.append_row(ENCABEZADO_CONSUMO)

    encabezado_resumen = (
        ['Mes', 'Participante (No. documento)', 'Población detectada (Drive)', 'Población (FCS)', 'Paquete (FCS)']
        + CAMPOS_PLATAFORMA + ['Archivos sin clasificar']
    )
    sh_resumen.append_row(encabezado_resumen)
    sh_hallazgos.append_row(ENCABEZADO_HALLAZGOS)

    fcs_por_documento = cargar_fcs(gc, config, avisos)

    # --- Lista de participantes a revisar (Seguimiento General, Hito = En ruta) ---
    filtrar_por_en_ruta = config.USAR_LISTA_EN_RUTA
    cedulas_en_ruta = cargar_cedulas_en_ruta(gc, config, avisos) if filtrar_por_en_ruta else set()
    if filtrar_por_en_ruta and not cedulas_en_ruta:
        avisos.append(('Aviso', 'La lista de "En ruta" en Seguimiento General quedó vacía (o no se pudo leer) — '
                                 'no se va a procesar ningún participante esta corrida.'))

    # --- Compuerta de seguridad: techo propio de tokens del mes ---
    techo_mensual = verificar_techo_tokens_mensual(sh_consumo, config, ahora) if config.USAR_AGENTE_IA else {'superado': False, 'gastados': 0}
    if techo_mensual['superado']:
        avisos.append(('Techo de tokens alcanzado',
                        f"Se alcanzó el techo propio de tokens del mes ({techo_mensual['gastados']} / {config.ALERTA_TOKENS_MES}). "
                        'El agente IA queda desactivado para esta corrida.'))

    restantes_inicial = config.MAX_LLAMADAS_AGENTE_POR_CORRIDA if (config.USAR_AGENTE_IA and not techo_mensual['superado']) else 0
    presupuesto_agente = {
        'restantes': restantes_inicial,
        'restantes_inicial': restantes_inicial,
        'saltados': 0,
        'tokens_usados': 0,
        'detenido_por_tokens': False,
    }

    if config.USAR_AGENTE_IA and restantes_inicial > 0 and client_gemini is None:
        client_gemini = agente.obtener_cliente_gemini()

    carpetas_mes = listar_subcarpetas(drive_service, config.ROOT_FOLDER_ID)

    filas_resumen: List[list] = []
    filas_hallazgos: List[list] = []
    cedulas_encontradas = set()
    contador = 0
    escaneo_completo = True

    for carpeta_mes in carpetas_mes:
        if contador >= config.MAX_PARTICIPANTES_POR_CORRIDA:
            escaneo_completo = False
            break
        nombre_mes = carpeta_mes['name']
        carpetas_participante = listar_subcarpetas(drive_service, carpeta_mes['id'])
        detenido_en_mes = False

        for carpeta_participante in carpetas_participante:
            if contador >= config.MAX_PARTICIPANTES_POR_CORRIDA:
                escaneo_completo = False
                detenido_en_mes = True
                break

            numero_documento = carpeta_participante['name'].strip()
            numero_normalizado = normalizar_documento(numero_documento)
            if filtrar_por_en_ruta and numero_normalizado not in cedulas_en_ruta:
                continue

            cedulas_encontradas.add(numero_normalizado)
            contador += 1

            resultado = revisar_carpeta_participante(
                drive_service, carpeta_participante['id'], numero_documento, nombre_mes, ahora,
                fcs_por_documento, presupuesto_agente, config, client_gemini, sleep_fn,
                dicc, ignorar,
            )
            filas_resumen.append(resultado['fila_resumen'])
            filas_hallazgos.extend(resultado['filas_hallazgos'])

        if detenido_en_mes:
            break

    # Cédulas "En ruta" que no aparecieron en NINGUNA carpeta de mes — solo se
    # puede afirmar con seguridad si se recorrió TODO.
    if filtrar_por_en_ruta and escaneo_completo:
        for cedula in cedulas_en_ruta:
            if cedula in cedulas_encontradas:
                continue
            filas_hallazgos.append(fila_hallazgo(ahora, '(sin carpeta)', cedula, '(carpeta)', OBSERVACIONES_INTERNAS['CARPETA_NO_ENCONTRADA'], ''))
            fila_vacia = ['(sin carpeta)', cedula, 'NO DETERMINADA', '', ''] + ['No encontrado'] * len(CAMPOS_PLATAFORMA) + ['']
            filas_resumen.append(fila_vacia)
    elif filtrar_por_en_ruta and not escaneo_completo:
        avisos.append(('Aviso', 'La corrida se detuvo por el límite de participantes antes de recorrer todas las '
                                 'carpetas de mes — no se pudo verificar quién de "En ruta" no tiene carpeta. Sube '
                                 'config.MAX_PARTICIPANTES_POR_CORRIDA o corre de nuevo para completar esa verificación.'))

    if filas_resumen:
        sh_resumen.append_rows(filas_resumen, value_input_option='RAW')
    if filas_hallazgos:
        sh_hallazgos.append_rows(filas_hallazgos, value_input_option='RAW')

    registrar_consumo_de_corrida(sh_consumo, ahora, presupuesto_agente)

    mensaje = f'{contador} carpeta(s) de participante revisadas. {len(filas_hallazgos)} hallazgo(s) encontrados.'
    if filtrar_por_en_ruta:
        mensaje += f' ({len(cedulas_en_ruta)} cédula(s) "En ruta" en Seguimiento General'
        if escaneo_completo:
            mensaje += f', {len(cedulas_en_ruta) - len(cedulas_encontradas)} sin carpeta'
        mensaje += '.)'
    if techo_mensual['superado']:
        mensaje += ' El agente IA estuvo desactivado toda la corrida (techo mensual de tokens alcanzado).'
    elif config.USAR_AGENTE_IA and presupuesto_agente['saltados'] > 0:
        motivo = 'techo de tokens de la corrida' if presupuesto_agente['detenido_por_tokens'] else 'límite de llamadas de la corrida'
        mensaje += f" {presupuesto_agente['saltados']} documento(s) quedaron sin revisión del agente IA ({motivo})."

    return {
        'mensaje': mensaje,
        'avisos': avisos,
        'contador': contador,
        'filas_resumen': filas_resumen,
        'filas_hallazgos': filas_hallazgos,
        'cedulas_en_ruta': cedulas_en_ruta,
        'cedulas_encontradas': cedulas_encontradas,
        'escaneo_completo': escaneo_completo,
        'presupuesto_agente': presupuesto_agente,
    }


def revisar_carpeta_participante(
    drive_service, carpeta_id: str, numero_documento: str, nombre_mes: str, ahora: datetime,
    fcs_por_documento: dict, presupuesto_agente: dict, config, client_gemini, sleep_fn,
    diccionario_actual: dict, ignorar_actual: set,
) -> dict:
    """Revisa una carpeta de participante y devuelve la fila de resumen + los hallazgos detectados."""
    presentes_por_campo = {c: [] for c in CAMPOS_PLATAFORMA}
    sin_clasificar: List[str] = []
    archivos_clasificados: List[dict] = []  # {id, nombre_original, campo}
    poblacion = 'NO DETERMINADA'
    filas_hallazgos: List[list] = []

    for archivo in listar_archivos(drive_service, carpeta_id):
        nombre_original = archivo['name']
        norm = normalizar_nombre(nombre_original, numero_documento)

        if norm in ignorar_actual:
            continue

        entrada = diccionario_actual.get(norm)
        if not entrada:
            sin_clasificar.append(nombre_original)
            filas_hallazgos.append(fila_hallazgo(ahora, nombre_mes, numero_documento, '(sin clasificar)', OBSERVACIONES_INTERNAS['SIN_CLASIFICAR'], nombre_original))
            continue

        presentes_por_campo[entrada['campo']].append(nombre_original)
        if entrada.get('poblacion'):
            poblacion = entrada['poblacion']
        archivos_clasificados.append({'id': archivo['id'], 'nombre_original': nombre_original, 'campo': entrada['campo']})

    # --- Cruce con el FCS ---
    fcs_data = fcs_por_documento.get(normalizar_documento(numero_documento))
    poblacion_fcs = ''
    paquete_fcs = ''

    if config.USAR_FCS and fcs_por_documento:
        if not fcs_data:
            filas_hallazgos.append(fila_hallazgo(ahora, nombre_mes, numero_documento, '(FCS)', OBSERVACIONES_INTERNAS['NO_EN_FCS'], ''))
        else:
            jco = fcs_data.get('jco')
            poblacion_fcs = 'JCO' if jco == 'SI' else ('GENERAL' if jco == 'NO' else '')
            paquete_fcs = fcs_data.get('paquete', '')

            if poblacion_fcs and poblacion != 'NO DETERMINADA' and poblacion_fcs != poblacion:
                filas_hallazgos.append(fila_hallazgo(
                    ahora, nombre_mes, numero_documento, 'evidenciaDesempleoConsultaAdres',
                    OBSERVACIONES_INTERNAS['POBLACION_INCONSISTENTE'], f'Drive: {poblacion} / FCS: {poblacion_fcs}',
                ))
            if poblacion == 'NO DETERMINADA' and poblacion_fcs:
                poblacion = poblacion_fcs

    if poblacion == 'NO DETERMINADA':
        filas_hallazgos.append(fila_hallazgo(ahora, nombre_mes, numero_documento, 'evidenciaDesempleoConsultaAdres', OBSERVACIONES_INTERNAS['SIN_POBLACION'], ''))

    # --- Revisión de contenido con el agente IA ---
    if config.USAR_AGENTE_IA:
        for item in archivos_clasificados:
            archivo_bytes = descargar_bytes_archivo(drive_service, item['id'])
            resultado = agente.evaluar_documento_con_agente(
                client_gemini, archivo_bytes, item['nombre_original'], item['campo'], numero_documento,
                fcs_data, presupuesto_agente, config, sleep_fn, poblacion=poblacion,
            )

            if resultado['saltado']:
                continue

            if resultado['error']:
                filas_hallazgos.append(fila_hallazgo(
                    ahora, nombre_mes, numero_documento, item['campo'], OBSERVACIONES_INTERNAS['AGENTE_FALLO'],
                    f"{resultado['error']} — {item['nombre_original']}",
                ))
                continue

            ya_marco_ilegible = any(h.get('codigo') == 'COM-ILEGIBLE' for h in resultado['hallazgos_crudos'])
            if resultado['documento_legible'] is False and not ya_marco_ilegible:
                obs_ilegible = obtener_observacion(item['campo'], 'COM-ILEGIBLE', 'Documento ilegible, recortado o con enmendaduras.', 'Calidad de imagen')
                filas_hallazgos.append(fila_hallazgo(ahora, nombre_mes, numero_documento, item['campo'], obs_ilegible, item['nombre_original']))

            for h in resultado['hallazgos_crudos']:
                obs = obtener_observacion(item['campo'], h.get('codigo'), h.get('detalle'), None)
                filas_hallazgos.append(fila_hallazgo(ahora, nombre_mes, numero_documento, item['campo'], obs, h.get('detalle')))

    # --- Campos faltantes ---
    for campo in CAMPOS_PLATAFORMA:
        if presentes_por_campo[campo]:
            continue  # está presente, no hay nada que reportar

        if campo == 'cursoHabilidadTecnica':
            # Caso especial: aplica según el paquete del FCS (no según población), y si el
            # paquete todavía no se pudo determinar no se puede decidir si aplica o no —
            # se reporta aparte en vez de asumir "falta".
            if paquete_fcs in ('BÁSICO', 'BASICO'):
                continue  # no aplica, confirmado por FCS
            if paquete_fcs == 'ESPECIALIZADO':
                filas_hallazgos.append(fila_hallazgo(
                    ahora, nombre_mes, numero_documento, campo, OBSERVACIONES_INTERNAS['FALTA'],
                    'El FCS confirma paquete especializado, que sí requiere este documento.',
                ))
                continue
            filas_hallazgos.append(fila_hallazgo(ahora, nombre_mes, numero_documento, campo, OBSERVACIONES_INTERNAS['PAQUETE_DESCONOCIDO'], ''))
            continue

        # Todos los demás campos: la regla de "quién debe tenerlo" vive en fichas_documentos.py
        # (confirmada por Christian el 2026-08-26) — un solo lugar para ajustarla sin tocar esta
        # función. Antes 'mitigacionBarreras' se exigía a TODOS los participantes (bug: solo
        # aplica a especializados no-JCO) y 'evidenciaDesempleoConsultaAdres'/'certificadoDeResidencia'
        # no tenían ninguna excepción para JCO (bug: ninguno de los dos aplica a JCO).
        regla_aplica = fichas_documentos.FICHAS.get(campo, {}).get('aplica', fichas_documentos.APLICA_TODOS)
        if not fichas_documentos.aplica_para_poblacion_y_paquete(regla_aplica, poblacion, paquete_fcs):
            continue

        detalle = 'Al menos la Encuesta de cierre debería estar en este campo.' if campo == 'mitigacionBarreras' else ''
        filas_hallazgos.append(fila_hallazgo(ahora, nombre_mes, numero_documento, campo, OBSERVACIONES_INTERNAS['FALTA'], detalle))

    # --- Estado por campo para el resumen: No encontrado / Con novedad / Verificado ---
    campos_con_hallazgo = {f[3] for f in filas_hallazgos}

    fila_resumen = [nombre_mes, numero_documento, poblacion, poblacion_fcs, paquete_fcs]
    for campo in CAMPOS_PLATAFORMA:
        if not presentes_por_campo[campo]:
            fila_resumen.append('No encontrado')
        elif campo in campos_con_hallazgo:
            fila_resumen.append('Con novedad')
        else:
            fila_resumen.append('Verificado')
    fila_resumen.append(', '.join(sin_clasificar))

    return {'fila_resumen': fila_resumen, 'filas_hallazgos': filas_hallazgos}
