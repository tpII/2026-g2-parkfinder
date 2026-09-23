"""Extrae las 4 patentes de cada foto de imagenes/originales/ a
imagenes/fuente/ detectando rectángulos por contorno (las fotos son a mano,
con encuadre variable) y asignándolos por cuadrante con LAYOUT_POR_TAMANO.

Si una foto no da 4 candidatos sin ambigüedad se marca como fallo y se deja
una imagen en imagenes/debug_recorte/. chica_v2 y mini_v2 fallan (poco
contraste con el fondo) y se recortaron a mano: correr este script no los pisa.

"""

import csv
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DIR_ORIGINALES = BASE_DIR / "imagenes" / "originales"
DIR_FUENTE = BASE_DIR / "imagenes" / "fuente"
DIR_DEBUG = BASE_DIR / "imagenes" / "debug_recorte"
CSV_ETIQUETAS = BASE_DIR / "imagenes" / "etiquetas.csv"

# Patente en cada cuadrante de cada caja (armado físico de la maqueta).
LAYOUT_POR_TAMANO = {
    "grande": {"TL": "DL908XR", "TR": "VNH615", "BL": "QW372ZP", "BR": "KGF480"},
    "media": {"TL": "MPT236", "TR": "BJ741CY", "BL": "XSO059", "BR": "RE483UK"},
    "chica": {"TL": "ZWD167", "TR": "AF520GN", "BL": "TCU894", "BR": "HM316QL"},
    "mini": {"TL": "PV649EW", "TR": "YIB703", "BL": "SX087DZ", "BR": "JOK251"},
}

ASPECT_RATIO_MIN = 1.7
ASPECT_RATIO_MAX = 3.3
AREA_FRACCION_MIN = 0.004   # candidato debe ocupar al menos 0.4% del área de la foto
AREA_FRACCION_MAX = 0.08    # y como mucho 8% (el contorno de toda la caja es mucho más grande)
EXTENT_MIN = 0.75           # área del contorno / área de su rectángulo delimitador
RATIO_HOMOGENEIDAD_AREA = 1.6  # tolerancia para agrupar candidatos "del mismo tamaño"
MARGEN_FRACCION = 0.05      # margen extra al recortar, como fracción del lado menor


