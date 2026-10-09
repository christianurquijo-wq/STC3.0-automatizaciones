"""Puerto a Python de Utilidades.gs."""
import re
import unicodedata


def normalizar_nombre(nombre_archivo: str, numero_documento: str) -> str:
    """
    Normaliza el nombre de un archivo para compararlo contra el DICCIONARIO:
    quita la extensión, quita el número de documento del inicio, y elimina
    espacios/guiones/guiones bajos/símbolos, dejando solo letras y números en
    mayúsculas.
    """
    n = re.sub(r'\.pdf$', '', nombre_archivo, flags=re.IGNORECASE)
    n = re.sub(r'^\s*' + re.escape(numero_documento) + r'\s*', '', n)
    n = quitar_acentos(n)  # antes faltaba: sin esto, "Autopostulación" perdía la Ó en vez de normalizarse a "AUTOPOSTULACION"
    n = n.upper()
    n = re.sub(r'[^A-Z0-9]', '', n)
    return n


def normalizar_documento(valor) -> str:
    """Deja solo dígitos: soporta que el número de documento venga como texto o número."""
    if valor is None:
        return ''
    return re.sub(r'[^0-9]', '', str(valor))


def quitar_acentos(texto: str) -> str:
    """Quita tildes/diacríticos (NFD + strip de marcas combinadas) para comparar texto sin acentos."""
    if texto is None:
        return ''
    nfd = unicodedata.normalize('NFD', str(texto))
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
