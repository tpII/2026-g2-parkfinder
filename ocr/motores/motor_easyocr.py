"""Motor EasyOCR: recibe la imagen original a color (rinde mejor que con el
preprocesamiento de Tesseract). Carga un modelo PyTorch en __init__."""

import easyocr

from motores.base import MotorOCR

ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class MotorEasyOCR(MotorOCR):
    nombre = "easyocr"

    def __init__(self):
        self._lector = easyocr.Reader(["en"], gpu=False)

    def leer(self, imagen_bgr):
        resultados = self._lector.readtext(imagen_bgr, detail=1, allowlist=ALLOWLIST)
        if not resultados:
            return "", 0.0
        texto = "".join(r[1] for r in resultados).upper().replace(" ", "")
        confianza = sum(r[2] for r in resultados) / len(resultados)
        return texto, confianza
