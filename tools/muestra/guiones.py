"""Comprueba que cada guion encaja con su perfil del catálogo.

    python tools/muestra/guiones.py              # todos los de muestras/guiones/
    python tools/muestra/guiones.py P03a P10a    # solo esos

Por guion: lo sintetiza con Kokoro, lo mezcla en estéreo y mide sus KPIs
objetivos con el mismo código del paso 2 (duración, silencio, interrupciones)
sobre los tiempos reales de la mezcla, y compara cada medida con la banda del
nivel que fija el perfil. El reparto del habla se mide e informa, sin banda; y revisa la estructura:
el perfil y el motivo del guion, y el saludo (G1) por lo que dice el primer
turno del agente.

Lo que no se mide con código (empatía, sondeo, claridad...) se revisa
leyendo; este comprobador solo garantiza lo medible. Sale con 1 si algo no encaja.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from pipeline import s2_contexto as s2               # noqa: E402

GUIONES = RAIZ / "muestras" / "guiones"
PRUEBA = RAIZ / "data" / "muestra" / "prueba"
KOKORO = RAIZ / ".venvs" / "kokoro" / "Scripts" / "python.exe"

# Bandas sobre los tiempos de la mezcla. Medido desde el audio, el silencio sale
# unos puntos más alto (el aire de Kokoro entre frases): de ahí el hueco entre bandas.
# La duración se comprueba para que la muestra tenga llamadas cortas y largas, no
# porque una llamada larga sea mala. El reparto del habla no se comprueba: sale lo
# que la llamada pida y se informa tal cual.
BANDAS = {
    "duracion":     {"corta": (0, 60), "objetivo": (75, 130), "larga": (180, 1e9)},
    "silencio":     {"bajo": (0, 18), "alto": (28, 100)},
}
INTERRUPCIONES = {"0": (0, 0), "1": (1, 1), "3+": (3, 99)}


def preparar(g: str) -> Path:
    guion = json.loads((GUIONES / f"{g}.json").read_text(encoding="utf-8"))
    llamada = {"id": f"guion_{g}", "fecha": "2026-01-01T00:00:00", "agente_id": "laura_gomez",
               "turnos": [{**t, "texto": t["texto"].replace("{agente}", "Laura")} for t in guion["turnos"]]}
    ruta = PRUEBA / f"{g}.json"
    ruta.write_text(json.dumps(llamada, ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def revisar(g: str, perfiles: dict) -> tuple[dict, list[str]]:
    guion = json.loads((GUIONES / f"{g}.json").read_text(encoding="utf-8"))
    p = perfiles[g[:3]]
    fallos = []
    if guion.get("perfil") != p["id"] or guion.get("motivo") != p["motivo"]:
        fallos.append(f"perfil/motivo {guion.get('perfil')}/{guion.get('motivo')} ≠ {p['id']}/{p['motivo']}")
    primero = next(t["texto"] for t in guion["turnos"] if t["hablante"] == "agente")
    g1 = ("{agente}" in primero) + ("Conecta" in primero)
    if (p["niveles"]["G1"] == "2" and g1 < 2) or (p["niveles"]["G1"] == "1" and g1 != 1) or \
            (p["niveles"]["G1"] == "0" and g1 != 0):
        fallos.append(f"G1={p['niveles']['G1']} pero el saludo es «{primero[:50]}»")
    verdad = json.loads((RAIZ / "data" / "voz" / f"guion_{g}" / "verdad.json").read_text(encoding="utf-8"))
    m = s2.medir(verdad)
    for k, bandas in BANDAS.items():
        lo, hi = bandas[p["niveles"][k]]
        if not lo <= m[k] <= hi:
            fallos.append(f"{k}={m[k]} fuera de «{p['niveles'][k]}» ({lo}-{hi:g})")
    lo, hi = INTERRUPCIONES[p["niveles"]["interrupciones"]]
    if not lo <= m["interrupciones"] <= hi:
        fallos.append(f"interrupciones={m['interrupciones']}, el perfil pide {p['niveles']['interrupciones']}")
    return m, fallos


def main(argv: list[str]) -> int:
    cat = json.loads((RAIZ / "diseno" / "catalogo.json").read_text(encoding="utf-8"))
    perfiles = {p["id"]: p for p in cat["perfiles"]}
    nombres = argv or sorted(f.stem for f in GUIONES.glob("*.json"))
    PRUEBA.mkdir(parents=True, exist_ok=True)
    rutas = [str(preparar(g)) for g in nombres]
    entorno = {**os.environ, "PYTHONWARNINGS": "ignore", "HF_HUB_DISABLE_SYMLINKS_WARNING": "1"}
    subprocess.run([str(KOKORO), str(RAIZ / "tools" / "voz" / "sintetizar.py"), *rutas],
                   check=True, env=entorno, capture_output=True)
    subprocess.run([sys.executable, str(RAIZ / "tools" / "voz" / "mezclar.py"), *rutas], check=True,
                   capture_output=True)
    malos = 0
    for g in nombres:
        m, fallos = revisar(g, perfiles)
        malos += bool(fallos)
        print(f"{'ok ' if not fallos else 'NO '} {g}  {m['duracion']:>5.0f} s  silencio {m['silencio']:>4.0f} %  "
              f"agente {m['habla_agente']:>3.0f} %  interrupciones {m['interrupciones']}"
              + "".join(f"\n      · {f}" for f in fallos))
    print(f"{len(nombres) - malos}/{len(nombres)} guiones encajan con su perfil en lo medible")
    return 1 if malos else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
