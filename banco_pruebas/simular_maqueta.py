"""Simulacro de punta a punta sobre las fotos del prototipo de maqueta.

Las escenas (e1, e2, ...) se recorren en orden. Comparando cada escena con la
anterior se deducen los eventos que mandaría el ESP32 (plaza ocupada / libre),
y cada uno se procesa con el pipeline completo: captura (las 3 tomas de la
escena como cuadros sucesivos) -> recorte -> OCR -> votación -> SQLite.
Después de cada escena se verifica que la base coincida con lo que hay en la
foto y que el tótem encuentre cada patente.

Uso: python simular_maqueta.py
Base de prueba: simulacion_maqueta.db (se borra al empezar).
"""

import statistics

from banco import BASE_DIR
from base_datos import BaseDatos
from captura import FuenteCarpeta
from motores.motor_tesseract import MotorTesseract
from pipeline import Pipeline
from recorte import cargar_plazas

DIR_FOTOS = BASE_DIR / "imagenes" / "maqueta"
RUTA_BASE = BASE_DIR / "simulacion_maqueta.db"
VACIA = "VACIA"


def escenas():
    """[(escena, {plaza: patente o VACIA})] en orden."""
    vistas = {}
    for ruta in sorted(DIR_FOTOS.glob("*.jpg")):
        nombre, *patentes = ruta.stem.split("_")
        vistas[nombre[:-1]] = {str(i): p for i, p in enumerate(patentes, 1)}
    return sorted(vistas.items())


def main():
    for sufijo in ("", "-wal", "-shm"):
        RUTA_BASE.with_name(RUTA_BASE.name + sufijo).unlink(missing_ok=True)
    base = BaseDatos(RUTA_BASE)
    motor = MotorTesseract()
    resolucion, plazas = cargar_plazas(DIR_FOTOS / "plazas.json")

    anterior = {plaza: VACIA for plaza in plazas}
    lecturas, errores = [], 0
    for escena, actual in escenas():
        print(f"\n== {escena}: plaza 1 {actual['1']}, plaza 2 {actual['2']}")
        with FuenteCarpeta(DIR_FOTOS, patron=f"{escena}?_*.jpg", repetir=True) as fuente:
            pipeline = Pipeline(fuente, motor, plazas, resolucion, base)
            # Primero las salidas, después las entradas (como llegarían del ESP32).
            for plaza in sorted(plazas):
                if anterior[plaza] != VACIA and actual[plaza] == VACIA:
                    pipeline.procesar_libre(plaza)
                    print(f"   plaza {plaza} libre (sale {anterior[plaza]})")
            for plaza in sorted(plazas):
                if anterior[plaza] == VACIA and actual[plaza] != VACIA:
                    lectura = pipeline.procesar_ocupada(plaza)
                    lecturas.append(lectura)
                    marca = "OK" if lectura.patente == actual[plaza] else "ERROR"
                    errores += marca != "OK"
                    print(f"   plaza {plaza} ocupada: {lectura.patente or 'sin leer':8s} "
                          f"({lectura.votos}/{lectura.capturas} votos, lecturas {lectura.crudas}, "
                          f"{lectura.tiempos_ms['total']:.0f} ms) {marca}")

        # La base tiene que coincidir con la foto, y el tótem encontrar cada auto.
        en_base = {fila["plaza"]: fila["patente"] for fila in base.ocupacion()}
        esperado = {p: patente for p, patente in actual.items() if patente != VACIA}
        coincide = en_base == esperado
        errores += not coincide
        print(f"   base: {en_base} {'coincide' if coincide else 'NO COINCIDE con ' + str(esperado)}")
        for plaza, patente in esperado.items():
            encontrada = base.buscar_patente(patente)
            ok = encontrada is not None and encontrada["plaza"] == plaza
            errores += not ok
            print(f"   tótem busca {patente}: {'plaza ' + encontrada['plaza'] if encontrada else 'NO ENCONTRADA'}")
        anterior = actual

    print(f"\nEventos de entrada: {len(lecturas)}, errores: {errores}")
    if lecturas:
        print("Latencia por entrada (ms): " + ", ".join(
            f"{etapa} {statistics.median(l.tiempos_ms[etapa] for l in lecturas):.0f}"
            for etapa in ("captura", "recorte", "ocr", "total")) + " (medianas)")
    base.cerrar()


if __name__ == "__main__":
    main()
