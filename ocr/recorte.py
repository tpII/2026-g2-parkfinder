"""Recorte de patentes por plaza: la cámara es fija, así que cada plaza ocupa
siempre la misma zona de la imagen (calibrada una vez). Dentro de esa zona se
busca la fila de caracteres de la patente y se recorta con un margen.

Se buscan los caracteres y no el marco de la patente porque en las fotos de
webcam el marco tiene poco contraste con el soporte y su contorno queda
abierto (no cierra como rectángulo); los caracteres, en cambio, siempre
contrastan: es lo que el OCR necesita leer.

Configuración de plazas (JSON):
  {"resolucion": [1280, 720],
   "plazas": {"1": [x, y, ancho, alto], "2": [x, y, ancho, alto]}}
Las coordenadas están en píxeles de la resolución de calibración; si la imagen
llega con otra resolución se escalan.
"""

import json

import cv2

MIN_ALTO_CARACTER = 8          # px; menos que esto no se puede leer
MAX_ALTO_CARACTER = 0.8        # fracción del alto de la zona
PROPORCION_CARACTER = (1.1, 6.0)  # alto / ancho: más altos que anchos (el 1 es angosto)
RELLENO_MIN = 0.15             # área de tinta / área del rectángulo del carácter
TOLERANCIA_ALTO = 0.25         # los caracteres de una patente miden lo mismo
TOLERANCIA_FILA = 0.35         # centro vertical, en alturas de carácter
HUECO_MAX = 3.0                # separación máxima entre caracteres, en alturas (cubre
                               # caracteres pegados que no pasan el filtro, p. ej. "SO" a 50 cm)
MIN_CARACTERES = 4             # menos que esto no es una patente (son 6 o 7)


def cargar_plazas(ruta):
    """Devuelve (resolucion, {nombre: (x, y, ancho, alto)})."""
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    return tuple(datos["resolucion"]), {n: tuple(z) for n, z in datos["plazas"].items()}


def escalar_zona(zona, resolucion, imagen):
    """Ajusta una zona calibrada a la resolución real de la imagen."""
    alto_img, ancho_img = imagen.shape[:2]
    fx, fy = ancho_img / resolucion[0], alto_img / resolucion[1]
    x, y, w, h = zona
    return round(x * fx), round(y * fy), round(w * fx), round(h * fy)


def _caracteres(gris):
    """Manchas oscuras con forma de carácter (x, y, ancho, alto)."""
    alto, ancho = gris.shape
    # Umbral adaptativo: tolera luz despareja dentro de la zona.
    bloque = max(15, (min(alto, ancho) // 6) | 1)
    binaria = cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                    cv2.THRESH_BINARY_INV, bloque, 15)
    n, _, stats, _ = cv2.connectedComponentsWithStats(binaria, 8)
    caracteres = []
    for x, y, w, h, area in stats[1:n]:
        if h < MIN_ALTO_CARACTER or h > MAX_ALTO_CARACTER * alto:
            continue
        if not PROPORCION_CARACTER[0] <= h / w <= PROPORCION_CARACTER[1]:
            continue
        if area < RELLENO_MIN * w * h:
            continue
        caracteres.append((int(x), int(y), int(w), int(h)))
    return caracteres


def _mejor_fila(caracteres):
    """El grupo más grande de caracteres de altura parecida, en la misma fila
    y sin huecos grandes entre ellos."""
    mejor = []
    for _, sy, _, sh in caracteres:
        centro = sy + sh / 2
        fila = sorted((c for c in caracteres
                       if abs(c[3] - sh) <= TOLERANCIA_ALTO * sh
                       and abs(c[1] + c[3] / 2 - centro) <= TOLERANCIA_FILA * sh),
                      key=lambda c: c[0])
        tramo = [fila[0]]
        for anterior, actual in zip(fila, fila[1:]):
            if actual[0] - (anterior[0] + anterior[2]) > HUECO_MAX * sh:
                if len(tramo) > len(mejor):
                    mejor = tramo
                tramo = []
            tramo.append(actual)
        if len(tramo) > len(mejor):
            mejor = tramo
    return mejor


def localizar_patente(zona_bgr):
    """(x0, y0, x1, y1) de la patente dentro de la zona, o None si no hay una
    fila de al menos MIN_CARACTERES caracteres."""
    gris = cv2.cvtColor(zona_bgr, cv2.COLOR_BGR2GRAY)
    fila = _mejor_fila(_caracteres(gris))
    if len(fila) < MIN_CARACTERES:
        return None
    alto, ancho = gris.shape
    x0 = min(c[0] for c in fila)
    x1 = max(c[0] + c[2] for c in fila)
    y0 = min(c[1] for c in fila)
    y1 = max(c[1] + c[3] for c in fila)
    # Margen: media altura a los costados (cubre un carácter que no se haya
    # detectado en una punta) y un tercio arriba y abajo.
    h = y1 - y0
    return (max(0, x0 - h // 2), max(0, y0 - h // 3),
            min(ancho, x1 + h // 2), min(alto, y1 + h // 3))


def recortar_plaza(imagen_bgr, zona):
    """Recorte de la patente de una plaza, o None si no se encontró."""
    x, y, w, h = zona
    region = imagen_bgr[y:y + h, x:x + w]
    caja = localizar_patente(region)
    if caja is None:
        return None
    x0, y0, x1, y1 = caja
    return region[y0:y1, x0:x1]


def recortar_plazas(imagen_bgr, plazas, resolucion):
    """{nombre de plaza: recorte de la patente o None}."""
    return {nombre: recortar_plaza(imagen_bgr, escalar_zona(zona, resolucion, imagen_bgr))
            for nombre, zona in plazas.items()}
