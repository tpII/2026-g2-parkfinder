"""Pruebas de la votación entre capturas de pipeline.py, con una cámara y un
motor OCR simulados (no hace falta cámara ni Tesseract).

Uso (desde ocr/):  python -m unittest -v test_votacion
"""

import unittest
from unittest import mock

import pipeline
from captura import ErrorCaptura
from pipeline import Pipeline


class FuenteFalsa:
    """Cámara simulada: cada captura devuelve el texto que "leerá" el motor,
    o lanza ErrorCaptura si el elemento es la excepción."""

    def __init__(self, textos):
        self.textos = list(textos)
        self.capturas = 0

    def capturar(self):
        texto = self.textos[self.capturas]
        self.capturas += 1
        if texto is ErrorCaptura:
            raise ErrorCaptura("captura fallida simulada")
        return texto


class MotorFalso:
    def leer(self, recorte):
        return recorte, 0  # el "recorte" ya es el texto


def leer(textos, capturas=3, votos_minimos=2):
    fuente = FuenteFalsa(textos)
    tuberia = Pipeline(fuente, MotorFalso(), {"1": [0, 0, 1, 1]}, [1280, 960], base=None,
                       capturas=capturas, votos_minimos=votos_minimos)
    # El recorte se saltea: la "imagen" pasa tal cual al motor. None = zona sin patente.
    with mock.patch.object(pipeline, "escalar_zona", return_value=None), \
         mock.patch.object(pipeline, "recortar_plaza", side_effect=lambda imagen, zona: imagen):
        return tuberia.leer_plaza("1"), fuente.capturas


class PruebasVotacion(unittest.TestCase):
    def test_dos_iguales_registra_y_corta(self):
        lectura, capturas = leer(["BJ741CY", "BJ741CY", "BJ741CY"])
        self.assertEqual(lectura.patente, "BJ741CY")
        self.assertEqual(lectura.votos, 2)
        self.assertEqual(lectura.formato, "mercosur")
        self.assertEqual(capturas, 2)  # la tercera no hace falta

    def test_una_sola_valida_no_registra(self):
        # Caso del 09/10: una "U" en lugar de la C da un formato válido pero incorrecto.
        lectura, capturas = leer(["BJ741UY", None, None])
        self.assertIsNone(lectura.patente)
        self.assertEqual(lectura.votos, 0)
        self.assertEqual(lectura.candidata, "BJ741UY")
        self.assertEqual(capturas, 3)

    def test_dos_distintas_y_desempate(self):
        lectura, capturas = leer(["BJ741UY", "BJ741CY", "BJ741CY"])
        self.assertEqual(lectura.patente, "BJ741CY")
        self.assertEqual(lectura.votos, 2)
        self.assertEqual(capturas, 3)

    def test_tres_distintas_no_registra(self):
        lectura, _ = leer(["BJ741UY", "BJ741CY", "BJ741GY"])
        self.assertIsNone(lectura.patente)
        self.assertEqual(lectura.candidata, "BJ741UY")

    def test_corta_si_no_puede_llegar_al_minimo(self):
        # Dos capturas sin patente: con una sola restante nadie llega a 2 votos.
        lectura, capturas = leer([None, None, "BJ741CY"])
        self.assertIsNone(lectura.patente)
        self.assertIsNone(lectura.candidata)
        self.assertEqual(capturas, 2)
        self.assertEqual(lectura.capturas, 2)

    def test_captura_fallida_cuenta_como_sin_patente(self):
        lectura, _ = leer([ErrorCaptura, "XSO059", "XSO059"])
        self.assertEqual(lectura.patente, "XSO059")
        self.assertEqual(lectura.formato, "viejo")
        self.assertEqual(lectura.crudas[0], None)

    def test_invalidas_no_votan(self):
        lectura, _ = leer(["HOLA", "XSO059", "XSO059"])
        self.assertEqual(lectura.patente, "XSO059")

    def test_un_voto_si_se_configura(self):
        # --votos-minimos 1 vuelve al comportamiento anterior.
        lectura, capturas = leer(["BJ741UY", None, None], votos_minimos=1)
        self.assertEqual(lectura.patente, "BJ741UY")
        self.assertEqual(capturas, 1)

    def test_minimo_invalido(self):
        with self.assertRaises(ValueError):
            Pipeline(None, None, {}, None, None, capturas=3, votos_minimos=4)


if __name__ == "__main__":
    unittest.main()
