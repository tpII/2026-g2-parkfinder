"""Genera 3 niveles de degradación (leve/medio/fuerte) por recorte para
simular una cámara de menor calidad: baja de resolución, blur gaussiano,
ruido gaussiano y recompresión JPG.

Salida: imagenes/degradadas/{recorte}_deg_{nivel}.jpg
Las degradadas versionadas son las usadas en las mediciones (generadas antes
de fijar SEMILLA); regenerarlas produce otras imágenes.
"""

from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DIR_FUENTE = BASE_DIR / "imagenes" / "fuente"
DIR_DEGRADADAS = BASE_DIR / "imagenes" / "degradadas"

SEMILLA = 0
_rng = np.random.default_rng(SEMILLA)

# escala: fracción del tamaño al achicar; blur: kernel gaussiano (impar);
# ruido_sigma: desvío del ruido por canal; calidad_jpg: 0-100.
# Calibrado con Tesseract crudo: "fuerte" es donde empiezan a fallar chica/mini.
NIVELES = {
    "leve": {"escala": 0.45, "blur": 3, "ruido_sigma": 10, "calidad_jpg": 55},
    "medio": {"escala": 0.22, "blur": 7, "ruido_sigma": 20, "calidad_jpg": 25},
    "fuerte": {"escala": 0.08, "blur": 13, "ruido_sigma": 35, "calidad_jpg": 8},
}


def reducir_resolucion(imagen, escala):
    alto, ancho = imagen.shape[:2]
    chico = cv2.resize(imagen, (max(1, round(ancho * escala)), max(1, round(alto * escala))),
                        interpolation=cv2.INTER_AREA)
    return cv2.resize(chico, (ancho, alto), interpolation=cv2.INTER_LINEAR)


def agregar_ruido_gaussiano(imagen, sigma):
    ruido = _rng.normal(0, sigma, imagen.shape)
    return np.clip(imagen.astype(np.float32) + ruido, 0, 255).astype(np.uint8)


def degradar(imagen, parametros):
    salida = reducir_resolucion(imagen, parametros["escala"])
    k = parametros["blur"]
    salida = cv2.GaussianBlur(salida, (k, k), 0)
    salida = agregar_ruido_gaussiano(salida, parametros["ruido_sigma"])
    return salida


def main():
    DIR_DEGRADADAS.mkdir(parents=True, exist_ok=True)
    recortes = sorted(DIR_FUENTE.glob("*.jpg"))
    if not recortes:
        print(f"No hay recortes en {DIR_FUENTE}")
        return

    total = 0
    for ruta in recortes:
        imagen = cv2.imread(str(ruta))
        if imagen is None:
            print(f"[ERROR] No se pudo abrir {ruta.name}")
            continue
        for nivel, parametros in NIVELES.items():
            degradada = degradar(imagen, parametros)
            nombre_salida = f"{ruta.stem}_deg_{nivel}.jpg"
            ruta_salida = DIR_DEGRADADAS / nombre_salida
            cv2.imwrite(str(ruta_salida), degradada,
                        [cv2.IMWRITE_JPEG_QUALITY, parametros["calidad_jpg"]])
            total += 1
        print(f"[OK] {ruta.name} -> 3 niveles")

    print(f"\nListo: {total} imágenes degradadas generadas en {DIR_DEGRADADAS}/")


if __name__ == "__main__":
    main()
