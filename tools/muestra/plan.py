"""Plan de la muestra: despliega diseno/reparto.json en llamadas fechadas y lo comprueba.

    python tools/muestra/plan.py

Escribe diseno/plan.json (una entrada por llamada: id, fecha, día, semana,
agente, equipo, perfil y guion) y diseno/plan.html (el plan día a día, con la
nota esperada de cada llamada y lo que debería verse en los datos).

Comprueba, sin azar, lo que se pidió al diseño:
  · los doce perfiles aparecen, así que la muestra cubre todos los niveles;
  · el Equipo Norte va por delante en nota esperada todas las semanas;
  · el Equipo Sur mejora tras el feedback, en nota y en las líneas que el
    reparto declara (feedback.mejoran), que deben ser de las que el Norte le
    sacaba ventaja antes del feedback;
  · ninguna otra línea del Sur cae más de 15 puntos tras el feedback: los datos
    no deben sugerir que el feedback empeoró algo que no se diseñó así.
Sale con 1 si algo falla.
"""
from __future__ import annotations

import html
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools" / "muestra"))

from pipeline import s2_contexto as s2               # noqa: E402
from catalogo import CSS, nota_esperada              # noqa: E402

DIAS = "lunes martes miércoles jueves viernes".split()


def desplegar(rep: dict, cat: dict, plantilla: dict) -> list[dict]:
    inicio = date.fromisoformat(rep["inicio"])
    usos: Counter = Counter()
    llamadas = []
    for semana in range(rep["semanas"]):
        for d in range(5):
            fecha = inicio + timedelta(weeks=semana, days=d)
            for aid, semanas in rep["agentes"].items():
                perfil = semanas[semana][d]
                variante = "ab"[usos[perfil] % rep["variantes"]]
                usos[perfil] += 1
                llamadas.append({
                    "id": f"{fecha.isoformat()}_{aid}", "fecha": f"{fecha.isoformat()}T{rep['hora_por_agente'][aid]}:00",
                    "dia": semana * 5 + d + 1, "semana": semana + 1, "agente_id": aid,
                    "equipo": plantilla["agentes"][aid]["equipo"], "perfil": perfil, "guion": f"{perfil}{variante}"})
    return llamadas


def resumen(llamadas: list[dict], cat: dict, config: dict) -> dict:
    """Medias esperadas por (equipo, semana) y cumplimiento esperado por línea y fase."""
    perfiles = {p["id"]: p for p in cat["perfiles"]}
    nota = {pid: nota_esperada(p, cat, config) for pid, p in perfiles.items()}
    semana = defaultdict(list)
    lineas = defaultdict(lambda: [0, 0])
    for c in llamadas:
        n = nota[c["perfil"]]
        semana[(c["equipo"], c["semana"])].append(n["nota_calidad"])
        fase = "antes" if c["semana"] <= 2 else "despues"
        for l in config["formulario"]["lineas"]:
            lineas[(c["equipo"], fase, l["id"])][0] += l["id"] not in n["fallos"]
            lineas[(c["equipo"], fase, l["id"])][1] += 1
    return {"nota": nota, "semana": {k: sum(v) / len(v) for k, v in semana.items()},
            "eliminadas": {k: sum(x == 0 for x in v) for k, v in semana.items()},
            "lineas": {k: 100 * a / b for k, (a, b) in lineas.items()}}


