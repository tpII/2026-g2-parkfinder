"""Pruebas de la relectura de plazas ocupadas sin patente (suscriptor.py y
BaseDatos.completar_patente), con una cámara y un motor OCR simulados y una
base temporal. No hace falta cámara, Tesseract ni broker MQTT.

Uso (desde ocr/):  python -m unittest -v test_relectura
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import pipeline
from base_datos import BaseDatos
from pipeline import Pipeline
from suscriptor import Servicio
from test_votacion import FuenteFalsa, MotorFalso


class PruebasRelectura(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.base = BaseDatos(Path(self.dir.name) / "prueba.db")
        # El recorte se saltea: la "imagen" que da la cámara falsa es el texto que lee el motor.
        for parche in (mock.patch.object(pipeline, "escalar_zona", return_value=None),
                       mock.patch.object(pipeline, "recortar_plaza",
                                         side_effect=lambda imagen, zona: imagen)):
            parche.start()
            self.addCleanup(parche.stop)

    def tearDown(self):
        self.base.cerrar()
        self.dir.cleanup()

    def servicio(self, textos, intentos=3):
        """Servicio con la cámara falsa; intervalo 0: cada relectura ya está vencida."""
        self.fuente = FuenteFalsa(textos)
        tuberia = Pipeline(self.fuente, MotorFalso(), {"1": [0, 0, 1, 1], "2": [0, 0, 1, 1]},
                           [1280, 960], self.base)
        return Servicio(tuberia, espera_captura=0, relectura_intervalo=0, relectura_intentos=intentos)

    def abierta(self, plaza):
        return self.base._con.execute(
            "SELECT patente, ingreso FROM estadias WHERE plaza = ? AND egreso IS NULL",
            (plaza,)).fetchone()

    def test_completa_la_patente_y_conserva_el_ingreso(self):
        servicio = self.servicio([None, None, "BJ741CY", "BJ741CY"])
        servicio.atender("1", "ocupada", time.perf_counter())
        ingreso = self.abierta("1")["ingreso"]
        self.assertIsNone(self.abierta("1")["patente"])
        self.assertIn("1", servicio.pendientes)

        servicio.releer_pendientes()
        self.assertEqual(self.abierta("1")["patente"], "BJ741CY")
        self.assertEqual(self.abierta("1")["ingreso"], ingreso)
        self.assertNotIn("1", servicio.pendientes)
        # La lectura de la relectura queda marcada en la base.
        fila = self.base._con.execute(
            "SELECT patente, relectura FROM lecturas ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((fila["patente"], fila["relectura"]), ("BJ741CY", 1))
        # Lo encuentra el tótem (misma consulta que la estadía abierta por patente).
        self.assertEqual(self.base.buscar_patente("BJ741CY")["plaza"], "1")

    def test_deja_de_releer_al_agotar_los_intentos(self):
        servicio = self.servicio([None] * 8, intentos=3)
        servicio.atender("1", "ocupada", time.perf_counter())
        for _ in range(3):
            servicio.releer_pendientes()
        self.assertNotIn("1", servicio.pendientes)
        self.assertIsNone(self.abierta("1")["patente"])
        self.assertEqual(self.fuente.capturas, 8)  # 2 del aviso + 2 por relectura (corta antes)

    def test_libre_cancela_la_relectura(self):
        servicio = self.servicio([None, None])
        servicio.atender("1", "ocupada", time.perf_counter())
        servicio.atender("1", "libre", time.perf_counter())
        self.assertEqual(servicio.pendientes, {})
        self.assertIsNone(self.espera(servicio))

    def test_con_patente_no_relee(self):
        servicio = self.servicio(["XSO059", "XSO059"])
        servicio.atender("2", "ocupada", time.perf_counter())
        self.assertEqual(servicio.pendientes, {})

    def test_los_avisos_tienen_prioridad(self):
        servicio = self.servicio([None, None, "BJ741CY", "BJ741CY"])
        servicio.atender("1", "ocupada", time.perf_counter())
        servicio.eventos.put(("2", "ocupada", time.perf_counter()))
        servicio.releer_pendientes()
        self.assertEqual(self.fuente.capturas, 2)  # no capturó: hay un aviso esperando
        self.assertIn("1", servicio.pendientes)

    def test_no_relee_antes_del_intervalo(self):
        servicio = self.servicio([None, None, "BJ741CY", "BJ741CY"])
        servicio.relectura_intervalo = 60
        servicio.atender("1", "ocupada", time.perf_counter())
        servicio.releer_pendientes()
        self.assertEqual(self.fuente.capturas, 2)
        self.assertGreater(self.espera(servicio), 50)

    def test_al_arrancar_relee_las_plazas_sin_patente(self):
        self.base._con.execute(
            "INSERT INTO estadias (plaza, patente, ingreso) VALUES ('2', NULL, '2026-11-05T15:00:00')")
        self.base._con.commit()
        servicio = self.servicio(["MPT236", "MPT236"])
        self.assertEqual(servicio.estado["2"], "ocupada")
        self.assertIn("2", servicio.pendientes)
        servicio.releer_pendientes()
        self.assertEqual(self.abierta("2")["patente"], "MPT236")
        self.assertEqual(self.abierta("2")["ingreso"], "2026-11-05T15:00:00")

    def test_completar_sin_estadia_abierta(self):
        servicio = self.servicio(["MPT236", "MPT236"])
        lectura, completada = servicio.pipeline.releer_plaza("2")
        self.assertEqual(lectura.patente, "MPT236")
        self.assertFalse(completada)

    def test_relectura_desactivada(self):
        servicio = self.servicio([None, None], intentos=0)
        servicio.atender("1", "ocupada", time.perf_counter())
        self.assertEqual(servicio.pendientes, {})

    def test_conexion_del_esp32(self):
        from suscriptor import CONEXION
        servicio = self.servicio([])
        servicio.atender(CONEXION, "conectado", time.perf_counter())
        servicio.atender(CONEXION, "conectado", time.perf_counter())  # retenido repetido
        servicio.atender(CONEXION, "desconectado", time.perf_counter())
        estados = [f["estado"] for f in self.base._con.execute(
            "SELECT estado FROM conexion_sensado ORDER BY id")]
        self.assertEqual(estados, ["conectado", "desconectado"])
        self.assertEqual(self.base.conexion_sensado(), "desconectado")
        self.assertEqual(self.fuente.capturas, 0)  # no dispara capturas

    @staticmethod
    def espera(servicio):
        return servicio.espera_hasta_relectura()


if __name__ == "__main__":
    unittest.main()
