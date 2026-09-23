"""Validación por regex de los formatos de patente: viejo (ABC123) y
Mercosur (AB123CD). PATRONES_POSICION también lo usa postproceso.py."""

import re

PATRONES_POSICION = {
    "viejo": "LLLDDD",
    "mercosur": "LLDDDLL",
}

REGEX_FORMATO = {
    "viejo": re.compile(r"^[A-Z]{3}[0-9]{3}$"),
    "mercosur": re.compile(r"^[A-Z]{2}[0-9]{3}[A-Z]{2}$"),
}


def limpiar(texto):
    """Mayúsculas y sin espacios."""
    return texto.upper().replace(" ", "")


def validar(texto):
    """Devuelve 'viejo' | 'mercosur', o None si no matchea ninguno (lectura fallida)."""
    texto = limpiar(texto)
    for formato, regex in REGEX_FORMATO.items():
        if regex.match(texto):
            return formato
    return None
