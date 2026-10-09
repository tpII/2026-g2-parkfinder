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
// Red WiFi (el ESP32 solo funciona en 2,4 GHz)
#define WIFI_SSID      "nombre_red_wifi"
#define WIFI_CLAVE     "contraseña_red_wifi"

// Broker: IP Raspberry Pi
#define MQTT_BROKER    "completar_con_ip"
#define MQTT_PUERTO    1883
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
