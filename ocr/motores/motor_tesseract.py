"""Motor Tesseract: preprocesamiento.py + --psm 8 (una palabra) y lista
blanca A-Z0-9. --psm 7 (una línea) devolvía vacío en recortes ajustados."""

import os

import pytesseract
from pytesseract import Output

from motores.base import MotorOCR
from preprocesamiento import preprocesar

CONFIG = "--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# En Linux (Pi) tesseract está en el PATH; en Windows hay que indicar el binario.
if "TESSERACT_CMD" in os.environ:
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
elif os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class MotorTesseract(MotorOCR):
    nombre = "tesseract"

    def leer(self, imagen_bgr):
        preprocesada, _ = preprocesar(imagen_bgr)
        texto = pytesseract.image_to_string(preprocesada, config=CONFIG).strip()

        datos = pytesseract.image_to_data(preprocesada, config=CONFIG, output_type=Output.DICT)
        confs = [float(c) for c in datos["conf"] if float(c) >= 0]
        confianza = (sum(confs) / len(confs) / 100) if confs else 0.0

        return texto, confianza
