// ParkFinder - Comunicación WiFi + MQTT del ESP32
// Biblioteca: MQTT de Joël Gähwiler (256dpi/arduino-mqtt)
//
// Temas:     parkfinder/plaza/1  (izquierda, vista desde la cámara)
//            parkfinder/plaza/2  (derecha)
// Contenido: "ocupada" o "libre"
// Publicación con QoS 1 y retain = true.
//
// Este módulo no depende de sensores: recibe datos simples
// (plaza, ocupada, distancia) y se encarga solo de publicarlos.

#pragma once
#include <Arduino.h>

// ---------- Configuración ----------
// Red WiFi (el ESP32 solo funciona en 2,4 GHz): WIFI_SSID y WIFI_CLAVE se
// definen en credenciales.h, que no se sube al repositorio. Para crearlo,
// copiar credenciales_ejemplo.h como credenciales.h y completar los datos.
#include "credenciales.h"

// Broker: la Raspberry Pi, buscada por nombre (mDNS) y no por IP, porque
// la IP cambia según la red (casa, hotspot de la facultad). Si el nombre
// no se resolviera en alguna red, se puede poner la IP directamente
// (por ejemplo "192.168.0.14"): también funciona.
#define MQTT_BROKER    "parkfinder.local"
#define MQTT_PUERTO    1883
#define MDNS_NOMBRE    "parkfinder-esp32"   // Nombre del ESP32 en la red
#define MQTT_ID        "parkfinder-esp32"   // Debe ser único en el broker

#define TEMA_BASE      "parkfinder/plaza/"  // Se le agrega el número de plaza
#define REINTENTO_MS   5000                 // Espera entre intentos de reconexión
#define MAX_PLAZAS     8                    // Plazas numeradas de 1 a MAX_PLAZAS
// -----------------------------------

// Inicia el WiFi y configura el cliente MQTT. Llamar una vez en setup().
// No bloquea: la conexión se completa dentro de comunicacionAtender().
void comunicacionConectar();

// Publica el estado de una plaza (numerada desde 1). Si no hay conexión
// o la publicación falla, queda pendiente y se reenvía al reconectar.
// Si se acumulan cambios, solo se envía el último (es el estado real).
void publicarEstado(int plaza, bool ocupada, float distanciaCm);

// Mantiene la conexión, reconecta si se cae y reenvía los pendientes.
// Llamar en cada loop().
void comunicacionAtender();
