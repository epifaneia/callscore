"""Catálogo de la muestra: comprueba la cobertura y genera diseno/catalogo.html.

    python tools/muestra/catalogo.py

Lee diseno/catalogo.json (factores, reglas, perfiles) y comprueba, sin azar:

  · cada perfil fija un nivel válido para cada factor;
  · cada perfil cumple las reglas de coherencia (p. ej. G3=0 → 3+ interrupciones);
  · cada nivel de cada factor sale en al menos un perfil.

Calcula la nota de calidad esperada de cada perfil con las mismas funciones
del paso 5, alimentadas con la respuesta que daría un Jev perfecto. Es la verdad
de referencia contra la que se medirá al Jev real. Los KPIs no tienen nota por
llamada: se juzgan en media. Sale con 1 si algo falla.
"""
from __future__ import annotations

import html
import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from pipeline import s2_contexto as s2                # noqa: E402
from pipeline import s5_guardarrail_out as s5        # noqa: E402

SEGURO = {"si": 0.95, "na": 0.95, "no": 0.05}       # lo que respondería un Jev sin dudas


def comprobar(cat: dict) -> list[str]:
    errores = []
    niveles = {f["id"]: {n["id"] for n in f["niveles"]} for f in cat["factores"]}
    for p in cat["perfiles"]:
        valores = {**p["niveles"], "motivo": p["motivo"]}
        for fid, validos in niveles.items():
            if valores.get(fid) not in validos:
                errores.append(f"{p['id']}: {fid}={valores.get(fid)!r} no es un nivel de {sorted(validos)}")
        for r in cat["reglas"]:
            if all(valores.get(k) == v for k, v in r["si"].items()) and \
                    any(valores.get(k) != v for k, v in r["entonces"].items()):
                errores.append(f"{p['id']}: incumple la regla «{r['porque']}»")
    for fid, n in cobertura(cat).items():
        errores += [f"{fid}={nivel}: ningún perfil lo cubre" for nivel, perfiles in n.items() if not perfiles]
    return errores


def cobertura(cat: dict) -> dict:
    cub = {f["id"]: {n["id"]: [] for n in f["niveles"]} for f in cat["factores"]}
    for p in cat["perfiles"]:
        for fid, nivel in {**p["niveles"], "motivo": p["motivo"]}.items():
            if fid in cub and nivel in cub[fid]:
                cub[fid][nivel].append(p["id"])
    return cub


def nota_esperada(perfil: dict, cat: dict, config: dict) -> dict:
    form = config["formulario"]
    v = perfil["niveles"]
    ans = {}
    for l in form["lineas"]:
        if l["tipo"] == "noul":
            ans[l["id"]] = {"noul": SEGURO[v[l["id"]]]}
        else:
            ans[l["id"]] = {"score": float(v[l["id"]]), "confidence": 0.9}
    lineas = s5.sellar_calidad(ans, form)
    return {**s5.nota_calidad(lineas), "fallos": [l["linea_id"] for l in lineas if not l["cumple"]]}


def mejores(cat: dict, config: dict) -> list[dict]:
    """Los perfiles de calidad máxima, de la llamada más larga a la más corta."""
    duracion = {n["id"]: n["valor"] for f in cat["factores"] if f["id"] == "duracion" for n in f["niveles"]}
    tope = max(nota_esperada(p, cat, config)["nota_calidad"] for p in cat["perfiles"])
    return sorted((p for p in cat["perfiles"] if nota_esperada(p, cat, config)["nota_calidad"] == tope),
                  key=lambda p: -duracion[p["niveles"]["duracion"]])


