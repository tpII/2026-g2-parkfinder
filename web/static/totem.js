// ParkFinder: lógica del tótem de consulta.
// Pide los datos a la API de app.py y muestra la pantalla que corresponde.

const SEGUNDOS_REINICIO = 30;     // tiempo que queda visible el resultado
const SEGUNDOS_INACTIVIDAD = 45;  // borra una patente escrita y abandonada
const SEGUNDOS_ERROR = 12;        // tiempo que queda visible un mensaje de error
const MS_ACTUALIZAR_MAPA = 5000;

const $ = (id) => document.getElementById(id);

let plazas = [];
let plazaTuya = null;       // plaza del resultado que se está mostrando
let temporizadorResultado = null;
let temporizadorInactividad = null;
let temporizadorError = null;
let firmaPlazas = "";       // estado de las plazas en la última actualización

// ---------- Patente ----------

// "ab123cd" -> "AB 123 CD", "abc123" -> "ABC 123". También sirve a medio escribir.
function formatearPatente(texto) {
  const limpio = texto.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 7);
  const partes = limpio.match(/^([A-Z]{1,3})(\d{0,3})([A-Z]{0,2})/);
  if (!partes) return limpio;
  return [partes[1], partes[2], partes[3]].filter(Boolean).join(" ");
}

const sinEspacios = (patente) => patente.replace(/\s/g, "");
const patenteValida = (patente) => /^([A-Z]{3}\d{3}|[A-Z]{2}\d{3}[A-Z]{2})$/.test(sinEspacios(patente));

// ---------- Mapa ----------

// El mapa se arma con textContent, nunca con innerHTML de datos del servidor.
function crearPlaza(plaza) {
  const esTuya = plaza.plaza === plazaTuya;
  const elemento = document.createElement("div");
  elemento.className = "plaza plaza--" + (esTuya ? "tuya" : plaza.estado);

  const numero = document.createElement("span");
  numero.className = "plaza__numero";
  numero.textContent = plaza.plaza;

  const led = document.createElement("span");
  led.className = "plaza__led";

  const estado = document.createElement("span");
  estado.className = "plaza__estado";
  estado.textContent = esTuya ? "Tu auto" : plaza.estado === "libre" ? "Libre" : "Ocupada";

  elemento.append(numero, led);
  if (plaza.estado !== "libre") {
    elemento.insertAdjacentHTML("beforeend",
      '<svg class="plaza__auto" aria-hidden="true"><use href="#auto"/></svg>');
  }
  elemento.append(estado);
  return elemento;
}

function dibujarMapa(contenedor, conRecorrido) {
  contenedor.replaceChildren();

  if (!plazas.length) {
    const aviso = document.createElement("p");
    aviso.className = "mapa__aviso";
    aviso.textContent = "No se pudo cargar el estado de las plazas.";
    contenedor.append(aviso);
    contenedor.style.paddingBottom = "0";
    return;
  }
  contenedor.style.paddingBottom = "";

  const fila = document.createElement("div");
  fila.className = "mapa__plazas";
  fila.append(...plazas.map(crearPlaza));

  const entrada = document.createElement("span");
  entrada.className = "mapa__entrada";
  entrada.textContent = "Entrada";

  contenedor.append(fila, entrada);
  if (conRecorrido) dibujarRecorrido(contenedor);
}

// Línea punteada desde la entrada hasta el centro de la plaza del usuario.
function dibujarRecorrido(contenedor) {
  const indice = plazas.findIndex((p) => p.plaza === plazaTuya);
  const ancho = contenedor.clientWidth;
  if (indice < 0 || !ancho) return;

  const alto = 98;
  const centro = ancho / 2;
  const destino = ancho * (indice + 0.5) / plazas.length;
  const giro = 12 * Math.sign(destino - centro);
  const camino = giro === 0
    ? `M${centro} ${alto - 34}V4`
    : `M${centro} ${alto - 34}V34Q${centro} 22 ${centro + giro} 22H${destino - giro}Q${destino} 22 ${destino} 10V4`;

  contenedor.insertAdjacentHTML("beforeend",
    `<svg class="mapa__recorrido" viewBox="0 0 ${ancho} ${alto}" aria-hidden="true"><path d="${camino}"/></svg>`);
}

function textoLado(plaza) {
  const posicion = plazas.findIndex((p) => p.plaza === plaza);
  const mitad = (plazas.length - 1) / 2;
  if (posicion < 0) return "";
  if (posicion < mitad) return "A la izquierda de la entrada";
  if (posicion > mitad) return "A la derecha de la entrada";
  return "Frente a la entrada";
}

async function actualizarPlazas() {
  try {
    const respuesta = await fetch("/api/estado", { cache: "no-store" });
    if (!respuesta.ok) throw new Error(respuesta.status);
    const datos = await respuesta.json();
    plazas = datos.plazas.map((p) => ({ ...p, estado: p.ocupada ? "ocupada" : "libre" }));
    const libres = plazas.filter((p) => p.estado === "libre").length;
    const total = plazas.length;
    $("resumen-libres").textContent = `${libres} de ${total} ${total === 1 ? "plaza libre" : "plazas libres"}`;
  } catch {
    plazas = [];
    $("resumen-libres").textContent = "";
  }
  // Si cambió alguna plaza, un error anterior (por ejemplo "puede estar en la
  // plaza 1") puede haber quedado desactualizado: se borra.
  const firma = plazas.map((p) => p.plaza + p.estado).join();
  if (firma !== firmaPlazas) {
    firmaPlazas = firma;
    ocultarError();
  }
  if (!plazaTuya) dibujarMapa($("mapa-busqueda"), false);
}

