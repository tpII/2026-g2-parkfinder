"""Mide el aporte de cada etapa del pipeline con Tesseract sobre el banco
completo: crudo -> + preprocesamiento -> + post-proceso y validación.

Uso: python evaluar_banco.py
Salida: resultados_ocr.csv
"""

import csv

import cv2
import pytesseract

from banco import (BASE_DIR, imprimir_resumen, listar_imagenes, nivel_de,
                   patente_esperada, tamano_de)
from motores.motor_tesseract import CONFIG
from postproceso import corregir
from preprocesamiento import preprocesar
from validacion import validar

CSV_SALIDA = BASE_DIR / "resultados_ocr.csv"


def leer_texto(imagen):
    return pytesseract.image_to_string(imagen, config=CONFIG).strip()


def main():
    archivos = listar_imagenes()
    if not archivos:
        print("No hay imágenes para evaluar (¿corriste recortar.py y degradar.py?)")
        return

    filas = []
    for ruta in archivos:
        imagen = cv2.imread(str(ruta))
        esperado = patente_esperada(ruta.stem)

        leido_crudo = leer_texto(imagen)
        preprocesada, _ = preprocesar(imagen)
        leido_prep = leer_texto(preprocesada)
        leido_final = corregir(leido_prep)
        formato_final = validar(leido_final)

        filas.append({
            "tamano": tamano_de(ruta.stem),
            "nivel": nivel_de(ruta.stem),
            "archivo": ruta.name,
            "esperado": esperado,
            "leido_crudo": leido_crudo,
            "ok_crudo": leido_crudo == esperado,
            "leido_prep": leido_prep,
            "ok_prep": leido_prep == esperado,
            "leido_final": leido_final,
            "formato_final": formato_final or "",
            "ok_final": leido_final == esperado,
        })

    ok_crudo = imprimir_resumen("=== Tesseract crudo ===", filas, "ok_crudo")
    ok_prep = imprimir_resumen("=== Tesseract + preprocesamiento ===", filas, "ok_prep")
    ok_final = imprimir_resumen("=== + post-proceso por posición + validación ===", filas, "ok_final")

    print(f"\ncrudo -> preprocesado: {ok_prep - ok_crudo:+d}")
    print(f"preprocesado -> final: {ok_final - ok_prep:+d}")
    print(f"crudo -> final:        {ok_final - ok_crudo:+d}  (de {len(filas)})")

    corrigieron = [f for f in filas if not f["ok_prep"] and f["ok_final"]]
    rompieron = [f for f in filas if f["ok_prep"] and not f["ok_final"]]
    print(f"\nEl post-proceso corrigió: {len(corrigieron)}")
    print(f"El post-proceso rompió:   {len(rompieron)}")

    fallidas = [f for f in filas if not f["formato_final"]]
    validas_pero_incorrectas = [f for f in filas if f["formato_final"] and not f["ok_final"]]
    print(f"\nLecturas marcadas 'fallida' (no matchea ningún formato): {len(fallidas)}/{len(filas)}")
    print(f"Formato válido pero patente incorrecta (error silencioso):  {len(validas_pero_incorrectas)}/{len(filas)}")

    with open(CSV_SALIDA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "tamano", "nivel", "archivo", "esperado",
            "leido_crudo", "ok_crudo", "leido_prep", "ok_prep",
            "leido_final", "formato_final", "ok_final",
        ])
        w.writeheader()
        w.writerows(filas)
    print(f"\nGuardado detalle en {CSV_SALIDA.name}")


if __name__ == "__main__":
    main()
