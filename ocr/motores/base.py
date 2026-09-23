"""Interfaz común de motor OCR: cada motor recibe la imagen BGR original y
aplica su propio preprocesamiento si lo necesita."""

from abc import ABC, abstractmethod


class MotorOCR(ABC):
    nombre = "motor"

    @abstractmethod
    def leer(self, imagen_bgr):
        """Devuelve (texto: str, confianza: float entre 0 y 1)."""
        raise NotImplementedError
