"""Paso 1 · Limpieza (código). Audio → turnos numerados.

Una llamada sale de aquí como:

    {"id", "fecha", "agente_id", "turnos": [{"n": "T1", "hablante": "agente"|"cliente",
                                             "inicio": s, "fin": s, "texto": str}, ...]}

Fecha y agente son etiquetas de la grabación (en una empresa, metadatos de la
centralita). Ningún modelo los decide.

Dos entradas:
  · `cargar()`      una transcripción ya hecha (muestras/llamadas/*.json).
  · `transcribir()` audio en estéreo, agente en el canal izquierdo y cliente en
                    el derecho, como graba una centralita. Quién habla sale del
                    canal, no de un modelo; los tiempos salen del audio para
                    los medidores del paso 2. faster-whisper en local, en CPU.
"""
from __future__ import annotations

import json
from math import gcd
from pathlib import Path

from kit.limpieza.text_norm import normalize
from pipeline.s2_contexto import interrumpe

HABLANTES = {"agente", "cliente"}
CANALES = ("agente", "cliente")         # izquierda, derecha
JUNTAR_SI_HUECO = 1.0                    # segmentos del mismo canal a menos de 1 s: un turno

_whisper = {}


def etiquetas_de(audio: Path) -> dict:
    """Las etiquetas viajan junto al audio: X.wav → X.etiquetas.json (id, fecha, agente_id)."""
    ruta = audio.with_name(audio.stem + ".etiquetas.json")
    if not ruta.is_file():
        raise FileNotFoundError(f"{audio.name}: falta {ruta.name}; sin etiquetas no se procesa")
    return json.loads(ruta.read_text(encoding="utf-8"))


def transcribir(audio: Path, etiquetas: dict | None = None, *, modelo: str = "large-v3-turbo") -> dict:
    """Estéreo → turnos. Cada canal se transcribe por separado y se intercalan por tiempo."""
    import numpy as np
    from faster_whisper import WhisperModel
    from scipy.io import wavfile
    from scipy.signal import resample_poly

    if modelo not in _whisper:
        _whisper[modelo] = WhisperModel(modelo, device="cpu", compute_type="int8")
    sr, x = wavfile.read(audio)
    if x.ndim != 2 or x.shape[1] != 2:
        raise ValueError(f"{audio.name}: hace falta estéreo (agente izquierda, cliente derecha)")
    x = x.astype(np.float32) / (32768.0 if x.dtype == np.int16 else 1.0)
    g = gcd(sr, 16000)

    # Palabra a palabra: un segmento de Whisper puede cruzar el silencio de un
    # canal mientras habla el otro; los tiempos por palabra no.
    palabras, avisos = [], []
    for col, hablante in enumerate(CANALES):
        canal = resample_poly(x[:, col], 16000 // g, sr // g).astype(np.float32)
        try:
            palabras += _palabras(_whisper[modelo], canal, hablante, vad=True)
        except IndexError:
            # Fallo conocido de la alineación por palabras de faster-whisper con el
            # filtro de voz activo (visto en la muestra: canal del agente de una
            # llamada). Se repite ese canal sin el filtro y queda anotado.
            palabras += _palabras(_whisper[modelo], canal, hablante, vad=False)
            avisos.append(f"canal {hablante}: transcrito sin filtro de voz")

    # Primero se agrupa cada canal por su cuenta y luego se intercalan los
    # turnos: en una interrupción los dos turnos se solapan, no se trocean.
    turnos: list[dict] = []
    for hablante in CANALES:
        propios: list[dict] = []
        for p in (p for p in palabras if p["hablante"] == hablante):
            if propios and p["inicio"] - propios[-1]["fin"] < JUNTAR_SI_HUECO:
                propios[-1]["fin"], propios[-1]["texto"] = p["fin"], f"{propios[-1]['texto']} {p['texto']}"
            else:
                propios.append(dict(p))
        turnos += propios
    turnos.sort(key=lambda t: t["inicio"])
    for i, t in enumerate(turnos, 1):
        t.update(n=f"T{i}", inicio=round(t["inicio"], 2), fin=round(t["fin"], 2))
    etiquetas = etiquetas or {"id": audio.stem, "fecha": None, "agente_id": None}
    return {**etiquetas, "turnos": turnos, "avisos": avisos}


def _palabras(modelo, canal, hablante: str, *, vad: bool) -> list[dict]:
    segs, _ = modelo.transcribe(canal, language="es", beam_size=5, vad_filter=vad,
                                word_timestamps=True, condition_on_previous_text=False)
    return [{"hablante": hablante, "inicio": w.start, "fin": w.end, "texto": w.word.strip()}
            for s in segs for w in (s.words or []) if w.word.strip()]


def cargar(path: Path) -> dict:
    """Transcripción en JSON → llamada limpia, con turnos ordenados y numerados."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    turnos = []
    for t in sorted(raw["turnos"], key=lambda t: t["inicio"]):
        if t["hablante"] not in HABLANTES:
            raise ValueError(f"{path.name}: hablante desconocido {t['hablante']!r}")
        texto = " ".join(t["texto"].split())
        if not normalize(texto)[0]:
            continue                                   # turno vacío: fuera
        turnos.append({"hablante": t["hablante"], "inicio": float(t["inicio"]),
                       "fin": float(t["fin"]), "texto": texto})
    for i, t in enumerate(turnos, 1):
        t["n"] = f"T{i}"
    return {"id": raw["id"], "fecha": raw["fecha"], "agente_id": raw["agente_id"], "turnos": turnos}


def como_state(llamada: dict) -> str:
    """Lo que lee Jev: una línea por turno, con su número para poder citarlo.

    Un solape no se ve en el texto, así que el código lo dice: el turno que
    empieza antes de que el otro termine lleva «interrumpe al cliente» (o al
    agente). Es el mismo criterio (s2_contexto.interrumpe, solape de 0,3 s o más)
    con el que el paso 2 cuenta interrupciones.
    """
    lineas, prev = [], None
    for t in llamada["turnos"]:
        marca = ""
        if prev and interrumpe(prev, t):
            marca = f", interrumpe al {prev['hablante']}"
        lineas.append(f"{t['n']} [{int(t['inicio']) // 60:02d}:{int(t['inicio']) % 60:02d} "
                      f"{t['hablante']}{marca}] {t['texto']}")
        prev = t
    return "\n".join(lineas)
