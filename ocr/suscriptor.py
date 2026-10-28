"""Servicio de la unidad central: escucha por MQTT los avisos de ocupación que
publica el ESP32 y ejecuta el pipeline.

Tópicos (acordados con el equipo del ESP32):
  parkfinder/plaza/<n>  ->  "ocupada" | "libre"
  plaza 1 = izquierda vista desde la cámara, plaza 2 = derecha.

Los avisos se encolan y se atienden de a uno en el hilo principal: hay una sola
cámara, y una lectura (~1.7 s en la Pi) no debe trabar el hilo de red de MQTT.
Un aviso que no cambia el estado conocido de la plaza (p. ej. el ESP32 repite
"ocupada" al reconectarse) se ignora, para no duplicar estadías.

Uso:
  python suscriptor.py --camara 0 --plazas plazas.json
  python suscriptor.py --carpeta FOTOS --patron "d30*.jpg" --plazas plazas.json   (sin cámara)
"""

import argparse
import logging
import queue
import time

import cv2
import numpy as np
import paho.mqtt.client as mqtt

from base_datos import BaseDatos
from captura import FuenteCamara, FuenteCarpeta
from motores.motor_tesseract import MotorTesseract
from pipeline import BASE_POR_DEFECTO, Pipeline, esperar_reloj
from recorte import cargar_plazas

PREFIJO = "parkfinder/plaza/"
ESTADOS = {"ocupada", "libre"}

log = logging.getLogger("parkfinder")


def calentar_motor(motor):
    """Lectura de práctica al arrancar: la primera llamada a Tesseract carga el
    modelo y tarda ~0.8 s más; así no la paga el primer auto que entra."""
    imagen = np.full((90, 330, 3), 255, np.uint8)
    cv2.putText(imagen, "ABC123", (12, 68), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 5)
    inicio = time.perf_counter()
    motor.leer(imagen)
    return time.perf_counter() - inicio


def interpretar(topico, contenido):
    """(plaza, estado) de un mensaje, o None si no respeta el formato acordado."""
    if not topico.startswith(PREFIJO):
        return None
    plaza = topico[len(PREFIJO):]
    estado = contenido.strip().lower()
    if not plaza or "/" in plaza or estado not in ESTADOS:
        return None
    return plaza, estado


class Servicio:
    def __init__(self, pipeline, espera_captura):
        self.pipeline = pipeline
        self.espera_captura = espera_captura
        self.eventos = queue.Queue()
        # Estado de partida desde la base: si la Pi se reinicia con un auto
        # estacionado, el "ocupada" que reenvíe el ESP32 no abre otra estadía.
        ocupadas = {fila["plaza"] for fila in pipeline.base.ocupacion()}
        self.estado = {p: "ocupada" if p in ocupadas else "libre" for p in pipeline.plazas}

    # --- Callbacks de MQTT (hilo de red): solo encolan ---

    def al_conectar(self, cliente, _datos, _flags, codigo, _propiedades):
        if codigo.is_failure:
            log.error("el broker rechazó la conexión: %s", codigo)
            return
        # Se suscribe en cada (re)conexión.
        cliente.subscribe(PREFIJO + "+", qos=1)
        log.info("conectado al broker, suscripto a %s+", PREFIJO)

    def al_desconectar(self, _cliente, _datos, _flags, codigo, _propiedades):
        log.warning("desconectado del broker (%s), reintentando", codigo)

    def al_recibir(self, _cliente, _datos, mensaje):
        contenido = mensaje.payload.decode("utf-8", errors="replace")
        if not contenido:
            return  # mensaje vacío: se borró el estado retenido del tópico, no es un aviso
        evento = interpretar(mensaje.topic, contenido)
        if evento is None:
            log.warning("mensaje con formato inválido, ignorado: %s %r", mensaje.topic, contenido)
            return
        self.eventos.put((*evento, time.perf_counter()))

    # --- Atención de eventos (hilo principal) ---

    def atender(self, plaza, estado, recibido):
        if plaza not in self.estado:
            log.warning("aviso de una plaza no configurada: %s", plaza)
            return
        if self.estado[plaza] == estado:
            log.info("plaza %s ya estaba %s: aviso repetido, ignorado", plaza, estado)
            return

        if estado == "ocupada":
            # Espera opcional antes de capturar. Con el ESP32 no hace falta: ya
            # confirma 1,5 s con el auto quieto antes de avisar.
            time.sleep(self.espera_captura)
            lectura = self.pipeline.procesar_ocupada(plaza)
            # El texto crudo solo se muestra si la corrección por posición cambió algo.
            crudo = "" if lectura.textos_ocr == lectura.crudas else f", OCR crudo {lectura.textos_ocr}"
            log.info("plaza %s ocupada: %s (%d/%d votos, lecturas %s%s, OCR %.0f ms) "
                     "%.2f s desde el aviso",
                     plaza, lectura.patente or "patente sin leer", lectura.votos,
                     lectura.capturas, lectura.crudas, crudo, lectura.tiempos_ms["ocr"],
                     time.perf_counter() - recibido)
        else:
            self.pipeline.procesar_libre(plaza)
            log.info("plaza %s libre", plaza)
        self.estado[plaza] = estado

    def ejecutar(self):
        while True:
            self.atender(*self.eventos.get())