def comprobar(llamadas: list[dict], rep: dict, cat: dict, r: dict, config: dict) -> list[str]:
    errores = []
    for aid, semanas in rep["agentes"].items():
        if len(semanas) != rep["semanas"] or any(len(s) != 5 for s in semanas):
            errores.append(f"{aid}: hacen falta {rep['semanas']} semanas de 5 días")
    faltan = {p["id"] for p in cat["perfiles"]} - {c["perfil"] for c in llamadas}
    errores += [f"el perfil {p} no aparece en la muestra" for p in sorted(faltan)]
    for s in range(1, rep["semanas"] + 1):
        if r["semana"][("norte", s)] <= r["semana"][("sur", s)]:
            errores.append(f"semana {s}: el Norte no va por delante")
    antes = [r["semana"][("sur", s)] for s in (1, 2)]
    despues = [r["semana"][("sur", s)] for s in range(3, rep["semanas"] + 1)]
    if min(despues) <= max(antes):
        errores.append("el Sur no mejora tras el feedback en todas las semanas")
    ventaja = ventaja_norte(r, config)
    for l in rep["feedback"]["mejoran"]:
        if l not in ventaja:
            errores.append(f"{l}: se diseña como mejora del feedback, pero el Norte no le saca ventaja antes")
        elif r["lineas"][("sur", "despues", l)] <= r["lineas"][("sur", "antes", l)]:
            errores.append(f"{l}: el Sur no mejora tras el feedback")
    for l in config["formulario"]["lineas"]:
        caida = r["lineas"][("sur", "antes", l["id"])] - r["lineas"][("sur", "despues", l["id"])]
        if l["id"] not in rep["feedback"]["mejoran"] and caida > 15:
            errores.append(f"{l['id']}: el Sur cae {caida:.0f} puntos tras el feedback sin que el diseño lo pida")
    return errores


def ventaja_norte(r: dict, config: dict, minimo: float = 15) -> list[str]:
    """Líneas donde el Norte cumple al menos `minimo` puntos más que el Sur antes del feedback."""
    return [l["id"] for l in config["formulario"]["lineas"]
            if r["lineas"][("norte", "antes", l["id"])] - r["lineas"][("sur", "antes", l["id"])] >= minimo]


