"""Orquestador: ante un evento de plaza ocupada captura, recorta la plaza,
lee con el motor OCR y registra la estadía en SQLite; ante plaza libre la
cierra.

Se leen hasta `capturas` imágenes por evento y gana la lectura válida más
repetida (la confianza de Tesseract no sirve: con --psm 8 + lista blanca da
0). Si una lectura ya tiene mayoría se corta antes.

Prueba manual (sin cámara, con una foto y un JSON de plazas de recorte.py):
  python pipeline.py --carpeta FOTOS --plazas plazas.json --plaza 1
  python pipeline.py --carpeta FOTOS --plazas plazas.json --plaza 1 --libre
"""

import os

# Antes de que pytesseract lance Tesseract: con un hilo tarda lo mismo que con
# cuatro (0.962 vs 0.969 s/img en la Pi) y deja tres núcleos para MQTT y la web.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

import argparse
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from base_datos import BaseDatos
from captura import FuenteCamara, FuenteCarpeta
from motores.motor_tesseract import MotorTesseract
from postproceso import corregir
from recorte import cargar_plazas, escalar_zona, recortar_plaza
from validacion import validar

RAIZ = Path(__file__).resolve().parent.parent
BASE_POR_DEFECTO = RAIZ / "datos" / "parkfinder.db"


@dataclass
class Lectura:
    plaza: str
    patente: str = None       # None: ninguna captura dio una lectura válida
    formato: str = None
    votos: int = 0
    capturas: int = 0
    crudas: list = field(default_factory=list)   # lectura de cada captura (None = sin patente)
    tiempos_ms: dict = field(default_factory=dict)


def ahora():
    return datetime.now().isoformat(timespec="seconds")


def reloj_sincronizado():
    """La Pi no tiene RTC: tras un corte arranca con la última hora guardada
    hasta que NTP la corrige. En Windows se asume sincronizado."""
    if os.name == "nt":
        return True
    try:
        salida = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                                capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return salida.strip() == "yes"


def esperar_reloj(maximo_seg=120):
    for _ in range(maximo_seg):
        if reloj_sincronizado():
            return True
        time.sleep(1)
    return False


class Pipeline:
    def __init__(self, fuente, motor, plazas, resolucion, base, capturas=3):
        self.fuente = fuente
        self.motor = motor
        self.plazas = plazas
        self.resolucion = resolucion
        self.base = base
        self.capturas = capturas

    def leer_plaza(self, plaza):
        """Captura, recorta y lee la plaza hasta `capturas` veces."""
        tiempos = {"captura": 0.0, "recorte": 0.0, "ocr": 0.0}
        votos = Counter()
        formatos = {}
        lectura = Lectura(plaza=plaza)
        inicio_total = time.perf_counter()

        for _ in range(self.capturas):
            inicio = time.perf_counter()
            imagen = self.fuente.capturar()
            tiempos["captura"] += time.perf_counter() - inicio

            inicio = time.perf_counter()
            zona = escalar_zona(self.plazas[plaza], self.resolucion, imagen)
            recorte = recortar_plaza(imagen, zona)
            tiempos["recorte"] += time.perf_counter() - inicio
            lectura.capturas += 1
            if recorte is None:
                lectura.crudas.append(None)
                continue

            inicio = time.perf_counter()
            texto, _ = self.motor.leer(recorte)
            tiempos["ocr"] += time.perf_counter() - inicio
            patente = corregir(texto)
            lectura.crudas.append(patente)
            formato = validar(patente)
            if formato:
                votos[patente] += 1
                formatos[patente] = formato
                if votos[patente] > self.capturas // 2:
                    break  # ya tiene mayoría: las capturas que faltan no la cambian

        if votos:
            # En empate gana la que apareció primero (Counter conserva el orden).
            lectura.patente, lectura.votos = votos.most_common(1)[0]
            lectura.formato = formatos[lectura.patente]
        tiempos["total"] = time.perf_counter() - inicio_total
        lectura.tiempos_ms = {etapa: round(1000 * t, 1) for etapa, t in tiempos.items()}
        return lectura

    def procesar_ocupada(self, plaza):
        lectura = self.leer_plaza(plaza)
        self.base.registrar_ingreso(lectura, ahora())
        return lectura

    def procesar_libre(self, plaza):
        return self.base.registrar_egreso(plaza, ahora())


def main():
    parser = argparse.ArgumentParser(description="Procesa un evento de plaza.")
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--camara", type=int, help="índice de la cámara")
    origen.add_argument("--carpeta", help="carpeta con fotos (prueba sin cámara)")
    parser.add_argument("--plazas", required=True, help="JSON de plazas (formato de recorte.py)")
    parser.add_argument("--plaza", required=True, help="plaza del evento")
    parser.add_argument("--libre", action="store_true", help="evento de plaza libre (por defecto, ocupada)")
    parser.add_argument("--base", default=str(BASE_POR_DEFECTO), help="archivo SQLite")
    parser.add_argument("--capturas", type=int, default=3)
    parser.add_argument("--sin-esperar-reloj", action="store_true",
                        help="no esperar la sincronización NTP (solo para pruebas)")
    args = parser.parse_args()

    if not args.sin_esperar_reloj and not esperar_reloj():
        raise SystemExit("El reloj no se sincronizó por NTP: no se registra con hora falsa.")

    resolucion, plazas = cargar_plazas(args.plazas)
    if args.plaza not in plazas:
        raise SystemExit(f"Plaza desconocida: {args.plaza} (hay: {', '.join(plazas)})")
    base = BaseDatos(args.base)
    fuente = FuenteCamara(args.camara) if args.camara is not None else FuenteCarpeta(args.carpeta, repetir=True)

    with fuente:
        pipeline = Pipeline(fuente, MotorTesseract(), plazas, resolucion, base, args.capturas)
        if args.libre:
            cerrada = pipeline.procesar_libre(args.plaza)
            print(f"plaza {args.plaza} libre" + ("" if cerrada else " (no tenía estadía abierta)"))
        else:
            lectura = pipeline.procesar_ocupada(args.plaza)
            print(f"plaza {args.plaza} ocupada: {lectura.patente or 'patente sin leer'} "
                  f"({lectura.votos}/{lectura.capturas} votos, lecturas {lectura.crudas}) "
                  f"tiempos {lectura.tiempos_ms} ms")
    base.cerrar()


if __name__ == "__main__":
    main()
