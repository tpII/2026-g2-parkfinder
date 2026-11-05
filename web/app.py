"""Servicio web del tótem: el conductor ingresa su patente y la página le dice
en qué plaza está estacionado (RF06).

Lee la base SQLite que escribe el suscriptor (ocr/suscriptor.py) en modo solo
lectura: la base está en WAL, así que el tótem consulta mientras el pipeline
registra. Corre como un servicio aparte del suscriptor, para que una falla de
la cámara o del OCR no deje sin respuesta al tótem.

Rutas:
  GET /                       página del tótem (static/totem.html)
  GET /api/patente/<patente>  plaza de una patente con estadía abierta
  GET /api/estado             estado de todas las plazas, sin patentes: el
                              tótem es público y no debe mostrar qué auto
                              está en cada plaza

Uso:
  python app.py                              (puerto 8080, base ../datos/parkfinder.db)
  python app.py --puerto 80 --base RUTA.db   (en la Pi lo lanza parkfinder-web.service)
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ocr"))
from validacion import validar  # noqa: E402  (módulo de ocr/, mismo criterio que el pipeline)

BASE_POR_DEFECTO = RAIZ / "datos" / "parkfinder.db"
PLAZAS_POR_DEFECTO = RAIZ / "config" / "plazas.json"
ESTATICOS = Path(__file__).resolve().parent / "static"

# Ubicación de cada plaza vista desde la entrada (la plaza 1 es la de la
# izquierda vista desde la cámara, igual que en los tópicos MQTT).
LADOS = {"1": "izquierda", "2": "derecha"}


def normalizar(texto):
    """'xso 059', 'XSO-059' -> 'XSO059'."""
    return re.sub(r"[^A-Za-z0-9]", "", texto).upper()


def hora(momento):
    """'2026-10-28T17:42:10' -> '17:42'."""
    return momento[11:16] if momento and len(momento) >= 16 else momento


def cargar_plazas(ruta):
    """Plazas configuradas, en orden, a partir de las zonas de config/plazas.json."""
    with open(ruta, encoding="utf-8") as archivo:
        return sorted(json.load(archivo)["plazas"], key=lambda p: (len(p), p))


def describir(plaza):
    return {"plaza": plaza, "lado": LADOS.get(plaza)}


def crear_app(ruta_base=BASE_POR_DEFECTO, ruta_plazas=PLAZAS_POR_DEFECTO):
    app = Flask(__name__, static_folder=str(ESTATICOS), static_url_path="/static")
    ruta_base = Path(ruta_base)
    plazas = cargar_plazas(ruta_plazas)

    def conectar():
        # Solo lectura: el tótem nunca escribe en la base del pipeline.
        if not ruta_base.exists():
            return None
        con = sqlite3.connect(ruta_base.as_uri() + "?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        return con

    def abiertas(con):
        return con.execute(
            "SELECT plaza, patente, ingreso FROM estadias WHERE egreso IS NULL ORDER BY plaza"
        ).fetchall()

    def sin_base():
        return jsonify(error="El sistema todavía no registró ningún vehículo."), 503

    @app.after_request
    def sin_cache(respuesta):
        if respuesta.mimetype == "application/json":
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    @app.get("/")
    def totem():
        return send_from_directory(ESTATICOS, "totem.html")

    @app.get("/api/patente/<path:texto>")
    def buscar(texto):
        patente = normalizar(texto)
        if not validar(patente):
            return jsonify(encontrada=False, patente=patente,
                           error="La patente no tiene un formato válido."), 400
        con = conectar()
        if con is None:
            return sin_base()
        with con:
            filas = abiertas(con)
        con.close()
        for fila in filas:
            if fila["patente"] == patente:
                return jsonify(encontrada=True, patente=patente, ingreso=fila["ingreso"],
                               hora=hora(fila["ingreso"]), **describir(fila["plaza"]))
        # Plazas ocupadas cuya patente no se pudo leer: el vehículo buscado
        # puede ser uno de ellos, y el tótem lo avisa en lugar de un "no está".
        sin_leer = [describir(f["plaza"]) for f in filas if f["patente"] is None]
        return jsonify(encontrada=False, patente=patente, sin_leer=sin_leer), 404

    @app.get("/api/estado")
    def estado():
        con = conectar()
        if con is None:
            return sin_base()
        with con:
            ocupadas = {f["plaza"] for f in abiertas(con)}
        con.close()
        return jsonify(plazas=[{**describir(plaza), "ocupada": plaza in ocupadas}
                               for plaza in plazas])

    return app


def main():
    parser = argparse.ArgumentParser(description="Servicio web del tótem de ParkFinder.")
    parser.add_argument("--base", default=str(BASE_POR_DEFECTO), help="archivo SQLite del suscriptor")
    parser.add_argument("--plazas", default=str(PLAZAS_POR_DEFECTO), help="JSON de plazas")
    parser.add_argument("--puerto", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    from waitress import serve
    print(f"Tótem en http://{args.host}:{args.puerto}  (base {args.base})", flush=True)
    serve(crear_app(args.base, args.plazas), host=args.host, port=args.puerto, threads=4)


if __name__ == "__main__":
    main()
