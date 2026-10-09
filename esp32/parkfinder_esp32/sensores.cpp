// sensores.cpp - Implementación del módulo de sensado
// - Confirmación: el estado cambia solo tras N lecturas consecutivas que coinciden.
// - Umbral distinto para ocupar y para liberar.
// - LED bicolor de 2 pines: rojo = ocupada, verde = libre.

#include "sensores.h"

// --- Parámetros del sensor ---
static const unsigned long TIMEOUT_US = 30000;  // Espera máxima del eco (~5 m)

// --- Parámetros del filtrado ---
static const float UMBRAL_OCUPAR_CM  = 10.0;  // Libre -> ocupada si d <= 10 cm
static const float UMBRAL_LIBERAR_CM = 13.0;  // Ocupada -> libre si d > 13 cm
static const int LECTURAS_CONFIRMACION = 15;  // Lecturas seguidas para confirmar

// --- Datos de cada plaza (privados de este archivo) ---
namespace {
  struct Plaza {
    int numero;
    int pinTrig;
    int pinEcho;
    int pinLedRojo;    // HIGH en este pin y LOW en el otro = rojo
    int pinLedVerde;   // HIGH en este pin y LOW en el otro = verde
    bool ocupada;      // Estado confirmado
    int contadorCambio;  // Lecturas consecutivas que contradicen el estado
    float ultimaDistancia;
  };
}

// Para agregar una plaza, sumar una línea.
static Plaza plazas[] = {
  // numero, Trig, Echo, LED rojo, LED verde, ocupada, contador, distancia
  { 1, 13, 12, 25, 26, false, 0, -1 },
};

static const int CANTIDAD_PLAZAS = sizeof(plazas) / sizeof(plazas[0]);
static int plazaActual = 0;  // Próxima plaza a medir (se miden de a una)

// Dispara el sensor y devuelve la distancia en cm (-1 si no hubo eco)
static float medirDistanciaCm(const Plaza &p) {
  digitalWrite(p.pinTrig, LOW);
  delayMicroseconds(2);
  digitalWrite(p.pinTrig, HIGH);
  delayMicroseconds(10);
  digitalWrite(p.pinTrig, LOW);

  unsigned long duracion = pulseIn(p.pinEcho, HIGH, TIMEOUT_US);
  if (duracion == 0) {
    return -1;
  }
  return duracion * 0.0343 / 2.0;
}

// Interpreta una lectura según el estado actual
static bool lecturaIndicaOcupada(const Plaza &p, float distancia) {
  if (distancia < 0) {
    return false;  // Sin eco = no hay objeto cerca
  }
  if (p.ocupada) {
    // Para seguir ocupada alcanza con estar dentro del umbral más amplio
    return distancia <= UMBRAL_LIBERAR_CM;
  } else {
    // Para pasar a ocupada hay que estar dentro del umbral más estricto
    return distancia <= UMBRAL_OCUPAR_CM;
  }
}

// Muestra el estado de la plaza en el LED bicolor
static void actualizarLed(const Plaza &p) {
  if (p.ocupada) {
    digitalWrite(p.pinLedVerde, LOW);
    digitalWrite(p.pinLedRojo, HIGH);
  } else {
    digitalWrite(p.pinLedRojo, LOW);
    digitalWrite(p.pinLedVerde, HIGH);
  }
}

void sensoresIniciar() {
  for (int i = 0; i < CANTIDAD_PLAZAS; i++) {
    Plaza &p = plazas[i];
    pinMode(p.pinTrig, OUTPUT);
    pinMode(p.pinEcho, INPUT);
    digitalWrite(p.pinTrig, LOW);

    pinMode(p.pinLedRojo, OUTPUT);
    pinMode(p.pinLedVerde, OUTPUT);
    actualizarLed(p);  // Arranca en libre (verde)
  }
}

bool sensoresActualizar(EventoPlaza &evento) {
  // Elegir la plaza de este turno y avanzar a la siguiente
  Plaza &p = plazas[plazaActual];
  plazaActual = (plazaActual + 1) % CANTIDAD_PLAZAS;

  float distancia = medirDistanciaCm(p);
  p.ultimaDistancia = distancia;
  bool lecturaOcupada = lecturaIndicaOcupada(p, distancia);

  if (lecturaOcupada == p.ocupada) {
    // La lectura coincide con el estado: descartar cambios parciales
    p.contadorCambio = 0;
    return false;
  }

  // La lectura contradice el estado actual: sumar al contador
  p.contadorCambio++;
  if (p.contadorCambio < LECTURAS_CONFIRMACION) {
    return false;  // Todavía no se confirma
  }

  // Cambio confirmado
  p.ocupada = lecturaOcupada;
  p.contadorCambio = 0;
  actualizarLed(p);

  evento.plaza = p.numero;
  evento.ocupada = p.ocupada;
  evento.distancia = distancia;
  return true;
}

int sensoresCantidadPlazas() {
  return CANTIDAD_PLAZAS;
}

EventoPlaza sensoresEstadoActual(int indice) {
  const Plaza &p = plazas[indice];
  return { p.numero, p.ocupada, p.ultimaDistancia };
}