def render(llamadas: list[dict], rep: dict, cat: dict, config: dict, r: dict, errores: list[str]) -> str:
    plantilla = config["plantilla"]
    perfiles = {p["id"]: p for p in cat["perfiles"]}
    texto_linea = {l["id"]: l["texto"] for l in config["formulario"]["lineas"]}
    ventaja = ventaja_norte(r, config)
    out = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width, initial-scale=1'><title>Plan de la muestra</title>"
           f"<style>{CSS}.dia{{margin:18px 0 6px}} .fb{{border-left:3px solid var(--tinta);padding:6px 12px;background:#EFECE4}}"
           f" nav a{{margin-right:12px}}</style></head><body>",
           "<h1>Plan de la muestra</h1>",
           f"<p class='sub'>{len(llamadas)} llamadas en {rep['semanas']} semanas de lunes a viernes, una por agente y día. "
           "Nada aleatorio: el reparto está escrito a mano en <code>diseno/reparto.json</code>. Cada llamada sale de un "
           "perfil del catálogo; su nota esperada es la verdad contra la que se mide a Jev.</p>"]
    out.append("<p class='ok'>Comprobado: los doce perfiles aparecen, el Norte va por delante todas las semanas y el Sur "
               "mejora tras el feedback en nota y en las líneas trabajadas: " + ", ".join(rep["feedback"]["mejoran"]) + ".</p>" if not errores else
               "<div class='mal'><b>El plan no cumple el diseño:</b><ul>" +
               "".join(f"<li>{html.escape(e)}</li>" for e in errores) + "</ul></div>")

    out.append("<h2>Lo que deberían enseñar los datos</h2><div class='scroll'><table><tr><th>Semana</th>"
               "<th>Norte · calidad esperada</th><th>Sur · calidad esperada</th><th>Eliminadas Norte</th><th>Eliminadas Sur</th></tr>")
    for s in range(1, rep["semanas"] + 1):
        marca = " · feedback al Sur" if s == 2 else ""
        out.append(f"<tr><td>{s}{marca}</td><td>{r['semana'][('norte', s)]:.1f}</td><td>{r['semana'][('sur', s)]:.1f}</td>"
                   f"<td>{r['eliminadas'][('norte', s)]}</td><td>{r['eliminadas'][('sur', s)]}</td></tr>")
    out.append("</table></div>")

    out.append("<h3>Cumplimiento esperado por línea</h3><p class='sub'>Las líneas marcadas son en las que el Norte saca "
               "15 puntos o más al Sur antes del feedback: de ahí debe salir el feedback. Las trabajadas tras el feedback "
               "son " + ", ".join(rep["feedback"]["mejoran"]) + "; ninguna otra cae más de 15 puntos.</p>"
               "<div class='scroll'><table><tr><th>Línea</th><th>Norte</th><th>Sur, semanas 1-2</th><th>Sur, semanas 3-4</th></tr>")
    for l in config["formulario"]["lineas"]:
        clase = " class='e'" if l["id"] in ventaja else ""
        out.append(f"<tr><td{clase}>{l['id']} {html.escape(texto_linea[l['id']])}</td>"
                   f"<td>{(r['lineas'][('norte', 'antes', l['id'])] + r['lineas'][('norte', 'despues', l['id'])]) / 2:.0f} %</td>"
                   f"<td>{r['lineas'][('sur', 'antes', l['id'])]:.0f} %</td><td>{r['lineas'][('sur', 'despues', l['id'])]:.0f} %</td></tr>")
    out.append("</table></div>")

    out.append("<h2>Día a día</h2><nav>" + "".join(f"<a href='#s{s}'>Semana {s}</a>" for s in range(1, rep["semanas"] + 1))
               + "</nav>")
    por_dia = defaultdict(list)
    for c in llamadas:
        por_dia[c["dia"]].append(c)
    for dia, cs in sorted(por_dia.items()):
        f = date.fromisoformat(cs[0]["fecha"][:10])
        if f.weekday() == 0:
            out.append(f"<h3 id='s{cs[0]['semana']}'>Semana {cs[0]['semana']}</h3>")
        out.append(f"<p class='dia'><b>Día {dia}</b> · {DIAS[f.weekday()]} {f.day}/{f.month}</p>"
                   "<div class='scroll'><table><tr><th>Agente</th><th>Equipo</th><th>Perfil</th><th>Guion</th>"
                   "<th>Calidad esperada</th></tr>")
        for c in cs:
            n = r["nota"][c["perfil"]]
            nota = "<td class='e'>0 · eliminada</td>" if n["eliminada"] else \
                f"<td class='{'l' if n['nota_calidad'] == 10 else ''}'>{n['nota_calidad']:.1f}</td>"
            out.append(f"<tr><td>{html.escape(plantilla['agentes'][c['agente_id']]['nombre'])}</td>"
                       f"<td>{html.escape(plantilla['equipos'][c['equipo']]['nombre'])}</td>"
                       f"<td>{c['perfil']} {html.escape(perfiles[c['perfil']]['nombre'])}</td><td>{c['guion']}</td>{nota}</tr>")
        out.append("</table></div>")
        if f.isoformat() == rep["feedback"]["dia"]:
            out.append(f"<p class='fb'><b>Fin del día {dia}:</b> {html.escape(rep['feedback']['texto'])}</p>")
    out.append("</body></html>")
    return "\n".join(out)


def main() -> int:
    rep = json.loads((RAIZ / "diseno" / "reparto.json").read_text(encoding="utf-8"))
    cat = json.loads((RAIZ / "diseno" / "catalogo.json").read_text(encoding="utf-8"))
    config = s2.cargar_config(RAIZ / "config")
    llamadas = desplegar(rep, cat, config["plantilla"])
    r = resumen(llamadas, cat, config)
    errores = comprobar(llamadas, rep, cat, r, config)
    (RAIZ / "diseno" / "plan.json").write_text(json.dumps(
        {"feedback": rep["feedback"], "llamadas": llamadas}, ensure_ascii=False, indent=1), encoding="utf-8")
    (RAIZ / "diseno" / "plan.html").write_text(render(llamadas, rep, cat, config, r, errores), encoding="utf-8")
    for s in range(1, rep["semanas"] + 1):
        print(f"semana {s}: Norte {r['semana'][('norte', s)]:.1f} · Sur {r['semana'][('sur', s)]:.1f}")
    print("ventaja del Norte antes del feedback:", ", ".join(ventaja_norte(r, config)))
    guiones = sorted({c["guion"] for c in llamadas})
    print(f"{len(llamadas)} llamadas · {len(guiones)} guiones distintos: {' '.join(guiones)}")
    for e in errores:
        print("FALLO", e)
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
