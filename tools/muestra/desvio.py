"""Desvío de Jev frente al diseño de la muestra, escrito en el README.

    python tools/muestra/desvio.py                  # data/jev.db + diseno/plan.json
    python tools/muestra/desvio.py --db X.db --plan plan.json

La verdad es el diseño: el plan dice de qué perfil sale cada llamada, y el perfil
(diseno/catalogo.json) fija qué cumple y qué falla en esa llamada. El diseño lo
escribió un modelo grande y se revisó a mano; Jev no lo ve nunca. Aquí se
compara, llamada a llamada, lo que decidió Jev con lo diseñado:

  · por línea de calidad: acuerdo en cumple / falla, y de los desacuerdos,
    cuántos marcó el guardarraíl como dudosos (van a revisión humana) y
    cuántos pasaron sin marcar (los que de verdad se cuelan);
  · eliminatorias: cuántas diseñadas detecta y cuántas marca sin estar,
    separando las que quedaron en revisión de las que eliminaron la llamada;
  · nota de calidad: error medio frente a la nota esperada;
  · KPIs que decide Jev (resuelto, satisfacción): acuerdo.

Escribe la tabla en README.es.md entre <!-- desvio:inicio --> y <!-- desvio:fin -->.
El README en inglés lleva una copia traducida a mano: si cambian las cifras, se actualiza allí.
Las llamadas que no están en el plan (las escritas antes del catálogo) no cuentan.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools" / "muestra"))

from pipeline import s2_contexto as s2                  # noqa: E402
from catalogo import nota_esperada                      # noqa: E402

MARCAS = ("<!-- desvio:inicio -->", "<!-- desvio:fin -->")


def cumple_disenado(linea: dict, nivel: str, form: dict) -> bool:
    if linea["tipo"] == "noul":
        return nivel in ("si", "na")
    return int(nivel) / (len(linea["niveles"]) - 1) >= form["score_cumple_desde"]


def medir(con: sqlite3.Connection, plan: dict, cat: dict, config: dict) -> dict:
    form, kpis = config["formulario"], {m["id"]: m for m in config["kpis"]["medidores"]}
    perfiles = {p["id"]: p for p in cat["perfiles"]}
    perfil_de = {c["id"]: perfiles[c["perfil"]] for c in plan["llamadas"]}

    acuerdo = {l["id"]: [0, 0, 0] for l in form["lineas"]} | {k: [0, 0, 0] for k in ("resuelto", "satisfaccion")}
    elim = {"disenadas": 0, "detectadas": 0, "falsas": 0, "a_revision": 0}
    error_nota, n, motores = [], 0, set()
    for llamada_id, nota, eliminada, motor in con.execute(
            "SELECT id, nota_calidad, eliminada, motor FROM llamadas"):
        p = perfil_de.get(llamada_id)
        if not p:
            continue
        n += 1
        motores.add(motor)
        jev = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT linea_id, cumple, dudoso FROM lineas WHERE llamada_id = ?", (llamada_id,))}
        for l in form["lineas"]:
            d = cumple_disenado(l, p["niveles"][l["id"]], form)
            cumple, dudoso = jev[l["id"]]
            _contar(acuerdo[l["id"]], bool(cumple) == d, dudoso)
            if l["gravedad"] == "eliminatoria":
                elim["disenadas"] += not d
                elim["detectadas"] += (not d) and not cumple
                elim["falsas"] += d and not cumple and not dudoso
                elim["a_revision"] += d and not cumple and bool(dudoso)
        for kid, valor, dudoso in con.execute(
                "SELECT kpi_id, valor, dudoso FROM kpis WHERE llamada_id = ? AND fuente = 'jev'", (llamada_id,)):
            nivel = p["niveles"][kid]
            d = nivel == "si" if kid == "resuelto" else int(nivel) >= kpis[kid]["satisfecho_desde"]
            _contar(acuerdo[kid], bool(valor) == d, dudoso)
        esperada = nota_esperada(p, cat, config)
        error_nota.append(abs(nota - esperada["nota_calidad"]))
    return {"n": n, "motores": sorted(motores), "acuerdo": acuerdo, "elim": elim,
            "error_nota": sum(error_nota) / len(error_nota) if error_nota else None}


def _contar(c: list, de_acuerdo: bool, dudoso) -> None:
    c[0] += de_acuerdo
    c[1] += 1
    c[2] += (not de_acuerdo) and bool(dudoso)


def tabla(r: dict, form: dict) -> str:
    if not r["n"]:
        return "*Sin llamadas con perfil todavía: se rellena al procesar la muestra del catálogo.*"
    nombre = {l["id"]: l["texto"] for l in form["lineas"]} | {"resuelto": "Resuelto (KPI)",
                                                               "satisfaccion": "Satisfacción (KPI)"}
    out = []
    if set(r["motores"]) & {"simulado", "seco"}:
        out.append("> **Sin Jev (motor simulado o en seco).** Estas cifras prueban la medición, no a Jev: el simulado acierta por azar.\n")
    e = r["elim"]
    out += [f"{r['n']} llamadas con perfil · motor: {', '.join(r['motores'])} · "
            f"error medio en la nota de calidad: {r['error_nota']:.2f} puntos sobre 10 · "
            f"eliminatorias detectadas: {e['detectadas']} de {e['disenadas']} · "
            f"eliminatorias sin estar en el diseño: {e['falsas']} eliminaron la llamada, {e['a_revision']} quedaron en revisión", "",
            "| línea | acuerdo con el diseño | desacuerdos marcados como dudosos | desacuerdos sin marcar |",
            "|---|---|---|---|"]
    for k, (ok, total, dudosos) in r["acuerdo"].items():
        if total:
            out.append(f"| {k} {nombre[k]} | {100 * ok / total:.0f} % ({ok}/{total}) | {dudosos} | {total - ok - dudosos} |")
    return "\n".join(out)


def escribir_readme(texto: str, readme: Path) -> None:
    contenido = readme.read_text(encoding="utf-8")
    patron = re.compile(re.escape(MARCAS[0]) + r".*?" + re.escape(MARCAS[1]), re.S)
    if not patron.search(contenido):
        raise SystemExit(f"README sin las marcas {MARCAS}")
    readme.write_text(patron.sub(lambda _: f"{MARCAS[0]}\n{texto}\n{MARCAS[1]}", contenido), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=RAIZ / "data" / "jev.db")
    ap.add_argument("--plan", type=Path, default=RAIZ / "diseno" / "plan.json")
    ap.add_argument("--readme", type=Path, default=RAIZ / "README.es.md")
    a = ap.parse_args()
    cat = json.loads((RAIZ / "diseno" / "catalogo.json").read_text(encoding="utf-8"))
    config = s2.cargar_config(RAIZ / "config")
    con = sqlite3.connect(a.db)
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    texto = tabla(medir(con, plan, cat, config), config["formulario"])
    print(texto)
    escribir_readme(texto, a.readme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
