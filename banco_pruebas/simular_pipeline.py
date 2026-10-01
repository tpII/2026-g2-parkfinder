"""Simula eventos de plaza sobre las fotos de la notebook y pasa cada uno por
el pipeline completo (captura -> recorte -> OCR -> votación -> SQLite).

Por cada escena (distancia): entran los dos autos (plaza 1 y 2), el tótem
busca cada patente, y salen. Las capturas alternan entre las tomas de esa
escena (d30, d30b, d30, ...), como cuadros distintos de una cámara fija con
los autos quietos.

Uso: python simular_pipeline.py [--capturas 3]
Base de prueba: simulacion.db (se borra al empezar).
"""

import argparse
import json
import statistics

from banco import BASE_DIR
from base_datos import BaseDatos
from captura import FuenteCarpeta
from motores.motor_tesseract import MotorTesseract
from pipeline import Pipeline

DIR_FOTOS = BASE_DIR / "imagenes" / "notebook"
RUTA_BASE = BASE_DIR / "simulacion.db"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capturas", type=int, default=3)
    args = parser.parse_args()

    for sufijo in ("", "-wal", "-shm"):
        RUTA_BASE.with_name(RUTA_BASE.name + sufijo).unlink(missing_ok=True)
    base = BaseDatos(RUTA_BASE)
    motor = MotorTesseract()
    with open(DIR_FOTOS / "plazas.json", encoding="utf-8") as f:
        config = json.load(f)

    lecturas, aciertos_totem = [], 0
    # Escena = nombre sin la "b" de la segunda toma (d30 y d30b son la misma escena).
    escenas = sorted({r.stem.split("_")[0].rstrip("b"): r for r in DIR_FOTOS.glob("*.jpg")}.items())
    for foto, ruta in escenas:
        _, *esperadas = ruta.stem.split("_")
        plazas = config[foto]["plazas"]
        with FuenteCarpeta(DIR_FOTOS, patron=f"{foto}*.jpg", repetir=True) as fuente:
            pipeline = Pipeline(fuente, motor, plazas, config[foto]["resolucion"], base, args.capturas)
            for plaza, esperado in zip(sorted(plazas), esperadas):
                lectura = pipeline.procesar_ocupada(plaza)
                lecturas.append(lectura)
                print(f"{foto} entra a plaza {plaza}: {lectura.patente or 'sin leer':8s} "
                      f"(esperado {esperado}, {lectura.votos}/{lectura.capturas} votos, "
                      f"lecturas {lectura.crudas}) total {lectura.tiempos_ms['total']:.0f} ms")

            for esperado in esperadas:
                encontrada = base.buscar_patente(esperado)
                aciertos_totem += encontrada is not None
                donde = f"plaza {encontrada['plaza']} desde {encontrada['ingreso']}" if encontrada else "NO ENCONTRADA"
                print(f"   tótem busca {esperado}: {donde}")
            print(f"   ocupación: {[dict(r) for r in base.ocupacion()]}")

            # Salida simulada de los autos (en el sistema real la avisa el ESP32
            # por MQTT): deja las plazas vacías para la foto siguiente.
            for plaza in sorted(plazas):
                pipeline.procesar_libre(plaza)

    print(f"\nEl tótem encontró {aciertos_totem}/{len(lecturas)} patentes")
    print("Latencia por evento de entrada (ms):")
    for etapa in ("captura", "recorte", "ocr", "total"):
        valores = [l.tiempos_ms[etapa] for l in lecturas]
        print(f"  {etapa:8s} mediana {statistics.median(valores):7.1f}   máx {max(valores):7.1f}")
    print(f"Plazas ocupadas al final: {len(base.ocupacion())} "
          "(deberían ser 0: el script simula la salida de cada auto)")
    base.cerrar()


if __name__ == "__main__":
    main()