CSS = """
:root { --papel:#F7F5F0; --tinta:#1F2328; --tinta-2:#55524C; --muda:#8A8780; --linea:#E3E0D8;
        --logro:#E3F0EA; --logro-t:#0B6E4F; --error:#F6E3DE; --error-t:#9A3218; }
body { background:var(--papel); color:var(--tinta); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
       margin:0 auto; max-width:1180px; padding:24px 16px 48px; }
h1 { font-size:22px; margin:0 0 6px; } h2 { font-size:18px; margin:36px 0 8px; } h3 { font-size:15px; margin:20px 0 6px; }
p { max-width:760px; } .sub { color:var(--tinta-2); }
.ok { border-left:3px solid var(--logro-t); padding:6px 12px; background:var(--logro); }
.mal { border-left:3px solid var(--error-t); padding:6px 12px; background:var(--error); }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; font-size:13px; font-variant-numeric:tabular-nums; }
th, td { text-align:left; padding:5px 8px; border-bottom:1px solid var(--linea); vertical-align:top; }
th { color:var(--tinta-2); font-weight:600; }
.factores td:first-child { white-space:nowrap; font-weight:600; }
.matriz td, .matriz th { text-align:center; white-space:nowrap; }
.matriz td:nth-child(-n+2), .matriz th:nth-child(-n+2) { text-align:left; }
.l { background:var(--logro); color:var(--logro-t); font-weight:600; }
.e { background:var(--error); color:var(--error-t); font-weight:600; }
.tag { font-size:11px; padding:1px 6px; border-radius:4px; margin-left:6px; }
.quien { color:var(--muda); font-size:12px; }
.ley span { display:inline-block; padding:2px 8px; border-radius:4px; margin-right:8px; font-size:13px; }
"""


def _clase(nivel: dict) -> str:
    return "l" if nivel.get("logro") is True else "e" if nivel.get("logro") is False else ""


