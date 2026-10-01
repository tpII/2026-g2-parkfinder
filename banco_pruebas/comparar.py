"""Compara los motores OCR (Tesseract, EasyOCR, PaddleOCR) sobre el banco
completo: precisión tras post-proceso + validación, tiempo por imagen,
tiempo de carga del motor y pico de memoria.

Uso: python comparar.py [--motores tesseract,easyocr,paddleocr] [--salida archivo.csv]
     En la Pi, de a un motor por proceso: el pico de memoria es del proceso
     entero, así que con varios motores en la misma corrida se acumula.
Salida: resultados_motores.csv (o la indicada en --salida)
"""

import argparse
import csv
import importlib
import time

import cv2

from banco import (BASE_DIR, imprimir_resumen, listar_imagenes, nivel_de,
                   patente_esperada, tamano_de)
from postproceso import corregir
from validacion import validar

# Import perezoso: en la Pi solo está instalado el motor que se está midiendo.
MOTORES = {
    "tesseract": ("motores.motor_tesseract", "MotorTesseract"),
    "easyocr": ("motores.motor_easyocr", "MotorEasyOCR"),
    "paddleocr": ("motores.motor_paddle", "MotorPaddle"),
}


def cargar_motor(nombre):
    modulo, clase = MOTORES[nombre]
    return getattr(importlib.import_module(modulo), clase)()


def pico_memoria_mb():
    """Pico de memoria residente (solo Linux/Mac; None en Windows): el de
    Python más el del subproceso más grande, porque pytesseract ejecuta el
    binario de Tesseract aparte y su memoria no cuenta en RUSAGE_SELF."""
    try:
        import resource
    except ImportError:
        return None
    propio = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    hijos = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return (propio + hijos) / 1024  # KB en Linux


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--motores", default=",".join(MOTORES),
                        help="lista separada por comas: " + ", ".join(MOTORES))
    parser.add_argument("--salida", default="resultados_motores.csv",
                        help="nombre del CSV de salida (dentro de banco_pruebas/)")
    args = parser.parse_args()
    nombres = [n.strip() for n in args.motores.split(",") if n.strip()]
    desconocidos = [n for n in nombres if n not in MOTORES]
    if desconocidos:
        parser.error(f"motores desconocidos: {', '.join(desconocidos)}")
    csv_salida = BASE_DIR / args.salida

    archivos = listar_imagenes()
    if not archivos:
        print("No hay imágenes para evaluar (¿corriste recortar.py y degradar.py?)")
        return

    todas_las_filas = []
    resumen_final = []
    for nombre in nombres:
        inicio = time.perf_counter()
        motor = cargar_motor(nombre)
        carga = time.perf_counter() - inicio
        print(f"\n{motor.nombre} cargado en {carga:.1f} s")

        print(f"Corriendo {motor.nombre} sobre {len(archivos)} imágenes...")
        filas = evaluar_motor(motor, archivos)
        todas_las_filas.extend(filas)
        ok = imprimir_resumen(f"=== {motor.nombre} ===", filas)
        tiempo_prom = sum(f["tiempo_seg"] for f in filas) / len(filas)
        memoria = pico_memoria_mb()
        print(f"Tiempo promedio por imagen: {tiempo_prom:.3f} s")
        if memoria is not None:
            print(f"Pico de memoria (Python + subproceso): {memoria:.0f} MB")
        resumen_final.append((motor.nombre, ok, tiempo_prom, carga, memoria))

    print("\n=== Comparación final ===")
    print(f"{'motor':12s} {'aciertos':16s} {'tiempo prom./img':18s} {'carga':8s} {'pico RAM'}")
    for nombre, ok, tiempo_prom, carga, memoria in resumen_final:
        ram = f"{memoria:.0f} MB" if memoria is not None else "-"
        print(f"{nombre:12s} {ok}/{len(archivos)} ({100 * ok / len(archivos):.1f}%)   "
              f"{tiempo_prom:.3f} s            {carga:5.1f} s  {ram}")

    with open(csv_salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "motor", "tamano", "nivel", "archivo", "esperado",
            "leido", "confianza", "corregido", "formato", "ok", "tiempo_seg",
        ])
        w.writeheader()
        w.writerows(todas_las_filas)
    print(f"\nGuardado detalle en {csv_salida.name}")


if __name__ == "__main__":
    main()
