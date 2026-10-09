"""Verificación de las zonas de las plazas después de mover o reubicar la
cámara: toma una captura, busca la patente dentro de la zona de cada plaza y
dice si la patente quedó bien adentro, al borde o fuera de la zona.

Deja una imagen con las zonas (azul) y la patente encontrada (rojo, verde si
la lectura es válida) para revisarla a ojo.

Con las dos plazas ocupadas, todo está bien si cada plaza da "OK". Si da
"AL BORDE" o "SIN PATENTE", mover la cámara (o corregir config/plazas.json) y
repetir. Con --continuo repite cada pocos segundos mientras se acomoda.

Uso (en la Pi, desde ~/parkfinder/ocr):
  ../venv/bin/python verificar_zonas.py
  ../venv/bin/python verificar_zonas.py --continuo
  python verificar_zonas.py --imagen foto.jpg        (sin cámara)
"""

import argparse
import time
from pathlib import Path

import cv2

from captura import ErrorCaptura, FuenteCamara
from motores.motor_tesseract import MotorTesseract
from postproceso import leer_patente
from recorte import cargar_plazas, escalar_zona, localizar_patente

RAIZ = Path(__file__).resolve().parent.parent
PLAZAS = RAIZ / "config" / "plazas.json"
SALIDA = RAIZ / "verificacion_zonas.jpg"

# Margen mínimo entre la patente y el borde de la zona, en alturas del
# recuadro rojo: menos que esto y un auto un poco corrido ya queda afuera.
MARGEN_MIN = 0.3

AZUL, ROJO, VERDE = (255, 0, 0), (0, 0, 255), (0, 170, 0)


def verificar_plaza(imagen, zona, motor):
    """(estado, detalle, caja en coordenadas de la imagen o None, color)."""
    x, y, w, h = zona
    caja = localizar_patente(imagen[y:y + h, x:x + w])
    if caja is None:
        return ("SIN PATENTE", "no se encontró una fila de caracteres en la zona "
                "(¿plaza vacía, patente fuera de la zona o mal iluminada?)", None, ROJO)

    x0, y0, x1, y1 = caja
    texto, _ = motor.leer(imagen[y + y0:y + y1, x + x0:x + x1])
    patente, formato = leer_patente(texto)
    lectura = f"{patente} ({formato})" if patente else f"'{texto}' inválida"

    margenes = {"izquierdo": x0, "derecho": w - x1, "superior": y0, "inferior": h - y1}
    justos = [lado for lado, m in margenes.items() if m < MARGEN_MIN * (y1 - y0)]
    detalle = f"lectura {lectura}; margen " + ", ".join(
        f"{lado} {m} px" for lado, m in margenes.items())
    caja_img = (x + x0, y + y0, x + x1, y + y1)
    color = VERDE if patente else ROJO

    if justos:
        return ("AL BORDE", f"{detalle} -> la patente está pegada al borde "
                f"{' y '.join(justos)} de la zona", caja_img, color)
    if not patente:
        return ("NO LEE", f"{detalle} -> la zona está bien pero la lectura no es "
                "válida (revisar foco, luz o distancia)", caja_img, color)
    return "OK", detalle, caja_img, color


def verificar(imagen, plazas, resolucion, motor):
    """Imprime el resultado de cada plaza, guarda la imagen anotada y devuelve
    True si todas dieron OK."""
    anotada = imagen.copy()
    todo_ok = True
    for nombre, zona in plazas.items():
        zona = escalar_zona(zona, resolucion, imagen)
        estado, detalle, caja, color = verificar_plaza(imagen, zona, motor)
        todo_ok &= estado == "OK"
        print(f"  plaza {nombre}: {estado:11s} {detalle}")

        x, y, w, h = zona
        cv2.rectangle(anotada, (x, y), (x + w, y + h), AZUL, 3)
        cv2.putText(anotada, f"plaza {nombre}: {estado}", (x + 8, max(30, y - 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, AZUL, 2)
        if caja is not None:
            cv2.rectangle(anotada, caja[:2], caja[2:], color, 3)
    cv2.imwrite(str(SALIDA), anotada)
    return todo_ok


def main():
    parser = argparse.ArgumentParser(description="Verifica las zonas de las plazas.")
    parser.add_argument("--plazas", default=str(PLAZAS))
    parser.add_argument("--camara", type=int, default=0)
    parser.add_argument("--imagen", help="verificar una foto en vez de capturar")
    parser.add_argument("--continuo", action="store_true",
                        help="repetir hasta Ctrl+C (para acomodar la cámara)")
    parser.add_argument("--cada", type=float, default=3.0, help="segundos entre pasadas")
    args = parser.parse_args()

    resolucion, plazas = cargar_plazas(args.plazas)
    motor = MotorTesseract()
    if args.imagen:
        imagen = cv2.imread(args.imagen)
        if imagen is None:
            raise SystemExit(f"no se pudo abrir {args.imagen}")
        todo_ok = verificar(imagen, plazas, resolucion, motor)
        print(f"Imagen anotada: {SALIDA}")
        raise SystemExit(0 if todo_ok else 1)

    try:
        fuente = FuenteCamara(args.camara, ancho=resolucion[0], alto=resolucion[1])
    except ErrorCaptura as e:
        raise SystemExit(f"{e}: ¿la cámara está conectada? (enchufarla después de que arranque la Pi)")
    if fuente.resolucion != tuple(resolucion):
        print(f"Aviso: la cámara entrega {fuente.resolucion} y las zonas son de "
              f"{tuple(resolucion)}; se escalan.")
    try:
        while True:
            print(time.strftime("%H:%M:%S"))
            todo_ok = verificar(fuente.capturar(), plazas, resolucion, motor)
            print("  => " + ("TODO OK" if todo_ok else "REVISAR") + f"  (imagen: {SALIDA})")
            if not args.continuo:
                break
            time.sleep(args.cada)
    except KeyboardInterrupt:
        pass
    finally:
        fuente.cerrar()
    raise SystemExit(0 if todo_ok else 1)


if __name__ == "__main__":
    main()
