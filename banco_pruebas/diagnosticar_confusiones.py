"""Diagnostica las confusiones letra↔letra de Tesseract: aísla el carácter
que falla y lo vuelve a leer solo (--psm 10) para distinguir si el error es
de la imagen o del motor en contexto de palabra.

Uso: python diagnosticar_confusiones.py
Salida: zooms en imagenes/debug_confusiones/ y tabla por consola.
"""

import cv2
import pytesseract
from pytesseract import Output

from banco import BASE_DIR, buscar_archivo
from motores.motor_tesseract import CONFIG as CONFIG_PALABRA
from preprocesamiento import preprocesar

DIR_DEBUG = BASE_DIR / "imagenes" / "debug_confusiones"

CONFIG_CARACTER = "--psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# (archivo, patente esperada, posición 0-indexada del carácter que falla, carácter esperado)
CASOS = [
    ("grande_v2_QW372ZP.jpg", "QW372ZP", 1, "W"),
    ("grande_v2_QW372ZP_deg_medio.jpg", "QW372ZP", 1, "W"),
    ("chica_v1_HM316QL.jpg", "HM316QL", 5, "Q"),
    ("chica_v2_ZWD167_deg_leve.jpg", "ZWD167", 1, "W"),
    ("mini_v2_PV649EW_deg_leve.jpg", "PV649EW", 6, "W"),
    ("mini_v2_JOK251.jpg", "JOK251", 0, "J"),
    ("media_v2_BJ741CY_deg_medio.jpg", "BJ741CY", 1, "J"),
]


def caja_del_caracter(imagen_gris, texto_esperado_len, posicion):
    """Divide la caja de la palabra completa en franjas iguales y devuelve la
    de la posición pedida. image_to_boxes (caja por carácter) se descartó:
    segmenta distinto que image_to_string y desalinea las posiciones."""
    datos = pytesseract.image_to_data(imagen_gris, config=CONFIG_PALABRA, output_type=Output.DICT)
    candidatos = [
        (l, t, w, h) for txt, l, t, w, h in
        zip(datos["text"], datos["left"], datos["top"], datos["width"], datos["height"])
        if txt.strip()
    ]
    if not candidatos:
        return None
    x, y, w, h = candidatos[0]
    ancho_char = w / texto_esperado_len
    x0 = round(x + posicion * ancho_char)
    x1 = round(x + (posicion + 1) * ancho_char)
    return x0, y, x1, y + h


def diagnosticar(nombre, esperado, posicion, caracter_esperado):
    ruta = buscar_archivo(nombre)
    imagen = cv2.imread(str(ruta))
    preprocesada, _ = preprocesar(imagen)

    leido = pytesseract.image_to_string(preprocesada, config=CONFIG_PALABRA).strip()

    DIR_DEBUG.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(DIR_DEBUG / f"{ruta.stem}_1_preprocesada.jpg"), preprocesada)

    caja = caja_del_caracter(preprocesada, len(esperado), posicion)
    if caja is None:
        print(f"{nombre:38s} esperado={esperado:9s} leido={leido!r:12s} "
              f"-> Tesseract no ubicó la palabra como bloque, no se pudo aislar")
        return

    x0, y0, x1, y1 = caja
    margen = 3  # más margen mezcla caracteres vecinos
    alto_img, ancho_img = preprocesada.shape
    x0, y0 = max(0, x0 - margen), max(0, y0 - margen)
    x1, y1 = min(ancho_img, x1 + margen), min(alto_img, y1 + margen)
    recorte_caracter = preprocesada[y0:y1, x0:x1]

    nombre_zoom = DIR_DEBUG / f"{ruta.stem}_2_zoom_pos{posicion}.jpg"
    zoom_grande = cv2.resize(recorte_caracter, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(str(nombre_zoom), zoom_grande)

    datos = pytesseract.image_to_data(recorte_caracter, config=CONFIG_CARACTER, output_type=Output.DICT)
    candidatos = [(t, c) for t, c in zip(datos["text"], datos["conf"]) if t.strip()]
    if candidatos:
        caracter_aislado, confianza = candidatos[0]
    else:
        caracter_aislado, confianza = "(vacío)", -1

    leido_en_palabra = leido[posicion] if posicion < len(leido) else "?"
    print(f"{nombre:38s} pos={posicion} esperado={caracter_esperado} "
          f"leido_en_palabra={leido_en_palabra} leido_aislado={caracter_aislado!r} "
          f"confianza_aislada={confianza}")


def main():
    print(f"{'archivo':38s} {'detalle'}")
    for caso in CASOS:
        diagnosticar(*caso)
    print(f"\nZooms guardados en {DIR_DEBUG}/")


if __name__ == "__main__":
    main()
