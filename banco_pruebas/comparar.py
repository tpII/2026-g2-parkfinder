"""Compara los motores OCR (Tesseract, EasyOCR, PaddleOCR) sobre el banco
completo: precisión tras post-proceso + validación y tiempo por imagen.

Uso: python comparar.py
Salida: resultados_motores.csv
"""

import csv
import time

import cv2

from banco import (BASE_DIR, imprimir_resumen, listar_imagenes, nivel_de,
                   patente_esperada, tamano_de)
from motores.motor_easyocr import MotorEasyOCR
from motores.motor_paddle import MotorPaddle
from motores.motor_tesseract import MotorTesseract
from postproceso import corregir
from validacion import validar

CSV_SALIDA = BASE_DIR / "resultados_motores.csv"


def evaluar_motor(motor, archivos):
    filas = []
    for i, ruta in enumerate(archivos, 1):
        imagen = cv2.imread(str(ruta))
        esperado = patente_esperada(ruta.stem)

        inicio = time.perf_counter()
        texto, confianza = motor.leer(imagen)
        duracion = time.perf_counter() - inicio

        corregido = corregir(texto)
        formato = validar(corregido)

        filas.append({
            "motor": motor.nombre,
            "tamano": tamano_de(ruta.stem),
            "nivel": nivel_de(ruta.stem),
            "archivo": ruta.name,
            "esperado": esperado,
            "leido": texto,
            "confianza": round(confianza, 3),
            "corregido": corregido,
            "formato": formato or "",
            "ok": corregido == esperado,
            "tiempo_seg": round(duracion, 3),
        })
        if i % 20 == 0:
            print(f"  ... {i}/{len(archivos)}")
    return filas


def main():
    archivos = listar_imagenes()
    if not archivos:
        print("No hay imágenes para evaluar (¿corriste recortar.py y degradar.py?)")
        return

    motores = [MotorTesseract(), MotorEasyOCR(), MotorPaddle()]

    todas_las_filas = []
    resumen_final = []
    for motor in motores:
        print(f"\nCorriendo {motor.nombre} sobre {len(archivos)} imágenes...")
        filas = evaluar_motor(motor, archivos)
        todas_las_filas.extend(filas)
        ok = imprimir_resumen(f"=== {motor.nombre} ===", filas)
        tiempo_prom = sum(f["tiempo_seg"] for f in filas) / len(filas)
        print(f"Tiempo promedio por imagen: {tiempo_prom:.3f} s")
        resumen_final.append((motor.nombre, ok, tiempo_prom))

    print("\n=== Comparación final ===")
    print(f"{'motor':12s} {'aciertos':16s} {'tiempo prom./img'}")
    for nombre, ok, tiempo_prom in resumen_final:
        print(f"{nombre:12s} {ok}/{len(archivos)} ({100 * ok / len(archivos):.1f}%)   {tiempo_prom:.3f} s")

    with open(CSV_SALIDA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "motor", "tamano", "nivel", "archivo", "esperado",
            "leido", "confianza", "corregido", "formato", "ok", "tiempo_seg",
        ])
        w.writeheader()
        w.writerows(todas_las_filas)
    print(f"\nGuardado detalle en {CSV_SALIDA.name}")


if __name__ == "__main__":
    main()
