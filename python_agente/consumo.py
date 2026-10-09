"""
Puerto a Python de Consumo.gs — registro de consumo del agente IA (llamadas +
tokens) y techo mensual de seguridad.

Nota sobre fechas: a diferencia de Apps Script (donde una celda de fecha es
un objeto Date real), gspread lee/escribe texto — así que guardamos la fecha
como ISO 8601 ("2026-08-24T21:19:00") y la parseamos al sumar el consumo del
mes. Si alguna fila tiene una fecha que no se puede leer, se ignora esa fila
(mismo criterio que el `if (!(fecha instanceof Date)) continue;` original).
"""
from datetime import datetime
from typing import Optional


def registrar_consumo_de_corrida(ws, ahora: datetime, presupuesto_agente: dict) -> None:
    """Escribe filas resumen de consumo del agente IA para la corrida que acaba de terminar."""
    llamadas_usadas = presupuesto_agente['restantes_inicial'] - presupuesto_agente['restantes']
    ws.append_row([ahora.isoformat(), 'AGENTE_LLAMADAS', llamadas_usadas,
                    'Documentos evaluados por el agente IA (Gemini) en esta corrida.'])
    if presupuesto_agente['tokens_usados'] > 0:
        ws.append_row([ahora.isoformat(), 'AGENTE_TOKENS', presupuesto_agente['tokens_usados'],
                        'Tokens totales (prompt + respuesta) consumidos por el agente IA en esta corrida.'])
    if presupuesto_agente['saltados'] > 0:
        ws.append_row([ahora.isoformat(), 'AGENTE_SALTADOS', presupuesto_agente['saltados'],
                        'Documentos clasificados que NO se evaluaron con el agente por alcanzar el límite '
                        'MAX_LLAMADAS_AGENTE_POR_CORRIDA de esta corrida.'])


def calcular_consumo_agente_mes_actual(ws, ahora: Optional[datetime] = None) -> int:
    return _sumar_consumo_mes_actual(ws, 'AGENTE_LLAMADAS', ahora)


def calcular_consumo_tokens_mes_actual(ws, ahora: Optional[datetime] = None) -> int:
    return _sumar_consumo_mes_actual(ws, 'AGENTE_TOKENS', ahora)


def _parsear_fecha(valor) -> Optional[datetime]:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor)[:19])
    except ValueError:
        return None


def _sumar_consumo_mes_actual(ws, tipo_buscado: str, ahora: Optional[datetime] = None) -> int:
    ahora = ahora or datetime.now()
    datos = ws.get_all_values()
    total = 0
    for fila in datos[1:]:  # fila 0 = encabezado
        if len(fila) < 3:
            continue
        fecha = _parsear_fecha(fila[0])
        tipo = fila[1]
        cantidad = fila[2]
        if fecha is None or tipo != tipo_buscado:
            continue
        if fecha.year == ahora.year and fecha.month == ahora.month:
            try:
                total += int(float(cantidad))
            except (ValueError, TypeError):
                pass
    return total


def verificar_techo_tokens_mensual(ws_consumo, config, ahora: Optional[datetime] = None) -> dict:
    """
    Compuerta de seguridad: revisa cuántos tokens se han gastado ya este mes
    contra config.ALERTA_TOKENS_MES. Se llama al arrancar ejecutar_revision(),
    ANTES de gastar ni una llamada más.
    """
    gastados = calcular_consumo_tokens_mes_actual(ws_consumo, ahora)
    return {'superado': gastados >= config.ALERTA_TOKENS_MES, 'gastados': gastados}


def estimar_consumo_mensual(ws_consumo, config, ahora: Optional[datetime] = None) -> str:
    """Igual que el menú 'Estimar consumo mensual' de Menu.gs, pero devuelve el texto en vez de un ui.alert."""
    total_documentos = config.ESTIMADOR_PARTICIPANTES_MES * config.ESTIMADOR_DOCS_POR_PARTICIPANTE
    dias_habiles_estimados = 22
    llamadas_por_dia_promedio = round(total_documentos / dias_habiles_estimados)

    llamadas_este_mes = calcular_consumo_agente_mes_actual(ws_consumo, ahora) if ws_consumo else 0
    tokens_este_mes = calcular_consumo_tokens_mes_actual(ws_consumo, ahora) if ws_consumo else 0

    mensaje = (
        'Supuestos (config.ESTIMADOR_*):\n'
        f'  Participantes/mes: {config.ESTIMADOR_PARTICIPANTES_MES}\n'
        f'  Documentos/participante: {config.ESTIMADOR_DOCS_POR_PARTICIPANTE}\n\n'
        'Proyección (el agente revisa TODOS los documentos clasificados):\n'
        f'  Documentos/llamadas totales al agente por mes: {total_documentos}\n'
        f'  Promedio de llamadas/día repartido en {dias_habiles_estimados} días: ~{llamadas_por_dia_promedio}\n'
        f'  Cupo gratuito de referencia (config.CUPO_REFERENCIA_RPD_GRATUITO): {config.CUPO_REFERENCIA_RPD_GRATUITO} solicitudes/día '
        f'(verificar la cifra vigente del modelo "{config.MODELO_GEMINI}" en https://ai.google.dev/gemini-api/docs/rate-limits)\n\n'
        f'Ya gastado este mes (medido, hoja "Consumo"): {llamadas_este_mes} llamadas, {tokens_este_mes} tokens.\n'
        f'Techo propio de tokens/mes (config.ALERTA_TOKENS_MES): {config.ALERTA_TOKENS_MES} — al alcanzarlo, la próxima '
        'corrida desactiva el agente automáticamente hasta que lo revises.\n\n'
    )

    if llamadas_por_dia_promedio > config.CUPO_REFERENCIA_RPD_GRATUITO:
        mensaje += (
            '⚠ El promedio diario estimado SUPERA el cupo gratuito de referencia. Con este volumen, '
            'convendría repartir las corridas en varias cuentas/proyectos, subir a un modelo de pago, o revisar si '
            'realmente hace falta que el agente evalúe TODOS los documentos.'
        )
    else:
        mensaje += (
            '✓ El promedio diario estimado queda dentro del cupo gratuito de referencia, repartiendo el volumen '
            'del mes en corridas diarias — pero recuerda que MAX_LLAMADAS_AGENTE_POR_CORRIDA y MAX_TOKENS_POR_CORRIDA '
            'limitan cuánto avanza CADA corrida individual.'
        )

    if tokens_este_mes >= config.ALERTA_TOKENS_MES:
        mensaje += (
            '\n\n⚠ Ya se alcanzó el techo propio de tokens del mes — la próxima corrida va a correr SOLO la '
            'clasificación de Fase 1, sin llamar al agente, hasta que subas config.ALERTA_TOKENS_MES o empiece un mes nuevo.'
        )

    return mensaje
