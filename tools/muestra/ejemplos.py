"""Ejemplos del equipo de referencia para el informe de feedback.

    JEV_MOTOR=openrouter python tools/muestra/ejemplos.py

Para cada línea que pide acción en data/feedback.md, toma hasta dos llamadas
del equipo de referencia que la cumplen con seguridad (una por agente, la nota
más alta primero), vuelve a transcribir su audio y pregunta a Jev qué turno del
agente lo muestra mejor. La cita se guarda en la fila de esa línea, que al
cumplirse no tenía cita. Reprocesar la llamada la borra; basta con relanzar.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import run                                                             # noqa: E402
from base import db, feedback                                          # noqa: E402
from kit.custodia import identity                                      # noqa: E402
from pipeline import s1_limpieza as s1, s2_contexto as s2              # noqa: E402
from pipeline import s3_guardarrail_in as s3, s4_proceso as s4         # noqa: E402
from pipeline import s5_guardarrail_out as s5                          # noqa: E402


def main() -> int:
    run._cargar_env(RAIZ / ".env")
    os.chdir(RAIZ)
    try:
        identity.require_actor()
    except identity.MissingActor as e:
        print(e, file=sys.stderr)
        return 2

    config = s2.cargar_config(RAIZ / "config")
    fb = json.loads((RAIZ / "diseno" / "plan.json").read_text(encoding="utf-8"))["feedback"]
    referencia = next(e for e in config["plantilla"]["equipos"] if e != fb["equipo"])
    hasta = f"{fb['dia']}T23:59:59"
    con = db.abrir(RAIZ / "data" / "jev.db")

    por_llamada: dict[str, list[dict]] = {}
    for l, _, _, distancia in feedback.distancias(con, config["formulario"], hasta, fb["equipo"], referencia):
        if distancia >= feedback.DISTANCIA_MINIMA:
            for llamada_id in feedback.para_ejemplo(con, l["id"], referencia, hasta):
                por_llamada.setdefault(llamada_id, []).append(
                    {"linea_id": l["id"], "texto": l["texto"], "consejo": l["consejo"]})

    for llamada_id, lineas in por_llamada.items():
        wav = RAIZ / "data" / "voz" / llamada_id / f"{llamada_id}_telefono.wav"
        llamada = s1.transcribir(wav, s1.etiquetas_de(wav))
        r = s4.pasada("ejemplos", s1.como_state(llamada), s3.preguntas_evidencia(lineas, llamada, cumple=True))
        s5.sellar_evidencia(r, lineas, llamada, ejemplo=True)
        with con:
            for l in lineas:
                con.execute("UPDATE lineas SET turno = ?, cita = ? WHERE llamada_id = ? AND linea_id = ?",
                            (l["turno"], l["cita"], llamada_id, l["linea_id"]))
        for l in lineas:
            print(f"  {llamada_id} {l['linea_id']}: {l['turno'] or 'sin ejemplo claro'}")

    salida = RAIZ / "data" / "feedback.md"
    salida.write_text(feedback.informe(con, config, dia=fb["dia"], equipo=fb["equipo"], referencia=referencia),
                      encoding="utf-8")
    print(f"feedback → {salida.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
