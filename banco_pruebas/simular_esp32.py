"""Simula al ESP32: publica avisos de ocupación por MQTT con el formato
acordado (parkfinder/plaza/<n> -> "ocupada" | "libre"), para probar el
suscriptor sin el hardware.

Escenario: entradas y salidas normales, un aviso repetido, las dos plazas
cambiando casi a la vez, y mensajes inválidos que el suscriptor debe ignorar.

Uso: python simular_esp32.py [--broker localhost] [--pausa 4]
"""

import argparse
import time

import paho.mqtt.client as mqtt

ESCENARIO = [
    # (tópico, contenido, qué se espera del suscriptor)
    ("parkfinder/plaza/1", "ocupada", "entra un auto a la plaza 1: lee y registra"),
    ("parkfinder/plaza/1", "ocupada", "aviso repetido: se ignora"),
    ("parkfinder/plaza/2", "ocupada", "entra un auto a la plaza 2: lee y registra"),
    ("parkfinder/plaza/1", "libre", "sale el de la plaza 1"),
    ("parkfinder/plaza/1", "ocupada", "entra otro a la 1, casi junto con..."),
    ("parkfinder/plaza/2", "libre", "...la salida de la 2: se atienden en orden"),
    ("parkfinder/plaza/9", "ocupada", "plaza no configurada: se ignora"),
    ("parkfinder/plaza/1", "abierta", "contenido inválido: se ignora"),
    ("parkfinder/plaza/1", "libre", "sale el de la plaza 1: quedan las dos libres"),
]
SIN_PAUSA = {4}  # índices que se publican inmediatamente después del anterior


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--puerto", type=int, default=1883)
    parser.add_argument("--pausa", type=float, default=4.0,
                        help="segundos entre avisos (la lectura tarda ~1.7 s más la espera de captura)")
    args = parser.parse_args()

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="simulador-esp32")
    cliente.connect(args.broker, args.puerto)
    cliente.loop_start()

    for i, (topico, contenido, nota) in enumerate(ESCENARIO):
        if i and i not in SIN_PAUSA:
            time.sleep(args.pausa)
        # retain=False en la simulación para no dejar estado guardado en el broker.
        cliente.publish(topico, contenido, qos=1).wait_for_publish()
        print(f"{time.strftime('%H:%M:%S')}  {topico} -> {contenido:8s} ({nota})", flush=True)

    cliente.loop_stop()
    cliente.disconnect()


if __name__ == "__main__":
    main()
