"""Feedback de un equipo frente a otro, sacado de la SQLite.

Compara línea a línea qué parte de las llamadas cumple cada equipo hasta el día
del feedback, ordena las líneas por distancia y convierte las que pasan del
umbral en llamadas a la acción: el consejo del formulario, el dato del equipo
de referencia como objetivo, citas de ese equipo haciéndolo bien (las elige
Jev con tools/muestra/ejemplos.py) y citas del equipo que recibe el feedback
donde se ve el fallo. Si hay datos posteriores, mide si la distancia se cerró.

Como el coaching, ningún texto de este informe lo ha escrito un modelo: las
frases son del formulario o de esta plantilla, y las citas, de las llamadas.
"""
from __future__ import annotations

import sqlite3

DISTANCIA_MINIMA = 15          # puntos de % cumplido para que una línea pida acción (decisión nuestra)
CITAS_POR_LINEA = 2
KPIS = ("duracion", "silencio", "interrupciones", "resuelto", "satisfaccion")
PORCENTAJE = {"resuelto", "satisfaccion"}


def informe(con: sqlite3.Connection, config: dict, *, dia: str, equipo: str, referencia: str) -> str:
    form, plantilla = config["formulario"], config["plantilla"]
    medidores = {m["id"]: m for m in config["kpis"]["medidores"]}
    nombre = {k: v["nombre"] for k, v in plantilla["equipos"].items()}
    hasta = f"{dia}T23:59:59"
    n = {e: _n(con, e, "<=", hasta) for e in (equipo, referencia)}
    out = [f"# Feedback al {nombre[equipo]} · {dia}", "",
           f"Qué hace mejor el {nombre[referencia]}, sacado de las llamadas hasta el {dia} "
           f"({n[referencia]} del {nombre[referencia]}, {n[equipo]} del {nombre[equipo]}).", ""]
    motores = {r[0] for r in con.execute("SELECT DISTINCT motor FROM llamadas")}
    if motores & {"simulado", "seco"}:
        out += ["> **Sin Jev (motor simulado o en seco).** Las decisiones son pseudoaleatorias: este informe prueba la "
                "fontanería, no mide a nadie.", ""]
    if not all(n.values()):
        return "\n".join(out + ["*Todavía no hay llamadas de los dos equipos.*"]) + "\n"

    filas = distancias(con, form, hasta, equipo, referencia)

    out += ["## Dónde está la distancia", "",
            f"% de llamadas que cumplen cada línea. Pide acción una distancia de {DISTANCIA_MINIMA} puntos o más.", "",
            f"| línea | {nombre[referencia]} | {nombre[equipo]} | distancia |", "|---|---|---|---|"]
    out += [f"| {l['id']} {l['texto']} | {ref:.0f} % | {eq:.0f} % | {d:+.0f} |" for l, ref, eq, d in filas]

    out += ["", "## KPIs en media", "",
            f"| indicador | {nombre[referencia]} | {nombre[equipo]} | objetivo |", "|---|---|---|---|"]
    for k in KPIS:
        m = medidores[k]
        ref, eq = (_kpi(con, k, e, "<=", hasta) for e in (referencia, equipo))
        out.append(f"| {m['texto']} | {_fmt(k, m, ref)} | {_fmt(k, m, eq)} | {_objetivo(m)} |")
    out += ["", "Los KPIs se juzgan en media, nunca por llamada: una llamada larga y excelente es buena.", ""]

    accion = [f for f in filas if f[3] >= DISTANCIA_MINIMA]
    out += ["## Llamadas a la acción", ""]
    if not accion:
        out.append(f"Ninguna línea separa a los equipos {DISTANCIA_MINIMA} puntos o más.")
    for i, (l, ref, eq, d) in enumerate(accion, 1):
        out += [f"### {i}. {l['texto']} ({l['id']}, {l['gravedad']})", "",
                f"- **El dato.** El {nombre[referencia]} la cumple en el {ref:.0f} % de sus llamadas; "
                f"el {nombre[equipo]}, en el {eq:.0f} %.",
                f"- **Qué hacer.** {l['consejo']}",
                f"- **Objetivo.** Llegar al {ref:.0f} % del {nombre[referencia]} en las próximas semanas."]
        for quien, cumple, rotulo in ((referencia, 1, f"Cómo lo hace el {nombre[referencia]}"),
                                      (equipo, 0, f"Dónde falla el {nombre[equipo]}")):
            citas = _citas(con, l["id"], quien, hasta, plantilla, cumple=cumple)
            if citas:
                out.append(f"- **{rotulo}:**")
                out += [f"  - {c}" for c in citas]
        out.append("")

    n_despues = _n(con, equipo, ">", hasta)
    if accion and n_despues:
        out += ["## Después del feedback", "",
                f"Las mismas líneas con las {n_despues} llamadas del {nombre[equipo]} posteriores al {dia}.", "",
                f"| línea | {nombre[equipo]} antes | {nombre[equipo]} después | {nombre[referencia]} después |",
                "|---|---|---|---|"]
        for l, ref, eq, d in accion:
            despues = _cumple(con, l["id"], equipo, ">", hasta)
            ref_despues = _cumple(con, l["id"], referencia, ">", hasta)
            out.append(f"| {l['id']} {l['texto']} | {eq:.0f} % | {despues:.0f} % | {ref_despues:.0f} % |")
        out.append("")
    return "\n".join(out) + "\n"


