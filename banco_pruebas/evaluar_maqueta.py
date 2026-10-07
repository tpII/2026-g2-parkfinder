"""Evalúa recorte por plaza + Tesseract sobre las fotos del prototipo de maqueta
(imagenes/maqueta/), con UNA sola calibración de zonas para todas las fotos
(imagenes/maqueta/plazas.json), como en el sistema real con la cámara fija.

Nombres: {escena}{toma}_{PATENTE plaza 1}_{PATENTE plaza 2}.jpg; VACIA = plaza
sin auto (no debe encontrarse patente). Deja en imagenes/debug_maqueta/ cada
foto con las zonas (azul) y la patente encontrada (rojo).

Uso: python evaluar_maqueta.py
"""

import time
from collections import Counter

import cv2

from banco import BASE_DIR
from motores.motor_tesseract import MotorTesseract
from postproceso import corregir
from recorte import cargar_plazas, escalar_zona, localizar_patente
from validacion import validar

DIR_FOTOS = BASE_DIR / "imagenes" / "maqueta"
DIR_DEBUG = BASE_DIR / "imagenes" / "debug_maqueta"
VACIA = "VACIA"


def main():
    resolucion, plazas = cargar_plazas(DIR_FOTOS / "plazas.json")
    DIR_DEBUG.mkdir(exist_ok=True)
    motor = MotorTesseract()
    resultados = Counter()
    tiempos_ocr = []

    for ruta in sorted(DIR_FOTOS.glob("*.jpg")):
        foto, *esperadas = ruta.stem.split("_")
        imagen = cv2.imread(str(ruta))
        debug = imagen.copy()

        for (nombre, zona), esperado in zip(sorted(plazas.items()), esperadas):
            x, y, w, h = escalar_zona(zona, resolucion, imagen)
            cv2.rectangle(debug, (x, y), (x + w, y + h), (255, 0, 0), 3)
            caja = localizar_patente(imagen[y:y + h, x:x + w])

            if caja is None:
                estado = "OK (vacía)" if esperado == VACIA else "NO ENCONTRADA"
                leido = "-"
            else:
                x0, y0, x1, y1 = caja
                cv2.rectangle(debug, (x + x0, y + y0), (x + x1, y + y1), (0, 0, 255), 3)
                inicio = time.perf_counter()
                texto, _ = motor.leer(imagen[y + y0:y + y1, x + x0:x + x1])
                tiempos_ocr.append(time.perf_counter() - inicio)
                leido = corregir(texto)
                if esperado == VACIA:
                    estado = "FALSO POSITIVO"
                elif leido == esperado:
                    estado = "OK"
                elif not validar(leido):
                    estado = "fallida"
                else:
                    estado = "ERROR SILENCIOSO"
            resultados[estado] += 1
            print(f"{foto} plaza {nombre}: esperado {esperado:8s} leído {leido:8s} {estado}")

        cv2.imwrite(str(DIR_DEBUG / ruta.name), debug)

    total = sum(resultados.values())
    print(f"\nResumen sobre {total} plazas:")
    for estado, n in resultados.most_common():
        print(f"  {estado:18s} {n}")
    if tiempos_ocr:
        tiempos_ocr.sort()
        print(f"OCR por patente: mediana {1000 * tiempos_ocr[len(tiempos_ocr) // 2]:.0f} ms")


if __name__ == "__main__":
    main()
