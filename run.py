"""Catalogación de llamadas con Jev, de punta a punta.

    CUSTODIA_ACTOR=daniel python run.py            # todas las muestras (transcripciones)
    python run.py muestras/llamadas/2026-10-05_0002.json
    python run.py data/voz/*/*_telefono.wav        # desde audio: X.wav + X.etiquetas.json

Por llamada: s1 turnos → s2 etiquetas y medidores → pasadas de Jev (calidad,
kpis, evidencia de los fallos) → s5 sella y calcula notas → SQLite.
Al final, coaching.md (agentes ordenados por gravedad) y estadistica.html
(evolución semanal; los KPIs, en media), todo en data/prueba/. Los resultados
de la muestra (data/jev.db y sus informes) los escribe tools/muestra/avanzar.py
y run.py no los toca.

Por defecto corre con el motor simulado, aunque haya clave: gastar exige JEV_MOTOR=openrouter
(ver clients/jev.py, con tope de gasto acumulado JEV_TOPE_USD).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from base import coaching, db, estadistica                       # noqa: E402
from clients import jev                                          # noqa: E402
from kit.custodia import identity                                # noqa: E402
from pipeline import s1_limpieza as s1, s2_contexto as s2        # noqa: E402
from pipeline import s3_guardarrail_in as s3, s4_proceso as s4   # noqa: E402
from pipeline import s5_guardarrail_out as s5                    # noqa: E402


def _cargar_env(path: Path) -> None:
    if not path.is_file():
        return
    for linea in path.read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def procesar(path: Path, config: dict) -> dict:
    if path.suffix.lower() == ".wav":
        llamada = s1.transcribir(path, s1.etiquetas_de(path))
    else:
        llamada = s1.cargar(path)
    state = s1.como_state(llamada)
    medidas = s2.medir(llamada)

    r_calidad = s4.pasada("calidad", state, s3.preguntas_calidad(config["formulario"]))
    r_kpi = s4.pasada("kpis", state, s3.preguntas_kpi(config["kpis"]))

    lineas = s5.sellar_calidad(r_calidad, config["formulario"])
    s5.contrastar(lineas, medidas, config["formulario"])
    fallos = [l for l in lineas if not l["cumple"]]
    r_evid = s4.pasada("evidencia", state, s3.preguntas_evidencia(fallos, llamada))
    s5.sellar_evidencia(r_evid, fallos, llamada)

    filas_kpi = s5.medidas_kpi(medidas, r_kpi, config["kpis"], config["formulario"])
    return {"id": llamada["id"], "fecha": llamada["fecha"], "duracion_s": medidas["duracion"],
            **s2.etiquetas(llamada, config["plantilla"]),
            **s5.nota_calidad(lineas),
            "lineas": lineas, "kpis": filas_kpi,
            "motor": r_calidad["_motor"], "modelo": r_calidad["_modelo"], "avisos": llamada.get("avisos", [])}


def main(argv: list[str]) -> int:
    _cargar_env(RAIZ / ".env")
    os.chdir(RAIZ)                                   # logs/ y data/ siempre bajo el proyecto
    try:
        print(f"run: actor {identity.require_actor()} · motor {jev.motor()}")
    except identity.MissingActor as e:
        print(e, file=sys.stderr)
        return 2

    config = s2.cargar_config(RAIZ / "config")
    rutas = [Path(a) for a in argv] or sorted((RAIZ / "muestras" / "llamadas").glob("*.json"))
    salidas = RAIZ / "data" / "prueba"
    con = db.abrir(salidas / "jev.db")
    for ruta in rutas:
        r = procesar(ruta, config)
        db.guardar(con, r)
        agente = r["agente_id"]
        calidad = "ELIMINADA" if r["eliminada"] else f"{r['nota_calidad']:.1f}"
        print(f"  {r['id']}  {agente:<14} calidad {calidad:<9} {r['duracion_s']:>4.0f} s  {r['estado']}")

    salida = salidas / "coaching.md"
    salida.write_text(coaching.informe(con, config), encoding="utf-8")
    print(f"coaching → {salida.relative_to(RAIZ)}")
    salida = salidas / "estadistica.html"
    salida.write_text(estadistica.informe(con, config), encoding="utf-8")
    print(f"estadística → {salida.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
