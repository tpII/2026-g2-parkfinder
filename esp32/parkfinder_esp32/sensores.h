// sensores.h - Módulo de sensado de ParkFinder
// Mide cada plaza (HC-SR04), filtra el ruido, actualiza el LED bicolor
// y avisa al programa principal cuando una plaza cambia de estado.

#pragma once
#include <Arduino.h>

// Datos de un cambio de estado (o del estado actual de una plaza)
struct EventoPlaza {
  int plaza;        // Número de plaza (1, 2, ...)
  bool ocupada;     // true = ocupada, false = libre
  float distancia;  // Distancia medida en cm (-1 si no hubo eco)
};

// Configura los pines de todas las plazas. Llamar en setup().
void sensoresIniciar();

// Mide UNA plaza (se van turnando en cada llamada).
// Devuelve true si se confirmó un cambio de estado, y lo carga en "evento".
// Devuelve false si no hubo cambio ("evento" no se modifica).
bool sensoresActualizar(EventoPlaza &evento);

// Consulta del estado actual, sin medir.
// Sirve para publicar el estado inicial o republicarlo al reconectar.
int sensoresCantidadPlazas();
EventoPlaza sensoresEstadoActual(int indice);  // indice: 0 .. cantidad-1
