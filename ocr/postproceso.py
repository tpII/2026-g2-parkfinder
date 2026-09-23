"""Post-proceso del texto OCR: corrige confusiones dígito↔letra (0↔O, 1↔I,
8↔B, 5↔S, 2↔Z) según la posición que ocupan en el formato de la patente."""

from validacion import PATRONES_POSICION, limpiar, validar

DIGITO_A_LETRA = {"0": "O", "1": "I", "8": "B", "5": "S", "2": "Z"}
LETRA_A_DIGITO = {v: k for k, v in DIGITO_A_LETRA.items()}


def corregir_por_posicion(texto, patron):
    """patron: cadena de 'L' (letra) y 'D' (dígito), del mismo largo que texto."""
    corregido = list(texto)
    for i, esperado in enumerate(patron):
        caracter = corregido[i]
        if esperado == "L" and caracter in DIGITO_A_LETRA:
            corregido[i] = DIGITO_A_LETRA[caracter]
        elif esperado == "D" and caracter in LETRA_A_DIGITO:
            corregido[i] = LETRA_A_DIGITO[caracter]
    return "".join(corregido)


def corregir(texto_ocr):
    """Corrige por posición si el largo coincide con algún formato; si no, lo
    devuelve solo limpio."""
    texto = limpiar(texto_ocr)
    for formato, patron in PATRONES_POSICION.items():
        if len(texto) == len(patron):
            return corregir_por_posicion(texto, patron)
    return texto


def leer_patente(texto_ocr):
    """Devuelve (patente, formato) si la lectura corregida es válida, o (None, None)."""
    corregido = corregir(texto_ocr)
    formato = validar(corregido)
    if formato is None:
        return None, None
    return corregido, formato
