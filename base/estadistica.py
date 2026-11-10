"""Evolución por semana de agentes y equipos, desde la SQLite → data/estadistica.html.

Por semana ISO (la etiqueta es el lunes) y por equipo o agente:

  · Calidad, que sí se juzga llamada a llamada: nota media (una eliminada
    cuenta con su 0, como en cualquier formulario), porcentaje de eliminadas y
    cuántas siguen en revisión con nota provisional.
  · KPIs, que solo se juzgan en media: la media de la semana frente al
    objetivo del servicio (config/kpis.json). Una llamada larga y excelente
    no es mala; una media de duración desviada sí es una señal.

Gráficos en SVG generados aquí, sin librerías ni red: un color por equipo
(validado para daltonismo sobre el papel de la marca), el agente siempre del
color de su equipo, la media del equipo como referencia gris y el objetivo
como línea discontinua. Cada punto dice su valor y su n al pasar el ratón; la
tabla lleva todo.
"""
from __future__ import annotations

import html
import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

# Paleta: papel y tintas de la marca; series validadas (validate_palette.js, modo claro, sobre #F7F5F0)
COLOR_EQUIPO = ["#007BA8", "#B06C00"]
GRIS = "#8A8780"
MESES = "ene feb mar abr may jun jul ago sep oct nov dic".split()
PORCENTAJE = {"resuelto", "satisfaccion"}          # se guardan 1/0 por llamada; su media ×100 es el %


def _lunes(fecha: str) -> date:
    d = date.fromisoformat(fecha[:10])
    return d - timedelta(days=d.weekday())


def agregados(con: sqlite3.Connection) -> dict:
    """{('equipo'|'agente', id): {lunes: {n, calidad, eliminadas, revision, <kpi_id>...}}}"""
    acc: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    por_llamada = {}
    for r in con.execute("SELECT id, fecha, agente_id, equipo, nota_calidad, eliminada, estado FROM llamadas"):
        claves = (("equipo", r[3]), ("agente", r[2]))
        semana = _lunes(r[1])
        por_llamada[r[0]] = (claves, semana)
        for c in claves:
            a = acc[c][semana]
            a["n"] += 1
            a["calidad"] += r[4]
            a["eliminadas"] += r[5]
            a["revision"] += r[6] == "revision"
    for llamada_id, kpi_id, valor in con.execute("SELECT llamada_id, kpi_id, valor FROM kpis"):
        claves, semana = por_llamada[llamada_id]
        for c in claves:
            acc[c][semana][kpi_id] += valor * (100 if kpi_id in PORCENTAJE else 1)
    for serie in acc.values():
        for a in serie.values():
            for k in a:
                if k not in ("n", "eliminadas", "revision"):
                    a[k] /= a["n"]
    return acc


def _etiqueta(d: date) -> str:
    return f"{d.day} {MESES[d.month - 1]}"


