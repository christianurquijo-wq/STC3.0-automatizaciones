"""
Puerto a Python de CatalogoObservaciones.gs — mismo contenido exacto, mismos
códigos y textos oficiales de la SDDE. No se toca el contenido del catálogo,
solo la sintaxis (dict de Python en vez de objeto de JS).
"""
from typing import Dict, List, Optional

CATALOGO_OBSERVACIONES: Dict[str, List[dict]] = {
    'documentoDeIdentidad': [
        {'codigo': 'DI-01', 'texto': 'Documento vencido.', 'categoria': 'Otro'},
        {'codigo': 'DI-02', 'texto': 'La fecha de nacimiento o expedición no coincidentes con el FCS y plataforma STC 3.0.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
    ],
    'declaracionJuramentada': [
        {'codigo': 'DJ-01', 'texto': 'Faltantes en el diligenciamiento que no permite identificar la información contenida en el documento.', 'categoria': 'Otro'},
        {'codigo': 'DJ-02', 'texto': 'Dirección distinta a la diligenciada en el FCS o plataforma STC 3.0.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'DJ-03', 'texto': 'No corresponde al formato autorizado por la SDDE.', 'categoria': 'Otro'},
        {'codigo': 'DJ-04', 'texto': 'Fecha posterior a la intervención o por fuera de la vigencia del programa.', 'categoria': 'Vigencia'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
    ],
    'evidenciaDesempleoConsultaAdres': [
        {'codigo': 'ED-01', 'texto': 'Departamento o municipio de ADRES no sea de Bogotá.', 'categoria': 'Otro'},
        {'codigo': 'ED-02', 'texto': 'Documento reporta al atendido en estado ACTIVO – CONTRIBUTIVO - COTIZANTE.', 'categoria': 'Otro'},
        {'codigo': 'ED-03', 'texto': 'Documento no corresponde al formato emitido por la plataforma ADRES del Ministerio de Salud.', 'categoria': 'Otro'},
        {'codigo': 'ED-04', 'texto': 'NO APLICA si es JCO (corresponde ACJ en su lugar).', 'categoria': 'Población / paquete'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
    ],
    'certificadoDeResidencia': [
        {'codigo': 'CR-01', 'texto': 'El recibo de servicio público NO coincide con la dirección registrada en la DJ y el sistema de información.', 'categoria': 'Otro'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
        {'codigo': 'COM-VIGENCIA_CONTRATO', 'texto': 'La fecha del documento NO está en la vigencia del contrato.', 'categoria': 'Vigencia'},
        {'codigo': 'COM-NO_AUTORIZADO_MO', 'texto': 'No corresponde a alguna de las evidencias autorizadas por MO.', 'categoria': 'Formato no autorizado'},
    ],
    'consultaRnecOMigracion': [
        {'codigo': 'RM-01', 'texto': 'Certificado de RNEC con estado diferente a "vigente".', 'categoria': 'Otro'},
        {'codigo': 'RM-02', 'texto': 'Documento que no corresponde al formato emitido por la RNEC o Migración Colombia.', 'categoria': 'Otro'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
        {'codigo': 'COM-VIGENCIA_CONTRATO', 'texto': 'La fecha del documento NO está en la vigencia del contrato.', 'categoria': 'Vigencia'},
    ],
    'valoracionRiesgoDesempleo': [
        {'codigo': 'VR-01', 'texto': 'El nivel de riesgo NO coincide con el FCS o puntaje.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'VR-02', 'texto': 'Datos básicos del atendido no coinciden con lo registrado en el FCS.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
    ],
    'cursoHabilidadTecnica': [
        {'codigo': 'CT-01', 'texto': 'Nombre del curso técnico diferente al relacionado en el FCS.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'CT-02', 'texto': 'Fechas de inicio o culminación de evidencia no coinciden con lo reportado en el FCS.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'CT-03', 'texto': 'Documento no cuenta con el soporte de conexión establecido en el M.O del operador y sus evidencias.', 'categoria': 'Contenido del curso'},
        {'codigo': 'CT-04', 'texto': 'Certificado de habilidades técnicas no cuenta con la evidencia de conexión en asincrónico y sincrónico.', 'categoria': 'Contenido del curso'},
        {'codigo': 'CT-05', 'texto': 'Evidencia no cumple con el mínimo de horas establecidas (40 horas: 16 sincrónicas + 32 asincrónicas mínimo).', 'categoria': 'Contenido del curso'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
        {'codigo': 'COM-NO_APLICA', 'texto': 'NO APLICA', 'categoria': 'No aplica'},
    ],
    'mitigacionBarreras': [
        {'codigo': 'MB-01', 'texto': 'Documento NO se encuentra firmado por el participante y el responsable.', 'categoria': 'Formato no autorizado'},
        {'codigo': 'MB-02', 'texto': 'El valor y la mitigación NO coinciden con lo registrado en el FCS.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
        {'codigo': 'COM-NO_APLICA', 'texto': 'NO APLICA', 'categoria': 'No aplica'},
        {'codigo': 'COM-NO_AUTORIZADO_MO', 'texto': 'No corresponde a alguna de las evidencias autorizadas por MO.', 'categoria': 'Formato no autorizado'},
    ],
    'autopostulacionJovenesConOportunidades': [
        {'codigo': 'AP-01', 'texto': 'Nombres, apellidos y/o número de identificación del atendido o del empleador NO coinciden con el FCS.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
        {'codigo': 'COM-NO_APLICA', 'texto': 'NO APLICA', 'categoria': 'No aplica'},
    ],
    'seguimientoRemision': [
        {'codigo': 'SR-01', 'texto': 'No se identifica la remisión en la plataforma del SPE.', 'categoria': 'Otro'},
        {'codigo': 'SR-02', 'texto': 'No coincide el código de remisión con el registrado en el FCS.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'SR-03', 'texto': 'No coincide nombre de la empresa o título de la vacante con el registrado en el FCS.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'SR-04', 'texto': 'NO se identifican datos de la empresa (razón social, NIT, nombre) a la cual fue remitido.', 'categoria': 'Otro'},
        {'codigo': 'SR-05', 'texto': 'NO se identifican datos de la vacante (código) que coincidan con el FCS.', 'categoria': 'Coherencia con FCS'},
        {'codigo': 'SR-06', 'texto': 'NO se identifican los dos seguimientos establecidos en el M.O.', 'categoria': 'Otro'},
        {'codigo': 'SR-07', 'texto': 'Fechas de seguimiento son del mismo día.', 'categoria': 'Vigencia'},
        {'codigo': 'SR-08', 'texto': 'No se evidencia la encuesta de cierre de atención.', 'categoria': 'Otro'},
        {'codigo': 'COM-ILEGIBLE', 'texto': 'Documento ilegible, recortado o con enmendaduras.', 'categoria': 'Calidad de imagen'},
        {'codigo': 'COM-NOMBRE_NO_COINCIDE', 'texto': 'Nombres, apellidos y/o número de identificación no coincidente con el atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-SECCION_EQUIVOCADA', 'texto': 'Documento cargado no corresponde a la sección o al atendido.', 'categoria': 'Documento equivocado'},
        {'codigo': 'COM-CASCADA', 'texto': 'No se verifica porque no fue remitido a Gestor en plataforma STC 3.0 o las fechas de elegibilidad no son iguales o anteriores a la prestación de los servicios.', 'categoria': 'Elegibilidad (causa raíz)'},
    ],
}

# Observaciones internas de Kuepa/Datágil que NO vienen del desplegable oficial de la SDDE.
OBSERVACIONES_INTERNAS: Dict[str, dict] = {
    'FALTA': {'codigo': 'COM-FALTA', 'texto': 'Falta el documento en la carpeta de Drive.', 'categoria': 'Documento faltante'},
    'NO_EN_FCS': {'codigo': 'COM-NOENFCS', 'texto': 'Número de documento no encontrado en el FCS.', 'categoria': 'Coherencia con FCS'},
    'POBLACION_INCONSISTENTE': {'codigo': 'COM-POBLACION', 'texto': 'La población según los archivos de Drive no coincide con la del FCS.', 'categoria': 'Población / paquete'},
    'SIN_CLASIFICAR': {'codigo': 'COM-SINCLASIF', 'texto': 'Archivo no reconocido en el diccionario de siglas.', 'categoria': 'Sin clasificar'},
    'SIN_FECHA': {'codigo': 'COM-SINFECHA', 'texto': 'El agente no reconoció ninguna fecha válida en el documento — revisar manualmente.', 'categoria': 'Vigencia'},
    'FECHA_AMBIGUA': {'codigo': 'COM-FECHAAMBIGUA', 'texto': 'El agente encontró varias fechas posibles en el documento y no pudo determinar cuál aplica — revisar manualmente.', 'categoria': 'Vigencia'},
    'AGENTE_FALLO': {'codigo': 'COM-AGENTEFALLO', 'texto': 'No se pudo evaluar el archivo con el agente IA (error técnico: cuota, conexión, o el modelo no devolvió una respuesta válida) — revisar manualmente.', 'categoria': 'Calidad de imagen'},
    'SIN_POBLACION': {'codigo': 'COM-SINPOBLACION', 'texto': 'No se pudo determinar la población (JCO o general): no se encontró ADRES ni ACJ, y el FCS tampoco la resolvió.', 'categoria': 'Población / paquete'},
    'PAQUETE_DESCONOCIDO': {'codigo': 'COM-PAQUETEDESCONOCIDO', 'texto': 'Falta el documento y no se pudo confirmar el paquete asignado en el FCS.', 'categoria': 'Población / paquete'},
    'CARPETA_NO_ENCONTRADA': {'codigo': 'COM-SINCARPETA', 'texto': 'No se encontró ninguna carpeta en Drive (en ningún mes) para este número de documento, aunque aparece con Hito "En ruta" en Seguimiento General.', 'categoria': 'Documento faltante'},
}


def obtener_observacion(campo: str, codigo: str, texto_respaldo: Optional[str] = None, categoria_respaldo: Optional[str] = None) -> dict:
    """Busca una observación por campo + código; si no está, cae a OBSERVACIONES_INTERNAS por código; si tampoco, arma una entrada mínima."""
    lista = CATALOGO_OBSERVACIONES.get(campo, [])
    encontrada = next((o for o in lista if o['codigo'] == codigo), None)
    if encontrada:
        return encontrada

    interna = next((o for o in OBSERVACIONES_INTERNAS.values() if o['codigo'] == codigo), None)
    if interna:
        return interna

    return {'codigo': codigo, 'texto': texto_respaldo or codigo, 'categoria': categoria_respaldo or 'Otro'}


def codigos_validos_para_campo(campo: str) -> List[dict]:
    """Códigos que el agente IA puede usar para un campo dado (para el enum del response_schema)."""
    lista = [{'codigo': o['codigo'], 'texto': o['texto']} for o in CATALOGO_OBSERVACIONES.get(campo, [])]
    if campo == 'certificadoDeResidencia':
        lista.append({'codigo': OBSERVACIONES_INTERNAS['SIN_FECHA']['codigo'], 'texto': OBSERVACIONES_INTERNAS['SIN_FECHA']['texto']})
        lista.append({'codigo': OBSERVACIONES_INTERNAS['FECHA_AMBIGUA']['codigo'], 'texto': OBSERVACIONES_INTERNAS['FECHA_AMBIGUA']['texto']})
    return lista
