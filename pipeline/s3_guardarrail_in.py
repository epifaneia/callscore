"""Paso 3 · Guardarraíl de entrada (código). Todo lo que Jev contesta es cerrado.

Cada pasada es un mapa de preguntas con sus opciones. Jev no ve los ids de las
preguntas, así que el significado va entero en `instructions` y `criteria`.

  · calidad    noul por eliminatoria y línea de sí/no, score por graduable.
  · kpis       las preguntas de KPI que no se pueden medir.
  · evidencia  por cada fallo, choice entre los turnos del agente + "ninguno":
               la cita es el turno elegido, literal por construcción.
"""
from __future__ import annotations


def _pregunta(item: dict) -> dict:
    if item["tipo"] == "noul":
        q = {"type": "noul", "instructions": item["pregunta"]}
        if "criterios" in item:                # qué cuenta como sí y qué como no, cuando la frontera es fina
            q["criteria"] = item["criterios"]
        return q
    return {"type": "score", "instructions": item["pregunta"], "criteria": item["niveles"]}


def preguntas_calidad(formulario: dict) -> dict:
    return {l["id"]: _pregunta(l) for l in formulario["lineas"]}


def preguntas_kpi(kpis: dict) -> dict:
    return {m["id"]: _pregunta(m) for m in kpis["medidores"] if m["fuente"] == "jev"}


def preguntas_evidencia(fallos: list[dict], llamada: dict, *, cumple: bool = False) -> dict:
    # Todas las líneas juzgan al agente: solo sus turnos pueden ser evidencia.
    criteria = {t["n"]: f"Turno {t['n']}" for t in llamada["turnos"] if t["hablante"] == "agente"}
    criteria["ninguno"] = "Ningún turno concreto lo muestra"
    # Lo esperado es el consejo de la línea: describe el comportamiento correcto
    # igual para líneas de sí/no y graduables, sin encadenar dos preguntas.
    # Con cumple=True se busca el ejemplo contrario: el turno que lo hace bien.
    hecho = "sí lo cumple" if cumple else "no lo cumple"
    return {f["linea_id"]: {
        "type": "choice",
        "instructions": (f"Punto de calidad: {f['texto']}. Lo que se espera del agente: {f['consejo']} "
                         f"En esta llamada el agente {hecho}. ¿Qué turno del agente lo muestra mejor?"),
        "criteria": criteria} for f in fallos}