def render(cat: dict, config: dict, errores: list[str]) -> str:
    fac = {f["id"]: f for f in cat["factores"]}
    nivel = {f["id"]: {n["id"]: n for n in f["niveles"]} for f in cat["factores"]}
    cub = cobertura(cat)
    perfiles = [(p, nota_esperada(p, cat, config)) for p in cat["perfiles"]]
    out = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
           f"<title>Catálogo de la muestra</title><style>{CSS}</style></head><body>",
           "<h1>Catálogo de la muestra</h1>",
           "<p class='sub'>Todo lo que puede pasar en una llamada de la muestra, y las combinaciones fijas que lo cubren. "
           "Nada es aleatorio. La nota esperada de cada perfil sale de las mismas fórmulas del pipeline con las respuestas "
           "de un Jev perfecto: es la verdad contra la que se mide al Jev real.</p>"]
    total = sum(len(n) for n in cub.values())
    out.append(f"<p class='ok'>Cobertura completa: los {total} niveles de los {len(cub)} factores salen en al menos "
               f"uno de los {len(perfiles)} perfiles. Reglas de coherencia: todas cumplidas.</p>" if not errores else
               "<div class='mal'><b>Fallos de cobertura o coherencia:</b><ul>" +
               "".join(f"<li>{html.escape(e)}</li>" for e in errores) + "</ul></div>")
    out.append("<p class='ley'><span class='l'>logro</span><span class='e'>error</span><span>neutro / no aplica</span></p>")

    # 1 · Factores
    out.append("<h2>1 · Factores y niveles</h2>")
    for grupo, titulo in (("calidad", "Formulario de calidad"), ("kpi", "KPIs"), ("contexto", "Contexto")):
        out.append(f"<h3>{titulo}</h3><div class='scroll'><table class='factores'><tr><th>Factor</th><th>Nivel</th>"
                   "<th>Qué pasa en la llamada</th><th>Perfiles</th></tr>")
        for f in (f for f in cat["factores"] if f["grupo"] == grupo):
            for i, n in enumerate(f["niveles"]):
                cab = (f"{f['id'] if f['id'][0] in 'EGN' else ''} {html.escape(f['nombre'])}"
                       + ("<span class='tag e'>eliminatoria</span>" if f.get("eliminatoria") else "")) if i == 0 else ""
                out.append(f"<tr><td>{cab}</td><td class='{_clase(n)}'>{html.escape(n['id'])}</td>"
                           f"<td>{html.escape(n['texto'])}</td><td class='quien'>{', '.join(cub[f['id']][n['id']])}</td></tr>")
        out.append("</table></div>")

    # 2 · Reglas
    out.append("<h2>2 · Reglas de coherencia</h2><ul>")
    for r in cat["reglas"]:
        si = ", ".join(f"{k} = {v}" for k, v in r["si"].items())
        ent = ", ".join(f"{k} = {v}" for k, v in r["entonces"].items())
        out.append(f"<li>Si {si}, entonces {ent}: {html.escape(r['porque'])}.</li>")
    out.append("</ul>")

    # 3 · Matriz
    cols = [f["id"] for f in cat["factores"] if f["grupo"] != "contexto"]
    out.append("<h2>3 · Perfiles de llamada</h2><p class='sub'>Cada fila fija un nivel por factor. "
               "Varios puntos por llamada: casi todos los perfiles mezclan logros y errores.</p>"
               "<div class='scroll'><table class='matriz'><tr><th>Perfil</th><th>Motivo</th>" +
               "".join(f"<th title='{html.escape(fac[c]['nombre'])}'>{c if c[0] in 'EGN' else html.escape(fac[c]['nombre'].split()[0].lower())}</th>" for c in cols) +
               "<th>Calidad esperada</th></tr>")
    for p, nota in perfiles:
        celdas = "".join(f"<td class='{_clase(nivel[c][p['niveles'][c]])}'>{p['niveles'][c]}</td>" for c in cols)
        calidad = "<td class='e'>0 · eliminada</td>" if nota["eliminada"] else f"<td>{nota['nota_calidad']:.1f}</td>"
        out.append(f"<tr><td><b>{p['id']}</b> {html.escape(p['nombre'])}</td><td>{p['motivo']}</td>{celdas}"
                   f"{calidad}</tr>")
    out.append("</table></div>")

    # 4 · Conclusión
    top = mejores(cat, config)
    larga = top[0]
    out.append("<h2>4 · La mejor llamada</h2>"
               f"<p>Las mejores llamadas de la muestra son {', '.join(p['id'] + ' ' + p['nombre'] for p in top)}: "
               f"calidad 10 sobre 10. La más larga de todas es <b>{larga['id']} {html.escape(larga['nombre'])}</b>: "
               f"{html.escape(larga['resumen'])}</p>"
               "<p><b>Conclusión: una llamada larga y excelente es natural y buena.</b> Las mejores llamadas son las "
               "difíciles, y por definición necesitan más tiempo. Por eso la duración no puntúa ninguna llamada: es un "
               "KPI y los KPIs solo se juzgan en media, por semana, agente y equipo, frente al objetivo del servicio. "
               "La calidad, en cambio, sí se juzga llamada a llamada: una verificación que falta es un fallo sin "
               "más contexto.</p>")

    out.append("<h3>Qué pasa en cada perfil</h3><div class='scroll'><table><tr><th>Perfil</th><th>Resumen</th>"
               "<th>Líneas que fallan</th></tr>")
    for p, nota in perfiles:
        out.append(f"<tr><td><b>{p['id']}</b> {html.escape(p['nombre'])}</td><td>{html.escape(p['resumen'])}</td>"
                   f"<td>{', '.join(nota['fallos']) or '—'}</td></tr>")
    out.append("</table></div></body></html>")
    return "\n".join(out)


def main() -> int:
    cat = json.loads((RAIZ / "diseno" / "catalogo.json").read_text(encoding="utf-8"))
    config = s2.cargar_config(RAIZ / "config")
    errores = comprobar(cat)
    (RAIZ / "diseno" / "catalogo.html").write_text(render(cat, config, errores), encoding="utf-8")
    for e in errores:
        print("FALLO", e)
    for p in cat["perfiles"]:
        n = nota_esperada(p, cat, config)
        calidad = "ELIMINADA" if n["eliminada"] else f"{n['nota_calidad']:.1f}"
        print(f"{p['id']} {p['nombre']:<22} calidad {calidad:<9} {p['niveles']['duracion']:<9} fallan {','.join(n['fallos']) or '-'}")
    print("diseno/catalogo.html", "· cobertura completa" if not errores else f"· {len(errores)} fallos")
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
