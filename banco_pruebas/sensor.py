"""Simula el aviso de un sensor HC-SR04 del ESP32: publica el estado de una
plaza por MQTT con el formato acordado (parkfinder/plaza/<n> -> "ocupada" |
"libre", QoS 1, retain), para probar el pipeline con la cámara real antes de
tener el ESP32.

Uso (desde la PC, con el venv del proyecto):
  python banco_pruebas/sensor.py 1 ocupada
  python banco_pruebas/sensor.py 2 libre
  python banco_pruebas/sensor.py --limpiar     # borra los estados retenidos del broker
"""

import argparse

import paho.mqtt.client as mqtt

PREFIJO = "parkfinder/plaza/"


def main():
    parser = argparse.ArgumentParser(description="Simula el aviso de un sensor de plaza.")
    parser.add_argument("plaza", nargs="?", help="número de plaza (1 = izquierda vista desde la cámara)")
    parser.add_argument("estado", nargs="?", choices=["ocupada", "libre"])
    parser.add_argument("--limpiar", action="store_true",
                        help="borra los estados retenidos de las plazas 1 y 2 en el broker")
    parser.add_argument("--broker", default="192.168.0.14", help="IP o nombre de la Raspberry Pi")
    parser.add_argument("--puerto", type=int, default=1883)
    args = parser.parse_args()
    if not args.limpiar and not (args.plaza and args.estado):
        parser.error("indicar plaza y estado (por ejemplo: 1 ocupada), o --limpiar")

    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="simulador-sensor")
    cliente.connect(args.broker, args.puerto)
    cliente.loop_start()
    if args.limpiar:
        # Un mensaje vacío con retain borra el estado guardado del tópico.
        for plaza in ("1", "2"):
            cliente.publish(PREFIJO + plaza, "", qos=1, retain=True).wait_for_publish()
        print("estados retenidos borrados (plazas 1 y 2)")
    else:
        cliente.publish(PREFIJO + args.plaza, args.estado, qos=1, retain=True).wait_for_publish()
        print(f"publicado {PREFIJO}{args.plaza} -> {args.estado}")
    cliente.loop_stop()
    cliente.disconnect()


if __name__ == "__main__":
    main()
