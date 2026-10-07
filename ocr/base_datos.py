"""Persistencia en SQLite. Dos tablas:
- lecturas: cada intento de leer una patente, con lo que leyó cada captura y
  el tiempo de cada etapa (diagnóstico y medición de latencia).
- estadias: qué patente ocupa qué plaza, desde y hasta cuándo. Lo que
  consulta el tótem es la estadía abierta (egreso NULL) de una patente.
"""

import json
import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS lecturas (
    id              INTEGER PRIMARY KEY,
    momento         TEXT NOT NULL,     -- ISO 8601, hora local
    plaza           TEXT NOT NULL,
    patente         TEXT,              -- NULL si ninguna captura dio una lectura válida
    formato         TEXT,              -- 'viejo' / 'mercosur'
    votos           INTEGER NOT NULL,  -- capturas que coincidieron con la patente elegida
    capturas        INTEGER NOT NULL,
    lecturas_crudas TEXT NOT NULL,     -- JSON: lectura corregida de cada captura (null = sin patente)
    textos_ocr      TEXT,              -- JSON: lo que devolvió el motor en cada captura, antes de corregir
    t_captura_ms    REAL,
    t_recorte_ms    REAL,
    t_ocr_ms        REAL,
    t_total_ms      REAL
);
CREATE TABLE IF NOT EXISTS estadias (
    id          INTEGER PRIMARY KEY,
    plaza       TEXT NOT NULL,
    patente     TEXT,                  -- NULL: plaza ocupada, patente sin leer
    ingreso     TEXT NOT NULL,
    egreso      TEXT,                  -- NULL mientras el auto sigue en la plaza
    lectura_id  INTEGER REFERENCES lecturas(id)
);
CREATE INDEX IF NOT EXISTS idx_estadias_patente ON estadias(patente, egreso);
CREATE INDEX IF NOT EXISTS idx_estadias_plaza ON estadias(plaza, egreso);
"""


class BaseDatos:
    def __init__(self, ruta):
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(ruta)
        self._con.row_factory = sqlite3.Row
        # WAL: el tótem puede leer mientras el pipeline escribe.
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.executescript(ESQUEMA)
        # Bases creadas antes de guardar el texto crudo del OCR.
        columnas = {fila[1] for fila in self._con.execute("PRAGMA table_info(lecturas)")}
        if "textos_ocr" not in columnas:
            self._con.execute("ALTER TABLE lecturas ADD COLUMN textos_ocr TEXT")

    def registrar_ingreso(self, lectura, momento):
        """Guarda la lectura y abre una estadía en la plaza. Devuelve el id de
        la estadía. Si la plaza ya tenía una estadía abierta (se perdió el
        evento de salida) la cierra antes."""
        with self._con:
            self._con.execute(
                "UPDATE estadias SET egreso = ? WHERE plaza = ? AND egreso IS NULL",
                (momento, lectura.plaza))
            cursor = self._con.execute(
                """INSERT INTO lecturas (momento, plaza, patente, formato, votos, capturas,
                       lecturas_crudas, textos_ocr, t_captura_ms, t_recorte_ms, t_ocr_ms, t_total_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (momento, lectura.plaza, lectura.patente, lectura.formato, lectura.votos,
                 lectura.capturas, json.dumps(lectura.crudas), json.dumps(lectura.textos_ocr),
                 lectura.tiempos_ms["captura"], lectura.tiempos_ms["recorte"],
                 lectura.tiempos_ms["ocr"], lectura.tiempos_ms["total"]))
            cursor = self._con.execute(
                "INSERT INTO estadias (plaza, patente, ingreso, lectura_id) VALUES (?, ?, ?, ?)",
                (lectura.plaza, lectura.patente, momento, cursor.lastrowid))
        return cursor.lastrowid

    def registrar_egreso(self, plaza, momento):
        """Cierra la estadía abierta de la plaza. Devuelve False si no había."""
        with self._con:
            cursor = self._con.execute(
                "UPDATE estadias SET egreso = ? WHERE plaza = ? AND egreso IS NULL",
                (momento, plaza))
        return cursor.rowcount > 0

    def buscar_patente(self, patente):
        """Estadía abierta de la patente (plaza, ingreso), o None."""
        return self._con.execute(
            "SELECT plaza, ingreso FROM estadias WHERE patente = ? AND egreso IS NULL",
            (patente,)).fetchone()

    def ocupacion(self):
        """Estadías abiertas, una por plaza ocupada."""
        return self._con.execute(
            "SELECT plaza, patente, ingreso FROM estadias WHERE egreso IS NULL ORDER BY plaza"
        ).fetchall()

    def cerrar(self):
        self._con.close()
