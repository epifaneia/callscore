"""Base de datos de la catalogación: una fila por llamada, por línea y por KPI.

SQLite, un fichero, sin servidor. Reprocesar una llamada la sustituye entera.
De aquí comen la estadística (evolución por agente y equipo) y el coaching.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS llamadas (
    id TEXT PRIMARY KEY, fecha TEXT NOT NULL,
    agente_id TEXT NOT NULL, equipo TEXT NOT NULL,
    duracion_s REAL, nota_calidad REAL, eliminada INTEGER,
    estado TEXT, motor TEXT, modelo TEXT, procesado TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS lineas (
    llamada_id TEXT, linea_id TEXT, tipo TEXT, gravedad TEXT,
    valor REAL, confianza REAL, cumple INTEGER, dudoso INTEGER, turno TEXT, cita TEXT,
    PRIMARY KEY (llamada_id, linea_id)
);
CREATE TABLE IF NOT EXISTS kpis (
    llamada_id TEXT, kpi_id TEXT, fuente TEXT, valor REAL, dudoso INTEGER,
    PRIMARY KEY (llamada_id, kpi_id)
);
"""


def abrir(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def guardar(con: sqlite3.Connection, r: dict) -> None:
    with con:
        for tabla, col in (("lineas", "llamada_id"), ("kpis", "llamada_id"), ("llamadas", "id")):
            con.execute(f"DELETE FROM {tabla} WHERE {col} = ?", (r["id"],))
        con.execute(
            "INSERT INTO llamadas (id, fecha, agente_id, equipo,"
            " duracion_s, nota_calidad, eliminada, estado, motor, modelo)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["fecha"], r["agente_id"], r["equipo"], r["duracion_s"], r["nota_calidad"],
             r["eliminada"], r["estado"], r["motor"], r["modelo"]))
        con.executemany(
            "INSERT INTO lineas VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r["id"], l["linea_id"], l["tipo"], l["gravedad"], l["valor"], l["confianza"],
              l["cumple"], l["dudoso"], l.get("turno"), l.get("cita")) for l in r["lineas"]])
        con.executemany(
            "INSERT INTO kpis VALUES (?,?,?,?,?)",
            [(r["id"], k["kpi_id"], k["fuente"], k["valor"], k["dudoso"]) for k in r["kpis"]])
