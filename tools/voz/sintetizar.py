"""Guion de llamada → un wav por turno, con Kokoro-82M en local.

    .venvs/kokoro/Scripts/python tools/voz/sintetizar.py muestras/llamadas/*.json

Esquema fijo y declarado: una voz para el agente y otra para el cliente,
siempre las mismas, sea quien sea el agente de la etiqueta. Es un pipeline
artificial y suena como tal; quién es quién lo dice la etiqueta, no la voz.

Kokoro corre en su propio entorno (torch con CUDA, ver requirements-voz.txt).
Salida: data/voz/<id>/T01.wav ... más turnos.json con la duración de cada
fichero. No mezcla ni simula teléfono: eso es mezclar.py.

Por qué Kokoro: se probaron Kokoro, Qwen3-TTS 0.6B y Chatterbox Multilingual
sobre las mismas tres llamadas. Kokoro dio el menor error de transcripción
(0,5 % de errores de palabra frente a 3,2 % y 3,8 %) y fue el único más
rápido que el tiempo real en una RTX 2060.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

RAIZ = Path(__file__).resolve().parents[2]
SR = 24000
VOCES = {"agente": "ef_dora", "cliente": "em_alex"}


def main(rutas: list[str]) -> None:
    pipe = KPipeline(lang_code="e", repo_id="hexgrad/Kokoro-82M")
    for ruta in rutas:
        guion = json.loads(Path(ruta).read_text(encoding="utf-8"))
        salida = RAIZ / "data" / "voz" / guion["id"]
        salida.mkdir(parents=True, exist_ok=True)
        turnos, t0 = [], time.perf_counter()
        for i, t in enumerate(guion["turnos"], 1):
            audio = np.concatenate([np.asarray(a) for _, _, a in pipe(t["texto"], voice=VOCES[t["hablante"]])])
            fichero = f"T{i:02d}.wav"
            sf.write(salida / fichero, audio.astype(np.float32), SR)
            turnos.append({"fichero": fichero, "sr": SR, "segundos": round(len(audio) / SR, 2)})
        segundos = time.perf_counter() - t0
        (salida / "turnos.json").write_text(json.dumps(
            {"motor": "kokoro-82m", "voces": VOCES, "segundos_sintesis": round(segundos, 1),
             "turnos": turnos}, indent=2), encoding="utf-8")
        print(f"{guion['id']}: {sum(t['segundos'] for t in turnos):.0f} s de voz en {segundos:.0f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
