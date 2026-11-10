"""Cliente de Jev (TypeSafe) a través de OpenRouter.

Jev no genera texto: recibe un `state` (lo que tiene que leer) y un mapa de
`questions` cerradas, y devuelve por cada pregunta probabilidades sobre las
opciones que le dimos. Tres tipos que usamos aquí:

  · choice  → `criteria` = {opción: descripción}; responde `choice` y, de forma
              opcional, `probabilities` y `confidence`.
  · score   → `criteria` = [nivel0, nivel1, ...]; responde `score` (media
              ponderada, puede ser fraccionaria) y, opcional, `confidence`.
  · noul    → sin criteria; responde `noul` = probabilidad de "sí".

Esquema verificado contra la referencia de OpenRouter (POST /api/alpha/decisions)
el 2026-10-28. Precio: 0,042 $ por millón de tokens de entrada; la salida no se cobra.

Tres motores con el mismo contrato. Por defecto, simulado: gastar dinero es
siempre una decisión explícita, nunca un efecto de tener la clave en .env.

  · simulado    sin red. Respuestas pseudoaleatorias deterministas: NO miden nada.
  · seco        sin red. Escribe en data/peticiones/ la petición exacta que se
                enviaría, para revisarla, y responde como el simulado.
  · openrouter  JEV_MOTOR=openrouter. El dato sale de la máquina (ledger con
                leaves_machine=True) y cuesta dinero, con dos guardarraíles:
                  - tope de gasto acumulado (JEV_TOPE_USD, por defecto 0,25 $),
                    sumando el coste real que OpenRouter devuelve en cada llamada
                    y queda en el ledger; antes de cada llamada se suma la
                    estimación de esa petición, y si se pasa, no se envía;
                  - tamaño: por encima de ~32.000 bytes TypeSafe pasa a contexto
                    largo, «más lento y menos preciso»; la petición no se envía.

No depende de ningún SDK — solo urllib de la stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import urllib.error
import urllib.request
from itertools import count
from pathlib import Path
from typing import Any

from kit.custodia import ledger
from kit.custodia.ledger import record_call

URL = "https://openrouter.ai/api/alpha/decisions"
MODELO_POR_DEFECTO = "typesafe/jev-1.14"   # versión fijada: los resultados cambian entre versiones
PRECIO_ENTRADA = 0.042 / 1_000_000          # $ por token de entrada (salida gratis)
BYTES_POR_TOKEN = 3.0                       # estimación conservadora para español: sobreestima el coste
LIMITE_BYTES = 30_000                       # por debajo del umbral de contexto largo (~32.000)
TOPE_POR_DEFECTO = 0.25                     # $ acumulados entre todas las ejecuciones

_peticion = count(1)


class TopeDeGasto(RuntimeError):
    """La siguiente llamada superaría el tope de gasto acumulado: no se envía."""


def motor() -> str:
    """simulado salvo que JEV_MOTOR diga otra cosa. La clave sola no gasta."""
    return os.environ.get("JEV_MOTOR", "").strip().lower() or "simulado"


def decide(*, step: str, state: Any, questions: dict) -> dict:
    """Una llamada a Jev. Devuelve `answers` normalizadas, más `_motor` y `_modelo`."""
    m = motor()
    body = {"model": os.environ.get("JEV_MODEL", MODELO_POR_DEFECTO), "state": state, "questions": questions}
    if m == "openrouter":
        return _openrouter(step=step, body=body)
    if m == "seco":
        _guardar_peticion(step, body)
        return {**_simulado(state=state, questions=questions), "_motor": "seco"}
    if m == "simulado":
        return _simulado(state=state, questions=questions)
    raise ValueError(f"JEV_MOTOR desconocido: {m!r} (simulado | seco | openrouter)")


def gasto_acumulado() -> float:
    """Suma del coste real devuelto por OpenRouter en todas las llamadas del ledger."""
    path = ledger.default().path
    if not path or not path.is_file():
        return 0.0
    total = 0.0
    for linea in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(linea)
        if r.get("engine") == "jev" and r.get("cost"):
            total += r["cost"]
    return total


def coste_estimado(cuerpo: str) -> float:
    return len(cuerpo.encode("utf-8")) / BYTES_POR_TOKEN * PRECIO_ENTRADA


def _openrouter(*, step: str, body: dict) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Falta OPENROUTER_API_KEY en .env.")
    cuerpo = json.dumps(body, ensure_ascii=False)
    tamano = len(cuerpo.encode("utf-8"))
    if tamano > LIMITE_BYTES:
        raise ValueError(f"{step}: petición de {tamano} bytes > {LIMITE_BYTES}: TypeSafe pasaría a "
                         "contexto largo (más lento y menos preciso). No se envía.")
    tope = float(os.environ.get("JEV_TOPE_USD", TOPE_POR_DEFECTO))
    gastado = gasto_acumulado()
    if gastado + coste_estimado(cuerpo) > tope:
        raise TopeDeGasto(f"{step}: gastado {gastado:.6f} $ + estimado {coste_estimado(cuerpo):.6f} $ "
                          f"> tope {tope} $ (JEV_TOPE_USD). No se envía.")
    with record_call(step=step, engine="jev", endpoint="openrouter.ai", leaves_machine=True,
                     payload=cuerpo, model=body["model"]) as rec:
        raw = _post(URL, cuerpo, key)
        _guardar(Path("data") / "respuestas", step, raw)     # solo probabilidades: ningún texto de la llamada
        uso = raw.get("usage") or {}
        rec.update(output_chars=len(json.dumps(raw)), cost=uso.get("cost"),
                   input_tokens=uso.get("input_tokens"), served_model=raw.get("model"))
    answers = raw.get("answers") or {}
    faltan = set(body["questions"]) - set(answers)
    if faltan:
        raise ValueError(f"Jev no contestó a {sorted(faltan)}")
    return {**{q: _normalizar(a) for q, a in answers.items()},
            "_motor": "openrouter", "_modelo": raw.get("model", body["model"])}


def _normalizar(a: dict) -> dict:
    """Los campos opcionales de la respuesta quedan explícitos: sin confianza es confianza 0
    (el guardarraíl de salida lo marca como dudoso), sin probabilidades se usa la confianza."""
    a = dict(a)
    if a.get("type") in ("choice", "score"):
        a.setdefault("confidence", 0.0)
    if a.get("type") == "choice":
        a.setdefault("probabilities", {a["choice"]: a["confidence"]})
    return a


def _post(url: str, body: str, key: str, timeout_s: float = 60.0) -> dict:
    req = urllib.request.Request(
        url, data=body.encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"OpenRouter {e.code}: {detalle}") from e


def _guardar_peticion(step: str, body: dict) -> None:
    _guardar(Path("data") / "peticiones", step, body)


def _guardar(carpeta: Path, step: str, datos: dict) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    cuerpo = json.dumps(datos, ensure_ascii=False, indent=1)
    (carpeta / f"{next(_peticion):04d}_{step}.json").write_text(cuerpo, encoding="utf-8")


def _simulado(*, state: Any, questions: dict) -> dict:
    """Misma forma de respuesta que Jev, sin red y sin ninguna inteligencia."""
    semilla = json.dumps(state, ensure_ascii=False, sort_keys=True)
    out: dict[str, Any] = {}
    for qid, q in questions.items():
        rnd = random.Random(hashlib.sha256((semilla + qid).encode("utf-8")).digest())
        tipo = q["type"]
        if tipo == "noul":
            out[qid] = {"type": "noul", "noul": round(rnd.random(), 3)}
            continue
        opciones = list(q["criteria"]) if tipo == "choice" else list(range(len(q["criteria"])))
        pesos = [rnd.random() ** 3 for _ in opciones]
        total = sum(pesos)
        probs = [p / total for p in pesos]
        if tipo == "choice":
            out[qid] = {"type": "choice", "choice": opciones[probs.index(max(probs))],
                        "probabilities": dict(zip(opciones, probs)), "confidence": max(probs)}
        else:
            out[qid] = {"type": "score", "score": sum(i * p for i, p in enumerate(probs)),
                        "probabilities": {str(i): p for i, p in enumerate(probs)},
                        "confidence": max(probs)}
    return {**out, "_motor": "simulado", "_modelo": "simulado"}
