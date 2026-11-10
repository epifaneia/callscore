"""Paso 2 · Contexto (código). Configuración y medidores objetivos.

Todo lo que se puede medir se mide aquí, sin modelo: duración, silencio,
reparto del habla e interrupciones salen de los tiempos de los turnos. Jev
nunca hace cuentas.
"""
from __future__ import annotations

import json
from pathlib import Path

# Un turno interrumpe si empieza al menos 0,3 s antes de que acabe el otro. Por debajo
# es redondeo de los tiempos de Whisper (medido: 0,01 s en un falso solape frente a
# 1,0-1,7 s en las interrupciones reales de la muestra). Decisión propia.
SOLAPE_MINIMO = 0.3


def interrumpe(prev: dict, t: dict) -> bool:
    return prev["hablante"] != t["hablante"] and prev["fin"] - t["inicio"] >= SOLAPE_MINIMO


def cargar_config(carpeta: Path) -> dict:
    return {nombre: json.loads((carpeta / f"{nombre}.json").read_text(encoding="utf-8"))
            for nombre in ("plantilla", "formulario", "kpis")}


def etiquetas(llamada: dict, plantilla: dict) -> dict:
    """Agente y equipo salen de la etiqueta de la grabación y de la plantilla."""
    aid = llamada["agente_id"]
    if aid not in plantilla["agentes"]:
        raise ValueError(f"{llamada['id']}: agente {aid!r} no está en la plantilla")
    return {"agente_id": aid, "equipo": plantilla["agentes"][aid]["equipo"]}


def _union(intervalos: list[tuple[float, float]]) -> float:
    total, fin_actual = 0.0, None
    for a, b in sorted(intervalos):
        if fin_actual is None or a > fin_actual:
            total += b - a
            fin_actual = b
        elif b > fin_actual:
            total += b - fin_actual
            fin_actual = b
    return total


def medir(llamada: dict) -> dict:
    turnos = llamada["turnos"]
    duracion = max(t["fin"] for t in turnos)
    habla = _union([(t["inicio"], t["fin"]) for t in turnos])
    agente = _union([(t["inicio"], t["fin"]) for t in turnos if t["hablante"] == "agente"])
    cliente = _union([(t["inicio"], t["fin"]) for t in turnos if t["hablante"] == "cliente"])
    # interrupción: el agente empieza a hablar antes de que el cliente termine
    interrupciones = sum(
        1 for prev, t in zip(turnos, turnos[1:])
        if prev["hablante"] == "cliente" and t["hablante"] == "agente" and interrumpe(prev, t))
    return {
        "duracion": round(duracion, 1),
        "silencio": round(100 * (duracion - habla) / duracion, 1),
        "habla_agente": round(100 * agente / (agente + cliente), 1),
        "interrupciones": interrupciones,
    }