def _num(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 10 or v == int(v) else f"{v:.1f}"


def _escala(valores: list[float], kpi: dict | None) -> tuple[float, list[float]]:
    """Máximo del eje y sus marcas: 0-10 para la calidad, 0-100 para %, y un techo redondo para el resto."""
    if kpi is None:
        return 10, [0, 5, 10]
    if kpi["unidad"] == "%":
        return 100, [0, 50, 100]
    alto = max(valores + [kpi["objetivo"] * (1 + kpi.get("margen", 0)) * 1.25, 1])
    paso = 10 ** math.floor(math.log10(alto))
    techo = math.ceil(alto / paso) * paso
    return techo, [0, techo / 2, techo]


def _grafico(series: list[dict], semanas: list[date], *, ancho: int, alto: int, titulo: str,
             etiquetas_directas: bool, max_fechas: int = 6, kpi: dict | None = None) -> str:
    """Líneas sobre una escala común. series: [{nombre, color, puntos: {lunes: (valor, n)}, referencia}]"""
    mi, md, ms, mb = 34, 96 if etiquetas_directas else 14, 26, 22
    w, h = ancho - mi - md, alto - ms - mb
    valores = [v for s in series for v, _ in s["puntos"].values()]
    techo, marcas = _escala(valores, kpi)
    x = (lambda i: mi + w / 2) if len(semanas) == 1 else (lambda i: mi + w * i / (len(semanas) - 1))
    y = lambda v: ms + h * (1 - min(v, techo) / techo)
    idx = {s: i for i, s in enumerate(semanas)}
    unidad = (kpi or {}).get("unidad", "")
    out = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="{html.escape(titulo)}">',
           f'<text x="{mi}" y="14" class="t">{html.escape(titulo)}</text>']
    for v in marcas:
        out.append(f'<line x1="{mi}" x2="{mi + w}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="{"base" if v == 0 else "grid"}"/>'
                   f'<text x="{mi - 6}" y="{y(v) + 4:.1f}" class="eje" text-anchor="end">{_num(v)}</text>')
    if kpi:
        obj = kpi["objetivo"]
        if "margen" in kpi:
            lo, hi = obj * (1 - kpi["margen"]), obj * (1 + kpi["margen"])
            out.append(f'<rect x="{mi}" y="{y(hi):.1f}" width="{w}" height="{y(lo) - y(hi):.1f}" class="banda"/>')
        out.append(f'<line x1="{mi}" x2="{mi + w}" y1="{y(obj):.1f}" y2="{y(obj):.1f}" class="obj"/>')
    paso = max(1, -(-len(semanas) // max_fechas))
    for i, s in enumerate(semanas):
        ultima = len(semanas) - 1
        if i == ultima or (i % paso == 0 and ultima - i >= paso):
            ancla = "middle" if len(semanas) == 1 else "start" if i == 0 else "end" if i == len(semanas) - 1 else "middle"
            out.append(f'<text x="{x(i):.1f}" y="{alto - 6}" class="eje" text-anchor="{ancla}">{_etiqueta(s)}</text>')
    etiquetas = []
    for s in series:
        pts = sorted((idx[k], v, n) for k, (v, n) in s["puntos"].items())
        clase = "ref" if s.get("referencia") else "serie"
        if len(pts) > 1:
            d = " ".join(f"{'M' if j == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for j, (i, v, _) in enumerate(pts))
            out.append(f'<path d="{d}" class="{clase}" stroke="{s["color"]}"/>')
        if not s.get("referencia"):
            for i, v, n in pts:
                out.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="{s["color"]}" class="pt">'
                           f'<title>{html.escape(s["nombre"])} · semana del {_etiqueta(semanas[i])}: '
                           f'{_num(v)}{unidad} ({int(n)} llamada{"s" if n != 1 else ""})</title></circle>')
            if etiquetas_directas and pts:
                i, v, _ = pts[-1]
                etiquetas.append([y(v) + 4, x(i) + 8, s["nombre"]])
    # etiquetas directas al final de cada línea, separadas al menos 14 px en vertical
    etiquetas.sort()
    for a, b in zip(etiquetas, etiquetas[1:]):
        b[0] = max(b[0], a[0] + 14)
    out += [f'<text x="{ex:.1f}" y="{ey:.1f}" class="lab">{html.escape(n)}</text>' for ey, ex, n in etiquetas]
    out.append("</svg>")
    return "".join(out)


CSS = """
:root { --papel:#F7F5F0; --tinta:#1F2328; --tinta-2:#55524C; --muda:#8A8780; --grid:#E3E0D8; --base:#C9C5BA; }
body { background:var(--papel); color:var(--tinta); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
       margin:0 auto; max-width:1080px; padding:24px 16px 48px; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:17px; margin:32px 0 8px; }
p { max-width:760px; } .sub { color:var(--tinta-2); margin:0 0 16px; }
.aviso { border-left:3px solid var(--tinta); padding:6px 12px; background:#EFECE4; }
.fila { display:grid; grid-template-columns:repeat(auto-fill, minmax(min(100%, 420px), 1fr)); gap:16px; }
.fila.mini { grid-template-columns:repeat(auto-fill, minmax(min(100%, 240px), 1fr)); }
.fila svg { display:block; width:100%; height:auto; background:#FBFAF7; border-radius:6px; }
.t { font-size:13px; font-weight:600; fill:var(--tinta); }
.eje { font-size:11px; fill:var(--muda); font-variant-numeric:tabular-nums; }
.lab { font-size:12px; fill:var(--tinta-2); }
.grid { stroke:var(--grid); stroke-width:1; } .base { stroke:var(--base); stroke-width:1; }
.obj { stroke:var(--tinta-2); stroke-width:1; stroke-dasharray:2 3; } .banda { fill:#ECE9E1; }
.serie { fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.ref { fill:none; stroke-width:1.5; stroke-dasharray:4 3; }
.pt { stroke:#FBFAF7; stroke-width:2; } .pt:hover { r:6; }
.ley { display:inline-flex; align-items:center; gap:6px; margin-right:16px; color:var(--tinta-2); font-size:13px; }
.ley i { width:12px; height:12px; border-radius:3px; display:inline-block; }
table { border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--grid); white-space:nowrap; }
th { color:var(--tinta-2); font-weight:600; }
.tabla { overflow-x:auto; }
"""


def informe(con: sqlite3.Connection, config: dict) -> str:
    plantilla, kpis = config["plantilla"], config["kpis"]["medidores"]
    acc = agregados(con)
    motores = {r[0] for r in con.execute("SELECT DISTINCT motor FROM llamadas")}
    semanas = sorted({s for serie in acc.values() for s in serie})
    equipos = list(plantilla["equipos"])
    color = {e: COLOR_EQUIPO[i] for i, e in enumerate(equipos)}

    def serie(tipo, ident, campo, nombre, col, **kw):
        return {"nombre": nombre, "color": col, **kw,
                "puntos": {s: (a[campo], a["n"]) for s, a in acc.get((tipo, ident), {}).items()}}

    def de_equipos(campo, titulo, kpi=None):
        return _grafico([serie("equipo", e, campo, plantilla["equipos"][e]["nombre"], color[e]) for e in equipos],
                        semanas, ancho=520, alto=240, titulo=titulo, etiquetas_directas=True, kpi=kpi)

    leyenda = "".join(f'<span class="ley"><i style="background:{color[e]}"></i>'
                      f'{html.escape(plantilla["equipos"][e]["nombre"])}</span>' for e in equipos)
    calidad = de_equipos("calidad", "Nota de calidad media")
    def titulo_kpi(m):
        margen = f" ±{100 * m['margen']:.0f} %" if "margen" in m else ""
        signo = {"menor": "≤ ", "mayor": "≥ ", "cerca": ""}[m["mejor"]]
        return f"{m['texto']} · objetivo {signo}{_num(m['objetivo'])}{m['unidad']}{margen}"

    graf_kpi = [de_equipos(m["id"], titulo_kpi(m), kpi=m) for m in kpis]

    mini = []
    for e in equipos:
        for aid, ag in plantilla["agentes"].items():
            if ag["equipo"] != e or ("agente", aid) not in acc:
                continue
            mini.append(_grafico(
                [serie("equipo", e, "calidad", "media del equipo", GRIS, referencia=True),
                 serie("agente", aid, "calidad", ag["nombre"], color[e])],
                semanas, ancho=300, alto=170, titulo=f'{ag["nombre"]} · {plantilla["equipos"][e]["nombre"]}',
                etiquetas_directas=False, max_fechas=3))

    cab_kpi = "".join(f"<th>{html.escape(m['texto'])}{' (' + m['unidad'] + ')' if m['unidad'] else ''}</th>" for m in kpis)
    filas = []
    for (tipo, ident), serie_ in sorted(acc.items(), key=lambda kv: (kv[0][0] != "equipo", kv[0][1])):
        nombre = (plantilla["equipos"][ident]["nombre"] if tipo == "equipo"
                  else plantilla["agentes"][ident]["nombre"])
        for s, a in sorted(serie_.items()):
            celdas_kpi = "".join(f"<td>{_num(a[m['id']])}</td>" for m in kpis)
            filas.append(f"<tr><td>{_etiqueta(s)}</td><td>{html.escape(nombre)}</td><td>{int(a['n'])}</td>"
                         f"<td>{a['calidad']:.1f}</td><td>{100 * a['eliminadas'] / a['n']:.0f} %</td>"
                         f"<td>{int(a['revision'])}</td>{celdas_kpi}</tr>")

    aviso = ('<p class="aviso"><b>Sin Jev (motor simulado o en seco).</b> Las decisiones son pseudoaleatorias: estas cifras '
             'prueban la fontanería, no miden a nadie.</p>') if motores & {"simulado", "seco"} else ""
    total = con.execute("SELECT COUNT(*) FROM llamadas").fetchone()[0]
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evolución de calidad</title><style>{CSS}</style></head><body>
<h1>Evolución de calidad por semana</h1>
<p class="sub">{total} llamadas · cada punto, al pasar el ratón, da su valor y cuántas llamadas lo forman.</p>
{aviso}
<h2>Calidad, llamada a llamada</h2>
<p class="sub">La calidad se juzga en cada llamada: una verificación que falta es un fallo sin más contexto.</p>
<div>{leyenda}</div>
<div class="fila">{calidad}</div>
<h2>KPIs, solo en media</h2>
<p class="sub">Un KPI no juzga una llamada: una llamada larga y excelente es natural y buena. Lo que se lee es la media de la
semana frente al objetivo del servicio (línea discontinua; la banda, el margen admitido).</p>
<div>{leyenda}</div>
<div class="fila">{"".join(graf_kpi)}</div>
<h2>Agentes · nota de calidad</h2>
<p class="sub">Línea de color: el agente. Discontinua gris: la media de su equipo.</p>
<div class="fila mini">{"".join(mini)}</div>
<h2>Tabla</h2>
<div class="tabla"><table><thead><tr><th>Semana</th><th>Equipo o agente</th><th>Llamadas</th><th>Calidad</th>
<th>Eliminadas</th><th>En revisión</th>{cab_kpi}</tr></thead><tbody>{"".join(filas)}</tbody></table></div>
</body></html>
"""