def main():
    parser = argparse.ArgumentParser(description="Servicio MQTT de ParkFinder.")
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--camara", type=int, help="índice de la cámara")
    origen.add_argument("--carpeta", help="carpeta con fotos (prueba sin cámara)")
    parser.add_argument("--patron", default="*.jpg", help="fotos de --carpeta a usar")
    parser.add_argument("--plazas", required=True, help="JSON de plazas (formato de recorte.py)")
    parser.add_argument("--base", default=str(BASE_POR_DEFECTO), help="archivo SQLite")
    parser.add_argument("--capturas", type=int, default=3)
    parser.add_argument("--espera-captura", type=float, default=0.0,
                        help="segundos entre el aviso de ocupada y la captura "
                             "(el ESP32 ya confirma 1,5 s antes de avisar)")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--puerto", type=int, default=1883)
    parser.add_argument("--sin-esperar-reloj", action="store_true",
                        help="no verificar la hora por NTP o RTC (solo para pruebas)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.sin_esperar_reloj and not esperar_reloj():
        raise SystemExit("La hora no es confiable (ni NTP ni RTC): no se registra con hora falsa.")

    resolucion, plazas = cargar_plazas(args.plazas)
    base = BaseDatos(args.base)
    if args.camara is not None:
        fuente = FuenteCamara(args.camara)
    else:
        fuente = FuenteCarpeta(args.carpeta, patron=args.patron, repetir=True)
    motor = MotorTesseract()
    log.info("lectura de práctica del motor OCR: %.2f s", calentar_motor(motor))
    pipeline = Pipeline(fuente, motor, plazas, resolucion, base, args.capturas)
    servicio = Servicio(pipeline, args.espera_captura)
    log.info("plazas %s, estado inicial %s", ", ".join(plazas), servicio.estado)

    # Sesión limpia: al (re)conectarse, el estado de cada plaza llega por su
    # mensaje retenido, que es el último y el real. Con sesión persistente el
    # broker guardaba todos los avisos mientras el servicio estaba apagado y
    # los entregaba juntos al volver: cada "ocupada" viejo disparaba una
    # captura de la escena actual y abría estadías falsas (prueba del 09/10).
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="parkfinder-pi",
                          clean_session=True)
    cliente.on_connect = servicio.al_conectar
    cliente.on_disconnect = servicio.al_desconectar
    cliente.on_message = servicio.al_recibir
    cliente.reconnect_delay_set(min_delay=1, max_delay=30)
    cliente.connect_async(args.broker, args.puerto, keepalive=30)
    cliente.loop_start()

    try:
        servicio.ejecutar()
    except KeyboardInterrupt:
        log.info("detenido")
    finally:
        cliente.loop_stop()
        cliente.disconnect()
        fuente.cerrar()
        base.cerrar()


if __name__ == "__main__":
    main()
