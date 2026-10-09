"""
Ficha de verificación por documento — el detalle específico de qué es y qué
se debe cruzar en cada uno de los 10 campos de la Plataforma, confirmado
directamente por Christian (Datágil) el 2026-08-26. Reemplaza el prompt
genérico único que usaba el agente antes (mismo texto para los 10
documentos, sin detalle de qué revisar) por una instrucción específica por
documento — y, en 'evidenciaDesempleoConsultaAdres', una variante distinta
según la población (GENERAL usa ADRES, JCO usa ACJ).

Si el negocio cambia un requisito (ej. intensidad horaria del curso,
umbrales del VRD, qué formatos de certificado de residencia se aceptan),
este es el único archivo que hay que tocar — no hace falta tocar agente.py
ni revision.py.

PENDIENTE DE CONFIRMAR CON CHRISTIAN: la regla dice que
'evidenciaDesempleoConsultaAdres' no aplica a JCO — pero el Diccionario
tiene el alias 'ACJ' mapeado a este mismo campo con población JCO (como si
ACJ fuera el equivalente JCO de la consulta ADRES). Mientras se confirma,
se dejó como NO obligatorio para JCO (no se marca "falta" si no aparece),
pero si un archivo ACJ sí aparece clasificado, igual se evalúa con la ficha
JCO de abajo.
"""
from typing import Optional

# Reglas de aplicabilidad -> se usan tanto para armar el prompt como para
# decidir en revision.py si "falta el documento" debe reportarse como hallazgo.
APLICA_TODOS = 'TODOS'
APLICA_TODOS_EXCEPTO_JCO = 'TODOS_EXCEPTO_JCO'
APLICA_SOLO_JCO = 'SOLO_JCO'
APLICA_TODOS_EXCEPTO_BASICO = 'TODOS_EXCEPTO_BASICO'
APLICA_SOLO_ESPECIALIZADO_NO_JCO = 'SOLO_ESPECIALIZADO_NO_JCO'

_PAQUETES_BASICO = ('BASICO', 'BÁSICO')
_PAQUETES_ESPECIALIZADO = ('ESPECIALIZADO',)


FICHAS = {
    'documentoDeIdentidad': {
        'aplica': APLICA_TODOS,
        'descripcion': (
            'Documento de identidad del participante — puede ser Cédula de Ciudadanía (CC), DNI, '
            'Permiso por Protección Temporal (PPT), o Cédula de Extranjería (CE). Es un escaneo o '
            'foto del documento.'
        ),
        'que_revisar': (
            'Confirma que coincidan con el FCS: nombre completo, número de documento, fecha de '
            'nacimiento, lugar de nacimiento y lugar de expedición. Cualquiera de los 4 tipos de '
            'documento (CC/DNI/PPT/CE) es válido — no marques "documento equivocado" solo por el tipo.'
        ),
    },
    'declaracionJuramentada': {
        'aplica': APLICA_TODOS,
        'descripcion': (
            'Declaración Juramentada (DJ) — documento estandarizado donde el participante acepta su '
            'participación en la ruta de empleabilidad. Puede estar diligenciado digital o físicamente.'
        ),
        'que_revisar': (
            'Confirma: (1) la fecha del documento está dentro de la vigencia del convenio, (2) el '
            'nombre completo y número de documento coinciden con el FCS, (3) el documento está firmado.'
        ),
    },
    'evidenciaDesempleoConsultaAdres': {
        'aplica': APLICA_TODOS_EXCEPTO_JCO,
        'variantes': {
            'GENERAL': {
                'descripcion': 'Consulta ADRES — pantallazo de la consulta del número de documento en la plataforma ADRES.',
                'que_revisar': (
                    'Confirma que el nombre y apellidos, y el número de documento, coincidan con el '
                    'FCS. Verifica que el tipo de afiliación NO sea "COTIZANTE" y el estado NO sea '
                    '"ACTIVO" — si el participante aparece como cotizante activo, repórtalo.'
                ),
            },
            'JCO': {
                'descripcion': 'Evidencia equivalente para población JCO (Jóvenes con Oportunidades) — variante ACJ en vez de la consulta ADRES.',
                'que_revisar': (
                    'Este participante es JCO: confirma nombre, apellidos y número de documento '
                    'contra el FCS. NO apliques los criterios de "cotizante activo" de la consulta '
                    'ADRES general — ese criterio es solo para población GENERAL.'
                ),
            },
        },
    },
    'certificadoDeResidencia': {
        'aplica': APLICA_TODOS_EXCEPTO_JCO,
        'descripcion': (
            'Puede ser un recibo de servicio público o un certificado/comprobante de puesto de '
            'votación (escaneado o pantallazo) — cualquiera de los dos formatos es válido.'
        ),
        'que_revisar': 'Lo único que debes verificar es que la dirección y/o ciudad que aparece en el documento corresponda a BOGOTÁ.',
    },
    'consultaRnecOMigracion': {
        'aplica': APLICA_TODOS,
        'descripcion': 'Consulta RNEC — documento digital emitido por la Registraduría que confirma la validez del documento de identidad.',
        'que_revisar': 'Confirma que el nombre, apellidos, tipo de documento y número de documento coincidan con el FCS.',
    },
    'valoracionRiesgoDesempleo': {
        'aplica': APLICA_TODOS,
        'descripcion': 'Valoración de Riesgo de Desempleo (VRD) — documento emitido por la SDDE que resume la atención del participante.',
        'que_revisar': (
            'Confirma que esté diligenciado completo y que tenga un resultado de valoración (ALTO, '
            'MEDIO o BAJO). Reglas de coherencia: si el participante es JCO, el resultado NO importa '
            '(el JCO siempre es especializado). Si NO es JCO: paquete BÁSICO debe tener riesgo BAJO o '
            'MODERADO; paquete ESPECIALIZADO debe tener riesgo ALTO o MODERADO — si no calza, repórtalo.'
        ),
    },
    'cursoHabilidadTecnica': {
        'aplica': APLICA_TODOS_EXCEPTO_BASICO,
        'descripcion': (
            'Compilado entre un certificado de formación y un pantallazo (CONSOLIDADO / CONSOLIDADO '
            'FORMACION). Ya existe una revisión detallada del compilado en otro paso — aquí solo '
            'valida los datos del certificado mismo.'
        ),
        'que_revisar': (
            'Confirma: nombre completo, tipo y número de documento correctos, fechas razonables (no '
            'futuras ni absurdas), y que el curso de formación coincida con el FCS. Intensidad '
            'horaria mínima esperada: 20 horas si es especializado (no JCO), 40 horas si es '
            'especializado JCO — repórtalo si la intensidad reportada es menor a la esperada.'
        ),
    },
    'mitigacionBarreras': {
        'aplica': APLICA_SOLO_ESPECIALIZADO_NO_JCO,
        'descripcion': 'Documento firmado por el participante donde se confirma la entrega de un bono de mitigación de barreras.',
        'que_revisar': (
            'Confirma que los datos del participante coincidan con el FCS y que el documento esté '
            'firmado, con fecha dentro de la vigencia del convenio.'
        ),
    },
    'autopostulacionJovenesConOportunidades': {
        'aplica': APLICA_SOLO_JCO,
        'descripcion': 'Pantallazo o HTML de la plataforma de autopostulación.',
        'que_revisar': (
            'Confirma que el nombre (puede venir incompleto — eso no es un problema) y el número de '
            'documento coincidan con el FCS, y que aparezca un estado que diga "Autopostulado".'
        ),
    },
    'seguimientoRemision': {
        'aplica': APLICA_TODOS,
        'descripcion': 'HTML que muestra un correo donde se remite información de candidatos a una empresa para una vacante.',
        'que_revisar': 'Confirma que el participante aparezca incluido en la lista de postulados de ese correo.',
    },
}


