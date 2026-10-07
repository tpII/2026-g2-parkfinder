"""Muestra el contenido de una base SQLite de ParkFinder: plazas ocupadas,
historial de estadías y últimas lecturas con su latencia.

Uso: python ver_base.py [ruta.db]   (por defecto ../datos/parkfinder.db)
"""

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def main():
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "datos" / "parkfinder.db"
    if not ruta.exists():
        raise SystemExit(f"No existe la base {ruta}")
    con = sqlite3.connect(ruta)

    print("== Plazas ocupadas (lo que consulta el tótem)")
    filas = con.execute("SELECT plaza, patente, ingreso FROM estadias WHERE egreso IS NULL ORDER BY plaza").fetchall()
    for plaza, patente, ingreso in filas:
        print(f"   plaza {plaza}: {patente or 'patente sin leer'} desde {ingreso}")
    if not filas:
        print("   (ninguna)")

    print("\n== Historial de estadías")
    for id_, plaza, patente, ingreso, egreso in con.execute(
            "SELECT id, plaza, patente, ingreso, egreso FROM estadias ORDER BY id"):
        print(f"   #{id_} plaza {plaza}: {patente or 'sin leer':8s} ingreso {ingreso}  egreso {egreso or '—'}")

    print("\n== Últimas lecturas")
    columnas = {fila[1] for fila in con.execute("PRAGMA table_info(lecturas)")}
    crudo = "textos_ocr" if "textos_ocr" in columnas else "NULL"
    for momento, plaza, patente, votos, capturas, crudas, textos, total in con.execute(
            f"""SELECT momento, plaza, patente, votos, capturas, lecturas_crudas, {crudo}, t_total_ms
               FROM lecturas ORDER BY id DESC LIMIT 10"""):
        ocr = f"  OCR crudo {textos}" if textos and textos != crudas else ""
        print(f"   {momento} plaza {plaza}: {patente or 'sin leer':8s} {votos}/{capturas} votos "
              f"{crudas}{ocr}  {total:.0f} ms")
    con.close()


if __name__ == "__main__":
    main()