def _solapan(a, b, umbral=0.6):
    """IoU aproximado entre dos rectángulos (x, y, w, h)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter == 0:
        return False
    union = aw * ah + bw * bh - inter
    return inter / union >= umbral


def detectar_rectangulos(imagen_bgr):
    """Devuelve (x, y, w, h) de los contornos con proporción, área y extent
    (área / área del rectángulo delimitador) de una etiqueta de patente.
    RETR_LIST porque las etiquetas quedan dentro del contorno de la caja; los
    contornos anidados se deduplican por superposición. El kernel se escala
    con el ancho: en fotos grandes el borde impreso es más grueso."""
    gris = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2GRAY)
    gris = cv2.GaussianBlur(gris, (5, 5), 0)
    bordes = cv2.Canny(gris, 30, 90)

    alto_img, ancho_img = gris.shape
    escala = max(1, round(ancho_img / 1200))
    kernel = np.ones((2 * escala + 1, 2 * escala + 1), np.uint8)
    bordes = cv2.dilate(bordes, kernel, iterations=1)
    bordes = cv2.morphologyEx(bordes, cv2.MORPH_CLOSE, kernel, iterations=1)

    contornos, _ = cv2.findContours(bordes, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area_img = alto_img * ancho_img

    candidatos = []
    for c in contornos:
        area = cv2.contourArea(c)
        if area < area_img * AREA_FRACCION_MIN or area > area_img * AREA_FRACCION_MAX:
            continue
        x, y, w, h = cv2.boundingRect(c)
        ratio = w / h if h else 0
        if not (ASPECT_RATIO_MIN <= ratio <= ASPECT_RATIO_MAX):
            continue
        extent = area / (w * h) if w and h else 0
        if extent < EXTENT_MIN:
            continue
        candidatos.append((x, y, w, h, area))

    candidatos.sort(key=lambda r: r[4], reverse=True)
    deduplicados = []
    for x, y, w, h, area in candidatos:
        if any(_solapan((x, y, w, h), s, umbral=0.4) for s in deduplicados):
            continue
        deduplicados.append((x, y, w, h))

    return seleccionar_grupo_homogeneo(deduplicados)


def seleccionar_grupo_homogeneo(rectangulos):
    """Se queda con el grupo más grande de rectángulos de área similar
    (RATIO_HOMOGENEIDAD_AREA): las 4 patentes de una caja miden lo mismo."""
    if not rectangulos:
        return []

    por_area = sorted(rectangulos, key=lambda r: r[2] * r[3])
    mejor_grupo, grupo_actual = [], [por_area[0]]
    for anterior, actual in zip(por_area, por_area[1:]):
        area_ant = anterior[2] * anterior[3]
        area_act = actual[2] * actual[3]
        if area_act / area_ant <= RATIO_HOMOGENEIDAD_AREA:
            grupo_actual.append(actual)
        else:
            if len(grupo_actual) > len(mejor_grupo):
                mejor_grupo = grupo_actual
            grupo_actual = [actual]
    if len(grupo_actual) > len(mejor_grupo):
        mejor_grupo = grupo_actual
    return mejor_grupo


def clasificar_por_cuadrante(candidatos):
    """Asigna cada candidato a TL/TR/BL/BR según su centroide. Devuelve None
    si no son exactamente 4 o algún cuadrante queda vacío o duplicado."""
    if len(candidatos) != 4:
        return None

    centros = [(x + w / 2, y + h / 2) for (x, y, w, h) in candidatos]
    xs = sorted(cx for cx, _ in centros)
    ys = sorted(cy for _, cy in centros)
    x_medio = (xs[1] + xs[2]) / 2
    y_medio = (ys[1] + ys[2]) / 2

    asignados = {}
    for rect, (cx, cy) in zip(candidatos, centros):
        clave = ("T" if cy < y_medio else "B") + ("L" if cx < x_medio else "R")
        if clave in asignados:
            return None  # dos candidatos en el mismo cuadrante
        asignados[clave] = rect

    if set(asignados) != {"TL", "TR", "BL", "BR"}:
        return None
    return asignados


def guardar_debug(imagen_bgr, rectangulos, ruta_salida):
    debug = imagen_bgr.copy()
    for etiqueta, (x, y, w, h) in rectangulos.items():
        cv2.rectangle(debug, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.putText(debug, str(etiqueta), (x, max(30, y - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    cv2.imwrite(str(ruta_salida), debug)


def recortar_original(ruta_imagen, tamano, version):
    imagen = cv2.imread(str(ruta_imagen))
    if imagen is None:
        print(f"  [ERROR] No se pudo abrir {ruta_imagen.name}")
        return False

    candidatos = detectar_rectangulos(imagen)
    asignados = clasificar_por_cuadrante(candidatos)

    DIR_DEBUG.mkdir(parents=True, exist_ok=True)
    if asignados is None:
        print(f"  [FALLO] {ruta_imagen.name}: se detectaron {len(candidatos)} "
              f"candidatos (se esperaban 4 sin ambigüedad). Recortar a mano.")
        rectangulos_debug = {f"cand{i}": r for i, r in enumerate(candidatos)}
        guardar_debug(imagen, rectangulos_debug, DIR_DEBUG / f"{ruta_imagen.stem}_FALLO.jpg")
        return False

    layout = LAYOUT_POR_TAMANO[tamano]
    alto_img, ancho_img = imagen.shape[:2]
    for cuadrante, patente in layout.items():
        x, y, w, h = asignados[cuadrante]
        margen = round(MARGEN_FRACCION * min(w, h))
        x0 = max(0, x - margen)
        y0 = max(0, y - margen)
        x1 = min(ancho_img, x + w + margen)
        y1 = min(alto_img, y + h + margen)
        recorte = imagen[y0:y1, x0:x1]

        nombre = f"{tamano}_{version}_{patente}.jpg"
        cv2.imwrite(str(DIR_FUENTE / nombre), recorte)

    guardar_debug(imagen, asignados, DIR_DEBUG / f"{ruta_imagen.stem}_OK.jpg")
    print(f"  [OK] {ruta_imagen.name}: 4 patentes recortadas")
    return True


def main():
    DIR_FUENTE.mkdir(parents=True, exist_ok=True)

    with open(CSV_ETIQUETAS, newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))

    originales = {}
    for fila in filas:
        originales[(fila["tamano"], fila["version"])] = fila["original"]

    ok, fallos = 0, []
    for (tamano, version), nombre_original in sorted(originales.items()):
        ruta = DIR_ORIGINALES / nombre_original
        if not ruta.exists():
            print(f"[ERROR] No existe {ruta}")
            fallos.append(nombre_original)
            continue
        print(f"Procesando {nombre_original} ({tamano} {version})...")
        if recortar_original(ruta, tamano, version):
            ok += 1
        else:
            fallos.append(nombre_original)

    print()
    print(f"Listo: {ok}/{len(originales)} fotos originales procesadas correctamente.")
    if fallos:
        print(f"Revisar manualmente ({len(fallos)}): {', '.join(fallos)}")
    print(f"Visualizaciones de debug en {DIR_DEBUG}/")


if __name__ == "__main__":
    main()