// ---------- Mensajes de error ----------

function mostrarError(titulo, texto) {
  $("error-titulo").textContent = titulo;
  $("error-texto").textContent = texto;
  $("error").hidden = false;
  $("ayuda").hidden = true;
  $("patente-marco").classList.add("patente--error");
  clearTimeout(temporizadorError);
  temporizadorError = setTimeout(ocultarError, SEGUNDOS_ERROR * 1000);
}

function ocultarError() {
  clearTimeout(temporizadorError);
  $("error").hidden = true;
  $("ayuda").hidden = false;
  $("patente-marco").classList.remove("patente--error");
}

// ---------- Búsqueda ----------

async function buscar(evento) {
  evento.preventDefault();
  const patente = $("patente").value;

  if (!patenteValida(patente)) {
    mostrarError("Revisá la patente", "Tiene que ser como ABC 123 o AB 123 CD.");
    $("patente").focus();
    return;
  }

  $("buscar").disabled = true;
  $("buscar").textContent = "Buscando…";
  try {
    const respuesta = await fetch("/api/patente/" + encodeURIComponent(sinEspacios(patente)), { cache: "no-store" });
    if (respuesta.ok) {
      await mostrarResultado(await respuesta.json());
    } else if (respuesta.status === 404) {
      const datos = await respuesta.json();
      mostrarError("No encontramos esta patente", textoNoEncontrada(datos.sin_leer || []));
    } else if (respuesta.status === 400) {
      mostrarError("Revisá la patente", "Tiene que ser como ABC 123 o AB 123 CD.");
    } else {
      throw new Error(respuesta.status);
    }
  } catch {
    mostrarError("No pudimos hacer la consulta", "El sistema no responde. Volvé a intentar en unos segundos.");
  } finally {
    $("buscar").disabled = false;
    $("buscar").textContent = "Buscar mi auto";
  }
}

// Si hay plazas ocupadas cuya patente el OCR no pudo leer, el auto buscado
// puede ser uno de esos: se avisa en vez de dar solo "no encontrada".
function textoNoEncontrada(sinLeer) {
  if (!sinLeer.length) {
    return "Revisá que esté bien escrita. Si recién estacionaste, esperá unos segundos y volvé a buscar.";
  }
  const lista = sinLeer.map((p) => `la plaza ${p.plaza}` + (p.lado ? ` (${p.lado})` : "")).join(" o ");
  return sinLeer.length === 1
    ? `Revisá que esté bien escrita. Hay una plaza ocupada cuya patente no se pudo leer: tu auto puede estar en ${lista}.`
    : `Revisá que esté bien escrita. Hay plazas ocupadas cuya patente no se pudo leer: tu auto puede estar en ${lista}.`;
}

async function mostrarResultado(datos) {
  await actualizarPlazas();
  plazaTuya = datos.plaza;

  // "2026-11-03T19:45:12" -> "19:45": se lee del texto para no alterar la hora guardada.
  const hora = (datos.ingreso.match(/T(\d{2}:\d{2})/) || [])[1];

  $("resultado-plaza").textContent = "Plaza " + datos.plaza;
  // El lado lo define el servidor (LADOS en app.py); si no lo tiene, se deduce del mapa.
  $("resultado-lado").textContent = datos.lado ? `A la ${datos.lado} de la entrada` : textoLado(datos.plaza);
  $("resultado-patente").textContent = formatearPatente(datos.patente);
  $("resultado-desde").textContent = hora ? "Desde las " + hora : "";

  $("vista-busqueda").hidden = true;
  $("vista-resultado").hidden = false;
  dibujarMapa($("mapa-resultado"), true);
  iniciarReinicio();
}

function iniciarReinicio() {
  const fin = Date.now() + SEGUNDOS_REINICIO * 1000;
  const avanzar = () => {
    const restante = Math.max(0, fin - Date.now());
    if (restante === 0) return volverABuscar();
    $("reinicio-barra").style.width = (restante / (SEGUNDOS_REINICIO * 10)) + "%";
    $("reinicio-texto").textContent = `Esta pantalla se reinicia en ${Math.ceil(restante / 1000)} s`;
  };
  avanzar();
  temporizadorResultado = setInterval(avanzar, 200);
}

function volverABuscar() {
  clearInterval(temporizadorResultado);
  plazaTuya = null;
  $("patente").value = "";
  ocultarError();
  $("vista-resultado").hidden = true;
  $("vista-busqueda").hidden = false;
  dibujarMapa($("mapa-busqueda"), false);
  $("patente").focus();
}

// ---------- Eventos ----------

// Si alguien escribe y se va, el próximo no ve su patente.
function reiniciarInactividad() {
  clearTimeout(temporizadorInactividad);
  temporizadorInactividad = setTimeout(() => {
    $("patente").value = "";
    ocultarError();
  }, SEGUNDOS_INACTIVIDAD * 1000);
}

$("patente").addEventListener("input", (evento) => {
  evento.target.value = formatearPatente(evento.target.value);
  ocultarError();
  reiniciarInactividad();
});
$("formulario").addEventListener("submit", buscar);
$("volver").addEventListener("click", volverABuscar);
window.addEventListener("resize", () => {
  if (plazaTuya) dibujarMapa($("mapa-resultado"), true);
});

actualizarPlazas();
setInterval(actualizarPlazas, MS_ACTUALIZAR_MAPA);
