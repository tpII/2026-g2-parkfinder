"""Evalúa recorte por plaza + Tesseract sobre las fotos de la webcam de la
notebook (imagenes/notebook/), con las zonas de imagenes/notebook/plazas.json.

Nombres: {foto}_{PATENTE plaza 1}_{PATENTE plaza 2}.jpg, plazas de izquierda
a derecha. Deja en imagenes/debug_notebook/ cada foto con las zonas (azul) y
la patente encontrada (rojo).

Uso: python evaluar_notebook.py
"""

import json
import time

import cv2

from banco import BASE_DIR
from motores.motor_tesseract import MotorTesseract
from postproceso import corregir
from recorte import escalar_zona, localizar_patente
from validacion import validar

DIR_FOTOS = BASE_DIR / "imagenes" / "notebook"
DIR_DEBUG = BASE_DIR / "imagenes" / "debug_notebook"


def main():
    with open(DIR_FOTOS / "plazas.json", encoding="utf-8") as f:
        config = json.load(f)
    DIR_DEBUG.mkdir(exist_ok=True)
    motor = MotorTesseract()

    total = aciertos = fallidas = silenciosos = 0
    for ruta in sorted(DIR_FOTOS.glob("*.jpg")):
        foto, *esperadas = ruta.stem.split("_")
        imagen = cv2.imread(str(ruta))
        debug = imagen.copy()
        resolucion = config[foto]["resolucion"]
        plazas = config[foto]["plazas"]

        for (nombre, zona), esperado in zip(sorted(plazas.items()), esperadas):
            x, y, w, h = escalar_zona(zona, resolucion, imagen)
            cv2.rectangle(debug, (x, y), (x + w, y + h), (255, 0, 0), 2)

            inicio = time.perf_counter()
            caja = localizar_patente(imagen[y:y + h, x:x + w])
            t_recorte = time.perf_counter() - inicio
            total += 1
            if caja is None:
                fallidas += 1
                print(f"{foto} plaza {nombre}: sin patente  (esperado {esperado})")
                continue

            x0, y0, x1, y1 = caja
            cv2.rectangle(debug, (x + x0, y + y0), (x + x1, y + y1), (0, 0, 255), 2)
            inicio = time.perf_counter()
            texto, _ = motor.leer(imagen[y + y0:y + y1, x + x0:x + x1])
            t_ocr = time.perf_counter() - inicio
            leido = corregir(texto)
            formato = validar(leido)

            ok = leido == esperado
            aciertos += ok
            if not formato:
                fallidas += 1
            elif not ok:
                silenciosos += 1
            estado = "OK" if ok else ("fallida" if not formato else "ERROR SILENCIOSO")
            print(f"{foto} plaza {nombre}: patente {x1 - x0}x{y1 - y0}px  leído {leido:8s} "
                  f"esperado {esperado:8s} {estado:16s} recorte {1000 * t_recorte:.0f} ms, OCR {1000 * t_ocr:.0f} ms")

        cv2.imwrite(str(DIR_DEBUG / ruta.name), debug)

    print(f"\nAciertos: {aciertos}/{total}")
    print(f"Fallidas (sin patente o formato inválido): {fallidas}/{total}")
    print(f"Formato válido pero patente incorrecta (error silencioso): {silenciosos}/{total}")


if __name__ == "__main__":
    main()
