"""
Preprocesamiento previo al OCR: gris -> redimensionar -> mediana ->
binarización y morfología opcionales. Parámetros en PARAMETROS_DEFAULT.

Medido sobre el banco de 144 imágenes con Tesseract:
    crudo                          93/144
    gris + mediana (default)      100/144
    gris + mediana + Otsu          83/144
    gris + mediana + adaptativo   ~30/144
Binarizar empeora porque Tesseract ya binariza internamente (Leptonica); por
eso queda desactivado, disponible para otros motores.
"""

import cv2
import numpy as np

PARAMETROS_DEFAULT = {
    "alto_minimo": 150,            # px; solo se agranda si la imagen viene más chica
    "mediana_kernel": 3,           # impar; 0 desactiva el filtro de mediana
    "blur_kernel": 0,              # impar; blur gaussiano adicional (0 = desactivado)
    "binarizar": False,            # ver docstring del módulo
    "metodo_binarizacion": "otsu",  # "otsu" | "adaptativo" (solo si binarizar=True)
    "adaptativo_block_size": 31,   # impar; tamaño de la vecindad local
    "adaptativo_c": 10,            # constante restada de la media local
    "morfologia": False,           # solo tiene sentido si binarizar=True
    "morfologia_kernel": 2,
}


def escala_de_grises(imagen_bgr):
    return cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY)


def redimensionar(gris, alto_minimo):
    """Solo agranda; achicar empeoró la lectura en el banco."""
    alto, ancho = gris.shape
    if alto >= alto_minimo:
        return gris
    factor = alto_minimo / alto
    return cv2.resize(gris, (round(ancho * factor), alto_minimo), interpolation=cv2.INTER_CUBIC)


def filtrar_mediana(gris, kernel):
    if not kernel:
        return gris
    return cv2.medianBlur(gris, kernel)


def desenfocar(gris, kernel):
    if not kernel:
        return gris
    return cv2.GaussianBlur(gris, (kernel, kernel), 0)


def binarizar(gris, metodo, adaptativo_block_size, adaptativo_c):
    if metodo == "otsu":
        _, binaria = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binaria
    if metodo == "adaptativo":
        return cv2.adaptiveThreshold(
            gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
            adaptativo_block_size, adaptativo_c,
        )
    raise ValueError(f"método de binarización desconocido: {metodo!r}")


def limpiar_morfologicamente(binaria, kernel_size):
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    # OPEN saca puntos sueltos, CLOSE cierra huecos dentro de los trazos.
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, kernel)
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)
    return binaria


def preprocesar(imagen_bgr, parametros=None):
    """Devuelve (imagen, pasos) con pasos = {nombre_etapa: imagen intermedia}."""
    p = {**PARAMETROS_DEFAULT, **(parametros or {})}

    gris = escala_de_grises(imagen_bgr)
    redimensionada = redimensionar(gris, p["alto_minimo"])
    sin_ruido = filtrar_mediana(redimensionada, p["mediana_kernel"])
    sin_ruido = desenfocar(sin_ruido, p["blur_kernel"])

    pasos = {
        "1_gris": gris,
        "2_redimensionada": redimensionada,
        "3_sin_ruido": sin_ruido,
    }

    if not p["binarizar"]:
        return sin_ruido, pasos

    binaria = binarizar(sin_ruido, p["metodo_binarizacion"], p["adaptativo_block_size"], p["adaptativo_c"])
    if p["morfologia"]:
        binaria = limpiar_morfologicamente(binaria, p["morfologia_kernel"])
    pasos["4_binaria"] = binaria
    return binaria, pasos

