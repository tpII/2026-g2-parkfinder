"""Servicio de la unidad central: escucha por MQTT los avisos de ocupación que
publica el ESP32 y ejecuta el pipeline.

Tópicos (acordados con el equipo del ESP32):
  parkfinder/plaza/<n>     ->  "ocupada" | "libre"
  plaza 1 = izquierda vista desde la cámara, plaza 2 = derecha.
  parkfinder/esp32/estado  ->  "conectado" | "desconectado"
  "desconectado" es la última voluntad del ESP32: la publica el broker si el
  ESP32 deja de responder. Se registra en la base y el tótem lo muestra.

Los avisos se encolan y se atienden de a uno en el hilo principal: hay una sola
cámara, y una lectura (~1.7 s en la Pi) no debe trabar el hilo de red de MQTT.
Un aviso que no cambia el estado conocido de la plaza (p. ej. el ESP32 repite
"ocupada" al reconectarse) se ignora, para no duplicar estadías.

Relectura: si una plaza queda ocupada con la patente sin leer (una mano que
tapaba la patente, un reflejo, lecturas sin consenso), se vuelve a leer cada
`relectura_intervalo` segundos, hasta `relectura_intentos` veces, mientras no
haya avisos en espera. Si se lee, se completa la estadía abierta sin cambiar
su hora de ingreso; si la plaza se libera, se deja de releer.

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
from pipeline import BASE_POR_DEFECTO, Pipeline, ahora, esperar_reloj
from recorte import cargar_plazas

PREFIJO = "parkfinder/plaza/"
ESTADOS = {"ocupada", "libre"}
TEMA_CONEXION = "parkfinder/esp32/estado"
ESTADOS_CONEXION = {"conectado", "desconectado"}
CONEXION = "conexion"  # primer elemento de los eventos de conexión en la cola

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
    def __init__(self, pipeline, espera_captura, relectura_intervalo=10.0, relectura_intentos=6):
        self.pipeline = pipeline
        self.espera_captura = espera_captura
        self.relectura_intervalo = relectura_intervalo
        self.relectura_intentos = relectura_intentos
        self.eventos = queue.Queue()
        # Estado de partida desde la base: si la Pi se reinicia con un auto
        # estacionado, el "ocupada" que reenvíe el ESP32 no abre otra estadía.
        abiertas = pipeline.base.ocupacion()
        ocupadas = {fila["plaza"] for fila in abiertas}
        self.estado = {p: "ocupada" if p in ocupadas else "libre" for p in pipeline.plazas}
        # plaza -> {"intentos": n, "proximo": momento de time.monotonic()}
        self.pendientes = {}
        for fila in abiertas:
            if fila["patente"] is None and fila["plaza"] in self.estado:
                self.agendar_relectura(fila["plaza"])

    # --- Callbacks de MQTT (hilo de red): solo encolan ---

    def al_conectar(self, cliente, _datos, _flags, codigo, _propiedades):
        if codigo.is_failure:
            log.error("el broker rechazó la conexión: %s", codigo)
            return
        # Se suscribe en cada (re)conexión.
        cliente.subscribe([(PREFIJO + "+", 1), (TEMA_CONEXION, 1)])
        log.info("conectado al broker, suscripto a %s+ y %s", PREFIJO, TEMA_CONEXION)

    def al_desconectar(self, _cliente, _datos, _flags, codigo, _propiedades):
        log.warning("desconectado del broker (%s), reintentando", codigo)

    def al_recibir(self, _cliente, _datos, mensaje):
        contenido = mensaje.payload.decode("utf-8", errors="replace")
        if not contenido:
            return  # mensaje vacío: se borró el estado retenido del tópico, no es un aviso
        if mensaje.topic == TEMA_CONEXION:
            estado = contenido.strip().lower()
            if estado in ESTADOS_CONEXION:
                self.eventos.put((CONEXION, estado, time.perf_counter()))
            else:
                log.warning("estado de conexión inválido, ignorado: %r", contenido)
            return
        evento = interpretar(mensaje.topic, contenido)
        if evento is None:
            log.warning("mensaje con formato inválido, ignorado: %s %r", mensaje.topic, contenido)
            return
        self.eventos.put((*evento, time.perf_counter()))

    # --- Atención de eventos (hilo principal) ---

    def atender(self, plaza, estado, recibido):
        if plaza == CONEXION:
            self.atender_conexion(estado)
            return
        if plaza not in self.estado:
            log.warning("aviso de una plaza no configurada: %s", plaza)
            return
        if self.estado[plaza] == estado:
            log.info("plaza %s ya estaba %s: aviso repetido, ignorado", plaza, estado)
            return

        if estado == "ocupada":
            # Espera antes de capturar: el ESP32 confirma 1,5 s con el auto
            # quieto, pero en la maqueta la mano puede seguir tapando la
            # patente después de apoyar la caja (prueba del 03/11).
            time.sleep(self.espera_captura)
            lectura = self.pipeline.procesar_ocupada(plaza)
            # El texto crudo solo se muestra si la corrección por posición cambió algo.
            crudo = "" if lectura.textos_ocr == lectura.crudas else f", OCR crudo {lectura.textos_ocr}"
            if lectura.patente:
                resultado = lectura.patente
            elif lectura.candidata:
                resultado = f"patente sin leer (sin consenso: {lectura.candidata})"
            else:
                resultado = "patente sin leer"
            log.info("plaza %s ocupada: %s (%d/%d votos, lecturas %s%s, OCR %.0f ms) "
                     "%.2f s desde el aviso",
                     plaza, resultado, lectura.votos,
                     lectura.capturas, lectura.crudas, crudo, lectura.tiempos_ms["ocr"],
                     time.perf_counter() - recibido)
            if not lectura.patente:
                self.agendar_relectura(plaza)
        else:
            self.pipeline.procesar_libre(plaza)
            if self.pendientes.pop(plaza, None):
                log.info("plaza %s libre (se deja de releer)", plaza)
            else:
                log.info("plaza %s libre", plaza)
        self.estado[plaza] = estado

    def atender_conexion(self, estado):
        if not self.pipeline.base.registrar_conexion(estado, ahora()):
            return  # el mismo estado que ya estaba registrado
        if estado == "desconectado":
            log.warning("ESP32 desconectado: el estado de las plazas puede no estar al día")
        else:
            log.info("ESP32 conectado")

    # --- Relectura de plazas ocupadas sin patente ---

    def agendar_relectura(self, plaza):
        if self.relectura_intentos > 0:
            self.pendientes[plaza] = {"intentos": 0,
                                      "proximo": time.monotonic() + self.relectura_intervalo}

    def espera_hasta_relectura(self):
        """Segundos hasta la próxima relectura (None si no hay ninguna pendiente)."""
        if not self.pendientes:
            return None
        proximo = min(p["proximo"] for p in self.pendientes.values())
        return max(0.0, proximo - time.monotonic())

    def releer_pendientes(self):
        for plaza in sorted(self.pendientes):
            if not self.eventos.empty():
                return  # los avisos del ESP32 tienen prioridad
            pendiente = self.pendientes[plaza]
            if pendiente["proximo"] > time.monotonic():
                continue
            pendiente["intentos"] += 1
            lectura, completada = self.pipeline.releer_plaza(plaza)
            intento = f"{pendiente['intentos']}/{self.relectura_intentos}"
            if completada:
                log.info("plaza %s relectura %s: %s (%d/%d votos, lecturas %s)", plaza, intento,
                         lectura.patente, lectura.votos, lectura.capturas, lectura.crudas)
                del self.pendientes[plaza]
            elif lectura.patente:
                # Ya no hay una estadía abierta sin patente en esa plaza.
                log.warning("plaza %s relectura %s: %s, pero la plaza ya no espera patente",
                            plaza, intento, lectura.patente)
                del self.pendientes[plaza]
            elif pendiente["intentos"] >= self.relectura_intentos:
                log.warning("plaza %s relectura %s: sin leer (lecturas %s); se deja de releer",
                            plaza, intento, lectura.crudas)
                del self.pendientes[plaza]
            else:
                log.info("plaza %s relectura %s: sin leer (lecturas %s)",
                         plaza, intento, lectura.crudas)
                pendiente["proximo"] = time.monotonic() + self.relectura_intervalo

    def ejecutar(self):
        while True:
            try:
                evento = self.eventos.get(timeout=self.espera_hasta_relectura())
            except queue.Empty:
                self.releer_pendientes()
            else:
                self.atender(*evento)


def main():
    parser = argparse.ArgumentParser(description="Servicio MQTT de ParkFinder.")
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument("--camara", type=int, help="índice de la cámara")
    origen.add_argument("--carpeta", help="carpeta con fotos (prueba sin cámara)")
    parser.add_argument("--patron", default="*.jpg", help="fotos de --carpeta a usar")
    parser.add_argument("--plazas", required=True, help="JSON de plazas (formato de recorte.py)")
    parser.add_argument("--base", default=str(BASE_POR_DEFECTO), help="archivo SQLite")
    parser.add_argument("--capturas", type=int, default=3)
    parser.add_argument("--votos-minimos", type=int, default=2,
                        help="capturas que deben coincidir para registrar la patente")
    parser.add_argument("--espera-captura", type=float, default=0.0,
                        help="segundos entre el aviso de ocupada y la captura "
                             "(el servicio usa 1 s; el ESP32 ya confirma 1,5 s antes de avisar)")
    parser.add_argument("--relectura-intervalo", type=float, default=10.0,
                        help="segundos entre relecturas de una plaza ocupada sin patente")
    parser.add_argument("--relectura-intentos", type=int, default=6,
                        help="relecturas por plaza antes de dejarla sin patente (0 = no releer)")
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
        # En la resolución de calibración de las zonas: la C270 en 720p
        # recorta el cuadro (no lo escala) y las zonas quedarían corridas.
        fuente = FuenteCamara(args.camara, ancho=resolucion[0], alto=resolucion[1])
        if fuente.resolucion != tuple(resolucion):
            log.warning("la cámara entrega %s y las zonas son de %s; se escalan",
                        fuente.resolucion, tuple(resolucion))
    else:
        fuente = FuenteCarpeta(args.carpeta, patron=args.patron, repetir=True)
    motor = MotorTesseract()
    log.info("lectura de práctica del motor OCR: %.2f s", calentar_motor(motor))
    pipeline = Pipeline(fuente, motor, plazas, resolucion, base, args.capturas, args.votos_minimos)
    servicio = Servicio(pipeline, args.espera_captura,
                        args.relectura_intervalo, args.relectura_intentos)
    log.info("plazas %s, estado inicial %s", ", ".join(plazas), servicio.estado)
    if servicio.pendientes:
        log.info("plazas ocupadas sin patente, se van a releer: %s", ", ".join(servicio.pendientes))

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
