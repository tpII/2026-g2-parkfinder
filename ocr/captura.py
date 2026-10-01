"""Fuentes de imagen intercambiables: el resto del sistema pide una imagen sin
saber si viene de la cámara o de una carpeta de fotos. La carpeta permite
probar el pipeline sin hardware y con bancos de fotos reales.

Prueba manual:
  python captura.py --camara 0 --guardar foto.jpg
  python captura.py --carpeta ../banco_pruebas/imagenes/fuente --n 3
"""

import argparse
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

import cv2


class ErrorCaptura(RuntimeError):
    pass


class FuenteImagen(ABC):
    nombre = "fuente"

    @abstractmethod
    def capturar(self):
        """Devuelve una imagen BGR. Lanza ErrorCaptura si no hay imagen."""
        raise NotImplementedError

    def capturar_varias(self, n):
        """n imágenes seguidas, para leer varias y quedarse con la más repetida."""
        return [self.capturar() for _ in range(n)]

    def cerrar(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cerrar()


class FuenteCamara(FuenteImagen):
    """Webcam UVC. Se abre una sola vez (abrir tarda ~1-2 s) y se lee por
    evento. En Windows usa DirectShow: con Media Foundation la lectura se
    colgaba 60 s en la PC de desarrollo."""

    nombre = "camara"

    def __init__(self, indice=0, ancho=1280, alto=720, formato="MJPG",
                 calentamiento=10, descarte=2):
        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_V4L2
        self._cap = cv2.VideoCapture(indice, backend)
        if not self._cap.isOpened():
            raise ErrorCaptura(f"no se pudo abrir la cámara {indice}")
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*formato))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._descarte = descarte

        # Los primeros cuadros salen oscuros mientras ajusta la exposición. Si
        # el primero ya falla, la cámara no entrega imagen: cortar acá en vez
        # de esperar el timeout de V4L2 (10 s) en cada uno.
        for _ in range(calentamiento):
            ok, _ = self._cap.read()
            if not ok:
                self._cap.release()
                raise ErrorCaptura(f"la cámara {indice} abre pero no entrega cuadros")
        self.resolucion = (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                           int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def capturar(self):
        # La cámara sigue capturando aunque nadie lea: sin descartar lo que
        # quedó en el buffer, la foto puede ser de antes del evento.
        for _ in range(self._descarte):
            self._cap.grab()
        ok, imagen = self._cap.read()
        if not ok or imagen is None:
            raise ErrorCaptura("la cámara no entregó imagen")
        return imagen

    def cerrar(self):
        self._cap.release()


class FuenteCarpeta(FuenteImagen):
    """Devuelve las fotos de una carpeta en orden alfabético, una por captura.
    `ultima_ruta` dice de qué archivo salió la última imagen (para saber qué
    patente esperar al evaluar)."""

    nombre = "carpeta"

    def __init__(self, carpeta, patron="*.jpg", repetir=False):
        self.rutas = sorted(Path(carpeta).glob(patron))
        if not self.rutas:
            raise ErrorCaptura(f"no hay imágenes {patron} en {carpeta}")
        self._repetir = repetir
        self._siguiente = 0
        self.ultima_ruta = None

    def __len__(self):
        return len(self.rutas)

    def capturar(self):
        if self._siguiente >= len(self.rutas):
            if not self._repetir:
                raise ErrorCaptura("no quedan imágenes en la carpeta")
            self._siguiente = 0
        ruta = self.rutas[self._siguiente]
        self._siguiente += 1
        imagen = cv2.imread(str(ruta))
        if imagen is None:
            raise ErrorCaptura(f"no se pudo leer {ruta.name}")
        self.ultima_ruta = ruta
        return imagen


def main():
    parser = argparse.ArgumentParser(description="Prueba manual de una fuente de imagen.")
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--camara", type=int, help="índice de la cámara (0 = la primera)")
    origen.add_argument("--carpeta", help="carpeta con fotos .jpg")
    parser.add_argument("--ancho", type=int, default=1280)
    parser.add_argument("--alto", type=int, default=720)
    parser.add_argument("--formato", default="MJPG", help="MJPG o YUYV")
    parser.add_argument("--n", type=int, default=1, help="cantidad de capturas")
    parser.add_argument("--guardar", help="guardar la última captura en este archivo")
    args = parser.parse_args()

    inicio = time.perf_counter()
    if args.camara is not None:
        fuente = FuenteCamara(args.camara, args.ancho, args.alto, args.formato)
        print(f"cámara {args.camara} abierta en {time.perf_counter() - inicio:.1f} s, "
              f"resolución {fuente.resolucion[0]}x{fuente.resolucion[1]}")
    else:
        fuente = FuenteCarpeta(args.carpeta)
        print(f"carpeta con {len(fuente)} imágenes")

    with fuente:
        for i in range(1, args.n + 1):
            inicio = time.perf_counter()
            imagen = fuente.capturar()
            brillo = imagen.mean()
            origen = f" ({fuente.ultima_ruta.name})" if isinstance(fuente, FuenteCarpeta) else ""
            aviso = "  <- casi negra: ¿la cámara entrega imagen?" if brillo < 5 else ""
            print(f"captura {i}: {imagen.shape[1]}x{imagen.shape[0]}, "
                  f"{1000 * (time.perf_counter() - inicio):.0f} ms, brillo {brillo:.0f}{origen}{aviso}")
        if args.guardar:
            cv2.imwrite(args.guardar, imagen)
            print(f"guardada en {args.guardar}")


if __name__ == "__main__":
    try:
        main()
    except ErrorCaptura as e:
        raise SystemExit(f"Error de captura: {e}")
