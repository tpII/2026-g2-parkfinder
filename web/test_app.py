"""Pruebas de la API del tótem con una base temporal.

Uso (desde web/):  python -m unittest -v test_app
"""

import json
import tempfile
import unittest
from pathlib import Path

from app import crear_app, normalizar
from base_datos import BaseDatos  # ocr/, en el path por app.py


class PruebasTotem(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        carpeta = Path(self.dir.name)
        self.base = carpeta / "prueba.db"
        plazas = carpeta / "plazas.json"
        plazas.write_text(json.dumps({"resolucion": [1280, 960],
                                      "plazas": {"1": [0, 0, 1, 1], "2": [0, 0, 1, 1]}}))
        # Esquema real, creado con la misma clase que usa el suscriptor.
        bd = BaseDatos(self.base)
        bd._con.executescript("""
            INSERT INTO estadias (plaza, patente, ingreso, egreso)
                VALUES ('1', 'XSO059', '2026-11-03T17:42:10', NULL);
            INSERT INTO estadias (plaza, patente, ingreso, egreso)
                VALUES ('2', 'MPT236', '2026-11-03T16:00:00', '2026-11-03T16:30:00');
        """)
        bd.cerrar()
        self.plazas = plazas
        self.cliente = crear_app(self.base, plazas).test_client()

    def tearDown(self):
        self.dir.cleanup()

    def test_normalizar(self):
        self.assertEqual(normalizar("xso 059"), "XSO059")
        self.assertEqual(normalizar("ab-123.cd"), "AB123CD")

    def test_encontrada(self):
        r = self.cliente.get("/api/patente/XSO059")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["plaza"], "1")
        self.assertEqual(r.json["lado"], "izquierda")
        self.assertEqual(r.json["hora"], "17:42")

    def test_encontrada_con_espacios_y_minusculas(self):
        r = self.cliente.get("/api/patente/xso%20059")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["patente"], "XSO059")

    def test_estadia_cerrada_no_aparece(self):
        r = self.cliente.get("/api/patente/MPT236")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.json["encontrada"])
        self.assertEqual(r.json["sin_leer"], [])

    def test_formato_invalido(self):
        r = self.cliente.get("/api/patente/HOLA")
        self.assertEqual(r.status_code, 400)

    def test_plaza_sin_leer(self):
        bd = BaseDatos(self.base)
        bd._con.execute("INSERT INTO estadias (plaza, patente, ingreso) VALUES ('2', NULL, '2026-11-03T18:00:00')")
        bd._con.commit()
        bd.cerrar()
        r = self.cliente.get("/api/patente/AB123CD")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json["sin_leer"], [{"plaza": "2", "lado": "derecha"}])

    def test_estado(self):
        r = self.cliente.get("/api/estado")
        self.assertEqual(r.status_code, 200)
        plazas = r.json["plazas"]
        self.assertEqual([p["plaza"] for p in plazas], ["1", "2"])
        self.assertTrue(plazas[0]["ocupada"])
        self.assertFalse(plazas[1]["ocupada"])
        # El tótem es público: el estado no expone qué patente ocupa cada plaza.
        self.assertNotIn(b"XSO059", r.data)
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_estado_sensado(self):
        self.assertIsNone(self.cliente.get("/api/estado").json["sensado"])
        bd = BaseDatos(self.base)
        bd.registrar_conexion("conectado", "2026-11-05T15:00:00")
        bd.registrar_conexion("desconectado", "2026-11-05T15:05:00")
        bd.cerrar()
        self.assertEqual(self.cliente.get("/api/estado").json["sensado"], "desconectado")

    def test_sin_base(self):
        cliente = crear_app(Path(self.dir.name) / "no_existe.db", self.plazas).test_client()
        self.assertEqual(cliente.get("/api/estado").status_code, 503)
        self.assertEqual(cliente.get("/api/patente/XSO059").status_code, 503)

    def test_pagina(self):
        r = self.cliente.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"ParkFinder", r.data)
        self.assertEqual(r.headers["Cache-Control"], "no-cache")
        r.close()
        r = self.cliente.get("/static/totem.js")
        self.assertEqual(r.headers["Cache-Control"], "no-cache")
        r.close()


if __name__ == "__main__":
    unittest.main()
