"""Utilidades compartidas por los scripts del banco de pruebas. Agrega ../ocr
al path para poder importar el núcleo.

Nombres de archivo: {tamano}_{version}_{PATENTE}[_deg_{nivel}].jpg
"""

import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent / "ocr"))

DIR_FUENTE = BASE_DIR / "imagenes" / "fuente"
DIR_DEGRADADAS = BASE_DIR / "imagenes" / "degradadas"

ORDEN_NIVELES = ["sin_degradar", "leve", "medio", "fuerte"]


def listar_imagenes():
    """Las 144 imágenes del banco: 36 recortes + 108 degradadas."""
    return sorted(DIR_FUENTE.glob("*.jpg")) + sorted(DIR_DEGRADADAS.glob("*.jpg"))


def buscar_archivo(nombre):
    for carpeta in (DIR_FUENTE, DIR_DEGRADADAS):
        ruta = carpeta / nombre
        if ruta.exists():
            return ruta
    raise FileNotFoundError(nombre)


def patente_esperada(stem):
    return stem.split("_")[2]


def nivel_de(stem):
    if "_deg_" in stem:
        return stem.split("_deg_")[1]
    return "sin_degradar"


def tamano_de(stem):
    return stem.split("_")[0]


def imprimir_resumen(titulo, filas, clave_ok="ok"):
    """Imprime aciertos por tamaño y nivel; devuelve el total de aciertos."""
    resumen = defaultdict(lambda: [0, 0])
    for fila in filas:
        clave = (fila["tamano"], fila["nivel"])
        resumen[clave][1] += 1
        resumen[clave][0] += 1 if fila[clave_ok] else 0

    print(f"\n{titulo}")
    print(f"{'tamano':8s} {'nivel':13s} aciertos")
    for (tamano, nivel), (aciertos, total) in sorted(
        resumen.items(), key=lambda kv: (kv[0][0], ORDEN_NIVELES.index(kv[0][1]))
    ):
        print(f"{tamano:8s} {nivel:13s} {aciertos}/{total}")

    total_ok = sum(1 for f in filas if f[clave_ok])
    print(f"TOTAL: {total_ok}/{len(filas)} ({100 * total_ok / len(filas):.1f}%)")
    return total_ok
