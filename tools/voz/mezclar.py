"""Turnos sintetizados → llamada en estéreo (agente izquierda, cliente derecha).

    python tools/voz/mezclar.py muestras/llamadas/*.json

Los huecos entre turnos salen del guion: si un turno empieza antes de que
acabe el anterior, se solapa lo mismo (interrupción sembrada); si no, se deja
la misma pausa. Así interrupciones y silencios son verdad conocida.

Dos condiciones por llamada:
  · limpio    16 kHz, tal cual sale de Kokoro.
  · telefono  8 kHz, banda de voz 300-3400 Hz y ruido de línea a 25 dB SNR.

Junto a cada wav, <wav>.etiquetas.json con id, fecha y agente: lo que run.py
lee para procesar el audio. Escribe también verdad.json: los turnos con los tiempos reales de la mezcla,
en el mismo formato que s1_limpieza. Es contra lo que se mide la transcripción.
"""
from __future__ import annotations

import json
import sys
from math import gcd
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, resample_poly, sosfilt

RAIZ = Path(__file__).resolve().parents[2]
PAUSA_MAX = 8.0          # un hueco del guion más largo se recorta: es tiempo muerto sin información
PAUSA_NORMAL = 0.6       # entre turnos, cuando el guion no dice nada


def _leer(path: Path, sr_dest: int) -> np.ndarray:
    sr, x = wavfile.read(path)
    x = x.astype(np.float32) / (32768.0 if x.dtype == np.int16 else 1.0)
    g = gcd(sr, sr_dest)
    return resample_poly(x, sr_dest // g, sr // g).astype(np.float32)


def _telefono(x: np.ndarray, sr: int, rng: np.random.Generator) -> np.ndarray:
    y = sosfilt(butter(4, [300, 3400], btype="band", fs=sr, output="sos"), x)
    potencia = np.mean(y ** 2) or 1e-9
    ruido = rng.normal(0, np.sqrt(potencia / 10 ** (25 / 10)), len(y))
    return (y + ruido).astype(np.float32)


def _hueco(t: dict, prev: dict) -> float:
    """Segundos entre el final del turno anterior y este; negativo si lo interrumpe.

    Guiones de la muestra: `pausa` (silencio de diseño, sin recorte: una espera
    larga es justo lo que se quiere medir) o `interrumpe` (segundos que pisa).
    Sin ninguno de los dos, una pausa normal. Transcripciones antiguas: el hueco
    sale de inicio/fin y se recorta a PAUSA_MAX.
    """
    if "interrumpe" in t:
        return -t["interrumpe"]
    if "pausa" in t:
        return t["pausa"]
    if "inicio" in t and "fin" in prev:
        return min(t["inicio"] - prev["fin"], PAUSA_MAX)
    return PAUSA_NORMAL


def mezclar(guion_path: Path) -> None:
    guion = json.loads(guion_path.read_text(encoding="utf-8"))
    carpeta = RAIZ / "data" / "voz" / guion["id"]
    sint = json.loads((carpeta / "turnos.json").read_text(encoding="utf-8"))

    for condicion, sr in (("limpio", 16000), ("telefono", 8000)):
        rng = np.random.default_rng(0)
        canales = {"agente": [], "cliente": []}
        verdad, cursor, prev = [], 0.5, None
        for t_guion, t_sint in zip(guion["turnos"], sint["turnos"]):
            audio = _leer(carpeta / t_sint["fichero"], sr)
            dur = len(audio) / sr
            if prev is not None:
                hueco = _hueco(t_guion, prev)
                inicio = verdad[-1]["fin"] + hueco if hueco >= 0 \
                    else max(verdad[-1]["inicio"] + 0.5, verdad[-1]["fin"] + hueco)
            else:
                inicio = cursor
            canales[t_guion["hablante"]].append((inicio, audio))
            verdad.append({"hablante": t_guion["hablante"], "inicio": round(inicio, 2),
                           "fin": round(inicio + dur, 2), "texto": t_guion["texto"]})
            prev = t_guion

        total = int((max(t["fin"] for t in verdad) + 0.5) * sr)
        estereo = np.zeros((total, 2), dtype=np.float32)
        for col, hablante in enumerate(("agente", "cliente")):
            for inicio, audio in canales[hablante]:
                a = int(inicio * sr)
                estereo[a:a + len(audio), col] += audio
            if condicion == "telefono":
                estereo[:, col] = _telefono(estereo[:, col], sr, rng)
        estereo /= max(1e-9, np.abs(estereo).max() / 0.9)
        wavfile.write(carpeta / f"{guion['id']}_{condicion}.wav", sr, (estereo * 32767).astype(np.int16))
        # lo que en una empresa daría la centralita junto a la grabación
        (carpeta / f"{guion['id']}_{condicion}.etiquetas.json").write_text(json.dumps(
            {k: guion[k] for k in ("id", "fecha", "agente_id")}, ensure_ascii=False, indent=2),
            encoding="utf-8")

    (carpeta / "verdad.json").write_text(json.dumps(
        {"id": guion["id"], "fecha": guion["fecha"], "agente_id": guion["agente_id"], "turnos": verdad},
        ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"{guion['id']}: {total / sr:.0f} s mezclados")


if __name__ == "__main__":
    for ruta in sys.argv[1:]:
        mezclar(Path(ruta))
