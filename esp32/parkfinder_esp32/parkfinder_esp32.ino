// ParkFinder - Programa principal del ESP32
// Une los módulos: sensores (HC-SR04 + LED) y comunicación (WiFi + MQTT).
// Es el único archivo que conoce a ambos.

#include "sensores.h"
#include "comunicacion.h"

// Pausa entre mediciones. Como las plazas se miden de a una,
// cada plaza se mide cada INTERVALO_MS x cantidad de plazas.
const unsigned long INTERVALO_MS = 100;  // No bajar de ~50 ms

// Muestra un evento o estado en el Monitor Serie
void mostrar(const EventoPlaza &e) {
  if (e.ocupada) {
    Serial.printf("Plaza %d: ocupada (%.1f cm)\n", e.plaza, e.distancia);
  } else {
    Serial.printf("Plaza %d: libre\n", e.plaza);
  }
}

// Traduce un evento de sensores a la interfaz de comunicación
void informar(const EventoPlaza &e) {
  mostrar(e);
  publicarEstado(e.plaza, e.ocupada, e.distancia);
}

void setup() {
  Serial.begin(115200);
  sensoresIniciar();
  comunicacionConectar();

  Serial.println();
  Serial.println("ParkFinder - Monitoreo de plazas");

  // Estado inicial de todas las plazas. Queda pendiente y se
  // publica (retenido) apenas se establece la conexión.
  for (int i = 0; i < sensoresCantidadPlazas(); i++) {
    informar(sensoresEstadoActual(i));
  }
}

void loop() {
  comunicacionAtender();

  EventoPlaza evento;
  if (sensoresActualizar(evento)) {
    informar(evento);
  }

  delay(INTERVALO_MS);
}
