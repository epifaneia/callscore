"""Avanza la muestra día a día: fabrica las llamadas del día, las procesa y regenera los informes.

    python tools/muestra/avanzar.py               # el siguiente día
    python tools/muestra/avanzar.py --hasta 10    # hasta el día 10 (el del feedback)
    python tools/muestra/avanzar.py --reiniciar   # vacía la base y vuelve al día 0

Por cada llamada del día en diseno/plan.json:
  1. guion muestras/guiones/<guion>.json → data/muestra/<id>.json, con el nombre
     del agente en el sitio de {agente} y las etiquetas de la llamada;
  2. voz con Kokoro (.venvs/kokoro) y mezcla en estéreo → data/voz/<id>/<id>_telefono.wav;
  3. pipeline desde el audio (run.procesar) y a la SQLite.
Después, coaching, estadística y desvío frente al diseño, con los datos hasta ese día.

El cursor vive en data/muestra/cursor.json. Si falta algún guion, no avanza y
dice cuáles.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import run                                                   # noqa: E402
from base import coaching, db, estadistica, feedback        # noqa: E402
from kit.custodia import identity                           # noqa: E402
from pipeline import s2_contexto as s2                      # noqa: E402

GUIONES = RAIZ / "muestras" / "guiones"
TRABAJO = RAIZ / "data" / "muestra"
CURSOR = TRABAJO / "cursor.json"
KOKORO = RAIZ / ".venvs" / "kokoro" / "Scripts" / "python.exe"


def fabricar(c: dict, plantilla: dict) -> Path:
    """Guion del perfil → llamada con su agente → audio estéreo con sus etiquetas."""
    wav = RAIZ / "data" / "voz" / c["id"] / f"{c['id']}_telefono.wav"
    if wav.is_file():
        return wav
    guion = json.loads((GUIONES / f"{c['guion']}.json").read_text(encoding="utf-8"))
    nombre = plantilla["agentes"][c["agente_id"]]["nombre"].split()[0]
    llamada = {"id": c["id"], "fecha": c["fecha"], "agente_id": c["agente_id"], "perfil": c["perfil"],
               "turnos": [{**t, "texto": t["texto"].replace("{agente}", nombre)} for t in guion["turnos"]]}
    ruta = TRABAJO / f"{c['id']}.json"
    ruta.write_text(json.dumps(llamada, ensure_ascii=False, indent=1), encoding="utf-8")
    entorno = {**os.environ, "PYTHONWARNINGS": "ignore", "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"}
    subprocess.run([str(KOKORO), str(RAIZ / "tools" / "voz" / "sintetizar.py"), str(ruta)],
                   check=True, env=entorno, capture_output=True)
    subprocess.run([sys.executable, str(RAIZ / "tools" / "voz" / "mezclar.py"), str(ruta)], check=True,
                   capture_output=True)
    return wav


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hasta", type=int)
    ap.add_argument("--reiniciar", action="store_true")
    a = ap.parse_args()
    run._cargar_env(RAIZ / ".env")
    os.chdir(RAIZ)
    try:
        identity.require_actor()
    except identity.MissingActor as e:
        print(e, file=sys.stderr)
        return 2

    TRABAJO.mkdir(parents=True, exist_ok=True)
    base_datos = RAIZ / "data" / "jev.db"
    if a.reiniciar:
        base_datos.unlink(missing_ok=True)
        CURSOR.unlink(missing_ok=True)
        print("muestra reiniciada: día 0")
        return 0

    plan = json.loads((RAIZ / "diseno" / "plan.json").read_text(encoding="utf-8"))
    ultimo = json.loads(CURSOR.read_text())["ultimo_dia"] if CURSOR.is_file() else 0
    total = max(c["dia"] for c in plan["llamadas"])
    hasta = min(a.hasta or ultimo + 1, total)
    dias = [c for c in plan["llamadas"] if ultimo < c["dia"] <= hasta]
    if not dias:
        print(f"la muestra ya va por el día {ultimo} de {total}")
        return 0

    faltan = sorted({c["guion"] for c in dias if not (GUIONES / f"{c['guion']}.json").is_file()})
    if faltan:
        print(f"faltan guiones en muestras/guiones/ para los días {ultimo + 1}-{hasta}: {' '.join(faltan)}")
        return 1

    config = s2.cargar_config(RAIZ / "config")
    con = db.abrir(base_datos)
    for dia in range(ultimo + 1, hasta + 1):
        for c in (c for c in dias if c["dia"] == dia):
            r = run.procesar(fabricar(c, config["plantilla"]), config)
            db.guardar(con, r)
            for aviso in r["avisos"]:
                print(f"  aviso {c['id']}: {aviso}")
        CURSOR.write_text(json.dumps({"ultimo_dia": dia}))
        fecha = next(c["fecha"][:10] for c in dias if c["dia"] == dia)
        nota = f" · {plan['feedback']['texto']}" if fecha == plan["feedback"]["dia"] else ""
        print(f"día {dia} ({fecha}) procesado{nota}")

    (RAIZ / "data" / "coaching.md").write_text(coaching.informe(con, config), encoding="utf-8")
    (RAIZ / "data" / "estadistica.html").write_text(estadistica.informe(con, config), encoding="utf-8")
    fb = plan["feedback"]
    if fecha >= fb["dia"]:
        otro = next(e for e in config["plantilla"]["equipos"] if e != fb["equipo"])
        (RAIZ / "data" / "feedback.md").write_text(
            feedback.informe(con, config, dia=fb["dia"], equipo=fb["equipo"], referencia=otro), encoding="utf-8")
    subprocess.run([sys.executable, str(RAIZ / "tools" / "muestra" / "desvio.py")], check=True, capture_output=True)
    print(f"día {hasta} de {total} · informes y desvío actualizados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
