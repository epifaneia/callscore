"""Paso 4 · Proceso (Jev). El único paso que llama a un modelo.

Una pasada = una petición con un `state` y varias preguntas. Jev decide; no
escribe nada. Lo que vuelve son probabilidades que interpreta el paso 5.
"""
from __future__ import annotations

from clients import jev


def pasada(nombre: str, state: str, preguntas: dict) -> dict:
    if not preguntas:
        return {}
    return jev.decide(step=f"s4_{nombre}", state=state, questions=preguntas)
