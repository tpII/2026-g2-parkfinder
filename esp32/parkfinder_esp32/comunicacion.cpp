// ParkFinder - Comunicación WiFi + MQTT del ESP32

#include "comunicacion.h"
#include <WiFi.h>
#include <ESPmDNS.h>
#include <MQTT.h>

static WiFiClient red;
static MQTTClient cliente(256);       // Buffer de 256 bytes, sobra para estos mensajes

// Último estado conocido de cada plaza (índice = plaza - 1)
struct EstadoPlaza {
  bool ocupada;
  float distanciaCm;
  bool pendiente;                     // true = todavía no confirmado por el broker
};
static EstadoPlaza estados[MAX_PLAZAS] = {};

static unsigned long ultimoIntento = 0;
static bool primerIntento = true;
static bool wifiAnterior = false;
static bool mdnsIniciado = false;

// Envía el estado guardado de una plaza. Devuelve true si el broker lo confirmó.
static bool enviar(int plaza) {
  EstadoPlaza &p = estados[plaza - 1];
  String tema = String(TEMA_BASE) + plaza;
  const char *contenido = p.ocupada ? "ocupada" : "libre";

  // publish(tema, contenido, retain, qos)
  bool ok = cliente.publish(tema, contenido, true, 1);

  if (ok) {
    p.pendiente = false;
    if (p.ocupada) {
      Serial.printf("[MQTT] %s -> %s (%.1f cm)\n", tema.c_str(), contenido, p.distanciaCm);
    } else {
      Serial.printf("[MQTT] %s -> %s\n", tema.c_str(), contenido);
    }
  } else {
    Serial.printf("[MQTT] %s -> %s (FALLÓ, queda pendiente)\n", tema.c_str(), contenido);
  }
  return ok;
}

// Reenvía todo lo pendiente. Si algo falla, corta y reintenta en la próxima vuelta.
static void enviarPendientes() {
  for (int plaza = 1; plaza <= MAX_PLAZAS; plaza++) {
    if (estados[plaza - 1].pendiente && !enviar(plaza)) return;
  }
}

// true si MQTT_BROKER es un nombre ".local" (se busca por mDNS)
static bool brokerEsMdns() {
  const char *sufijo = ".local";
  size_t largo = strlen(MQTT_BROKER), largoSufijo = strlen(sufijo);
  return largo > largoSufijo && strcmp(MQTT_BROKER + largo - largoSufijo, sufijo) == 0;
}

// Carga en el cliente la dirección del broker. Si es un nombre ".local",
// lo busca por mDNS en cada intento: la IP puede haber cambiado si el
// ESP32 o la Pi cambiaron de red. La búsqueda bloquea hasta 2 s si la Pi
// no responde; entre intentos (cada REINTENTO_MS) las mediciones siguen.
static bool resolverBroker() {
  if (!brokerEsMdns()) {
    cliente.setHost(MQTT_BROKER, MQTT_PUERTO);  // IP escrita a mano
    return true;
  }
  if (!mdnsIniciado) {
    mdnsIniciado = MDNS.begin(MDNS_NOMBRE);
    if (!mdnsIniciado) {
      Serial.println("[mDNS] No se pudo iniciar");
      return false;
    }
  }
  String nombre = MQTT_BROKER;
  nombre.remove(nombre.length() - strlen(".local"));  // queryHost va sin ".local"
  IPAddress ip = MDNS.queryHost(nombre, 2000);
  if (ip == IPAddress()) {
    Serial.printf("[mDNS] No se encontró %s en la red\n", MQTT_BROKER);
    return false;
  }
  Serial.printf("[mDNS] %s -> %s\n", MQTT_BROKER, ip.toString().c_str());
  cliente.setHost(ip, MQTT_PUERTO);
  return true;
}

static bool intentarConectar() {
  if (!resolverBroker()) {
    return false;
  }
  Serial.printf("[MQTT] Conectando a %s:%d... ", MQTT_BROKER, MQTT_PUERTO);

  if (cliente.connect(MQTT_ID)) {
    Serial.println("conectado");
    return true;
  }
  // lastError: error de red/biblioteca; returnCode: respuesta del broker
  Serial.printf("falló (error %d, código %d)\n",
                cliente.lastError(), cliente.returnCode());
  return false;
}

void comunicacionConectar() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_CLAVE);
  Serial.printf("[WiFi] Conectando a %s...\n", WIFI_SSID);

  // La dirección del broker se carga en cada intento (resolverBroker)
  cliente.begin(red);
  // keepalive 10 s, sesión limpia, timeout 1000 ms (acota el bloqueo al reconectar)
  cliente.setOptions(10, true, 1000);
}

void publicarEstado(int plaza, bool ocupada, float distanciaCm) {
  if (plaza < 1 || plaza > MAX_PLAZAS) {
    Serial.printf("[MQTT] Plaza %d fuera de rango (1..%d)\n", plaza, MAX_PLAZAS);
    return;
  }

  EstadoPlaza &p = estados[plaza - 1];
  p.ocupada = ocupada;
  p.distanciaCm = distanciaCm;
  p.pendiente = true;

  if (cliente.connected()) {
    enviar(plaza);
  } else {
    Serial.printf("[MQTT] Sin conexión, plaza %d queda pendiente\n", plaza);
  }
}

void comunicacionAtender() {
  cliente.loop();  // Procesa el tráfico MQTT y detecta desconexiones

  // Estado del WiFi (se informa solo cuando cambia)
  bool wifiOk = (WiFi.status() == WL_CONNECTED);
  if (wifiOk != wifiAnterior) {
    if (wifiOk) {
      Serial.print("[WiFi] Conectado, IP: ");
      Serial.println(WiFi.localIP());
    } else {
      Serial.println("[WiFi] Desconectado");
    }
    wifiAnterior = wifiOk;
  }
  if (!wifiOk) return;

  // Reconexión al broker sin bloquear el loop
  if (!cliente.connected()) {
    if (!primerIntento && millis() - ultimoIntento < REINTENTO_MS) return;
    primerIntento = false;
    ultimoIntento = millis();
    if (!intentarConectar()) return;
  }

  enviarPendientes();
}
