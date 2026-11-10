"""Sesiones de coaching: agentes ordenados por la gravedad de sus faltas.

Gravedad de un agente = suma del peso de sus fallos (eliminatoria 3, grave 2,
leve 1). Cada punto de mejora es el consejo escrito de antemano en el
formulario, con la cita literal del turno que lo demuestra. Ningún texto de
este informe lo ha escrito un modelo.

Los fallos dudosos no suman: van aparte, pendientes de revisión humana.
"""
from __future__ import annotations

import sqlite3


def informe(con: sqlite3.Connection, config: dict) -> str:
    form, plantilla = config["formulario"], config["plantilla"]
    lineas = {l["id"]: l for l in form["lineas"]}
    peso = form["gravedad_peso"]
    filas = con.execute(
        "SELECT l.*, c.agente_id, c.fecha, c.motor FROM lineas l JOIN llamadas c ON c.id = l.llamada_id"
        " WHERE l.cumple = 0 ORDER BY c.fecha").fetchall()
    motores = {r[0] for r in con.execute("SELECT DISTINCT motor FROM llamadas")}

    por_agente: dict[str, dict] = {}
    for f in filas:
        a = por_agente.setdefault(f["agente_id"], {"gravedad": 0, "fallos": [], "dudosos": []})
        if f["dudoso"]:
            a["dudosos"].append(f)
        else:
            a["gravedad"] += peso[f["gravedad"]]
            a["fallos"].append(f)

    out = ["# Sesiones de coaching", ""]
    if motores & {"simulado", "seco"}:
        out += ["> **Sin Jev (motor simulado o en seco).** Las decisiones son pseudoaleatorias: este informe prueba la "
                "fontanería, no mide a nadie.", ""]
    ranking = sorted(por_agente.items(), key=lambda kv: -kv[1]["gravedad"])
    for pos, (aid, a) in enumerate(ranking, 1):
        ag = plantilla["agentes"][aid]
        equipo = plantilla["equipos"][ag["equipo"]]["nombre"]
        out += [f"## {pos}. {ag['nombre']} · {equipo} · gravedad {a['gravedad']}", ""]
        for f in sorted(a["fallos"], key=lambda f: -peso[f["gravedad"]]):
            out.append(_punto(f, lineas))
        if a["dudosos"]:
            out += ["", "*Pendiente de revisión humana:*"]
            out += [_punto(f, lineas) for f in a["dudosos"]]
        out.append("")
    return "\n".join(out) + "\n"


def _punto(f: sqlite3.Row, lineas: dict) -> str:
    l = lineas[f["linea_id"]]
    cita = f" — {f['llamada_id']} {f['turno']}: «{f['cita']}»" if f["cita"] else f" — {f['llamada_id']}: sin turno que lo muestre"
    return f"- **[{f['gravedad']}] {l['texto']}.** {l['consejo']}{cita}"