def distancias(con, form: dict, hasta: str, equipo: str, referencia: str) -> list[tuple]:
    """Línea a línea, % de llamadas que la cumplen: (línea, referencia, equipo, distancia), de mayor a menor."""
    filas = []
    for l in form["lineas"]:
        ref, eq = (_cumple(con, l["id"], e, "<=", hasta) for e in (referencia, equipo))
        filas.append((l, ref, eq, ref - eq))
    return sorted(filas, key=lambda f: -f[3])


def para_ejemplo(con, linea_id: str, equipo: str, hasta: str) -> list[str]:
    """Llamadas del equipo que cumplen la línea con seguridad, la nota más alta primero, una por agente."""
    filas = con.execute(
        "SELECT l.llamada_id, c.agente_id FROM lineas l JOIN llamadas c ON c.id = l.llamada_id"
        " WHERE l.linea_id = ? AND c.equipo = ? AND c.fecha <= ? AND l.cumple = 1 AND l.dudoso = 0"
        " ORDER BY l.valor DESC, c.fecha", (linea_id, equipo, hasta)).fetchall()
    elegidas, agentes = [], set()
    for llamada_id, agente in filas:
        if agente not in agentes and len(elegidas) < CITAS_POR_LINEA:
            agentes.add(agente)
            elegidas.append(llamada_id)
    return elegidas


def _n(con, equipo: str, op: str, hasta: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM llamadas WHERE equipo = ? AND fecha {op} ?", (equipo, hasta)).fetchone()[0]


def _cumple(con, linea_id: str, equipo: str, op: str, hasta: str) -> float:
    v = con.execute(f"SELECT AVG(l.cumple) FROM lineas l JOIN llamadas c ON c.id = l.llamada_id"
                    f" WHERE l.linea_id = ? AND c.equipo = ? AND c.fecha {op} ?", (linea_id, equipo, hasta)).fetchone()[0]
    return 100 * (v or 0)


def _kpi(con, kpi_id: str, equipo: str, op: str, hasta: str) -> float | None:
    return con.execute(f"SELECT AVG(k.valor) FROM kpis k JOIN llamadas c ON c.id = k.llamada_id"
                       f" WHERE k.kpi_id = ? AND c.equipo = ? AND c.fecha {op} ?", (kpi_id, equipo, hasta)).fetchone()[0]


def _citas(con, linea_id: str, equipo: str, hasta: str, plantilla: dict, *, cumple: int) -> list[str]:
    """Citas seguras (no dudosas) de fallos o de ejemplos, de agentes distintos."""
    filas = con.execute(
        "SELECT l.llamada_id, l.turno, l.cita, c.agente_id FROM lineas l JOIN llamadas c ON c.id = l.llamada_id"
        " WHERE l.linea_id = ? AND c.equipo = ? AND c.fecha <= ? AND l.cumple = ? AND l.dudoso = 0"
        " AND l.cita IS NOT NULL ORDER BY c.fecha", (linea_id, equipo, hasta, cumple)).fetchall()
    elegidas, agentes = [], set()
    for f in filas:
        if len(elegidas) == CITAS_POR_LINEA:
            break
        if f[3] in agentes:
            continue
        agentes.add(f[3])
        elegidas.append(f"{plantilla['agentes'][f[3]]['nombre']}, {f[0][:10]} {f[1]}: «{f[2]}»")
    return elegidas


def _fmt(k: str, m: dict, v: float | None) -> str:
    if v is None:
        return "—"
    if k in PORCENTAJE:
        return f"{100 * v:.0f} %"
    return f"{v:.1f}".replace(".", ",") if k == "interrupciones" else f"{v:.0f} {m['unidad']}"


def _objetivo(m: dict) -> str:
    u = f" {m['unidad']}" if m["unidad"] else ""
    if m["mejor"] == "cerca":
        return f"{m['objetivo']}{u} ±{100 * m['margen']:.0f} %"
    return f"{'≤' if m['mejor'] == 'menor' else '≥'} {m['objetivo']}{u}".replace(".", ",")