def obtener_ficha(campo: str, poblacion: Optional[str] = None) -> dict:
    """Devuelve {aplica, descripcion, que_revisar} para un campo — resolviendo la variante GENERAL/JCO cuando aplica."""
    base = FICHAS.get(campo)
    if base is None:
        return {'aplica': APLICA_TODOS, 'descripcion': '', 'que_revisar': ''}
    if 'variantes' in base:
        variante = base['variantes'].get('JCO' if poblacion == 'JCO' else 'GENERAL', {})
        return {'aplica': base['aplica'], 'descripcion': variante.get('descripcion', ''), 'que_revisar': variante.get('que_revisar', '')}
    return base


def aplica_para_poblacion_y_paquete(regla_aplica: str, poblacion: Optional[str], paquete: Optional[str]) -> bool:
    """True si el documento es obligatorio para esta combinación de población/paquete — usado para decidir si 'falta' es un hallazgo real."""
    paquete = (paquete or '').upper()
    if regla_aplica == APLICA_TODOS:
        return True
    if regla_aplica == APLICA_TODOS_EXCEPTO_JCO:
        return poblacion != 'JCO'
    if regla_aplica == APLICA_SOLO_JCO:
        return poblacion == 'JCO'
    if regla_aplica == APLICA_TODOS_EXCEPTO_BASICO:
        return paquete not in _PAQUETES_BASICO
    if regla_aplica == APLICA_SOLO_ESPECIALIZADO_NO_JCO:
        return poblacion != 'JCO' and paquete in _PAQUETES_ESPECIALIZADO
    return True


def resolver_poblacion(entradas_clasificadas: list, datos_fcs: Optional[dict]) -> str:
    """
    entradas_clasificadas: lista de entradas del Diccionario ya matcheadas para los archivos de un
    participante (cada una puede traer 'poblacion' si el nombre del archivo ya lo revela, ej. ACJ).
    Si ninguna lo revela, se cae al dato del FCS (columna 'jco'). Devuelve 'GENERAL', 'JCO', o
    'NO DETERMINADA' — misma lógica que revision.py, factorizada acá para que debug_agente.py use
    exactamente el mismo criterio y no diverjan con el tiempo.
    """
    for entrada in entradas_clasificadas:
        if entrada.get('poblacion'):
            return entrada['poblacion']
    if datos_fcs:
        jco = datos_fcs.get('jco')
        if jco == 'SI':
            return 'JCO'
        if jco == 'NO':
            return 'GENERAL'
    return 'NO DETERMINADA'
