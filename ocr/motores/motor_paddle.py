"""Motor PaddleOCR: recibe la imagen original a color. Se desactivan los pasos
pensados para páginas completas (orientación, curvatura) porque la entrada ya
es el recorte de una patente."""

from paddleocr import PaddleOCR

from motores.base import MotorOCR


class MotorPaddle(MotorOCR):
    nombre = "paddleocr"

    def __init__(self):
        self._ocr = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # Con MKL-DNN, paddlepaddle 3.3.1 falla en CPU x86 (bug oneDNN/PIR); en ARM no aplica.
            enable_mkldnn=False,
        )

    def leer(self, imagen_bgr):
        resultado = self._ocr.predict(imagen_bgr)
        if not resultado:
            return "", 0.0
        r = resultado[0]
        textos = r.get("rec_texts") or []
        scores = r.get("rec_scores") or []
        if not textos:
            return "", 0.0
        texto = "".join(textos).upper().replace(" ", "")
        confianza = sum(scores) / len(scores) if scores else 0.0
        return texto, confianza
