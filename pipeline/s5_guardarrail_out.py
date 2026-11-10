"""Paso 5 · Guardarraíl de salida (código). Marca y degrada; nunca corrige.

  · Calidad: una eliminatoria fallada deja la nota en 0. Una eliminatoria en
    la banda dudosa no aprueba ni suspende: la llamada queda en revisión.
  · Notas: las calcula este módulo con fórmula fija. Jev no da ninguna cifra.
    Solo la calidad tiene nota por llamada. Los KPIs se guardan como medidas
    y se juzgan en media (base/estadistica.py): una llamada larga y excelente
    no es mala; la duración solo es mala en promedio.
  · Contraste: si Jev da por cumplida una línea que un medidor objetivo
    contradice (escucha con tres o más interrupciones medidas), la línea pasa
    a dudosa. La IA y el medidor se miran el uno al otro.
  · Evidencia: la cita es el texto del turno elegido, copiado de la
    transcripción. Un fallo sin turno queda marcado como sin evidencia.
"""
from __future__ import annotations


def _dudoso_noul(p: float, form: dict) -> bool:
    lo, hi = form["banda_dudosa"]
    return lo <= p <= hi


def sellar_calidad(ans: dict, form: dict) -> list[dict]:
    out = []
    for l in form["lineas"]:
        a = ans[l["id"]]
        r = {"linea_id": l["id"], "tipo": l["tipo"], "gravedad": l["gravedad"],
             "texto": l["texto"], "pregunta": l["pregunta"], "consejo": l["consejo"]}
        if l["tipo"] == "noul":
            p = a["noul"]
            r.update(valor=p, confianza=None, peso=l.get("peso"), cumple=p >= form["umbral_noul"],
                     dudoso=_dudoso_noul(p, form))
        else:
            maximo = len(l["niveles"]) - 1
            r.update(valor=a["score"], maximo=maximo, peso=l["peso"], confianza=a["confidence"],
                     cumple=a["score"] / maximo >= form["score_cumple_desde"],
                     dudoso=a["confidence"] < form["confianza_minima"])
        out.append(r)
    return out


def contrastar(lineas: list[dict], medidas: dict, form: dict) -> None:
    """Jev contra los medidores, en sitio. Una línea con `contraste` en el formulario que
    Jev da por cumplida mientras su medidor dice lo contrario pasa a dudosa: no se
    corrige a fallo, se manda a revisión."""
    contraste = {l["id"]: l["contraste"] for l in form["lineas"] if "contraste" in l}
    for l in lineas:
        c = contraste.get(l["linea_id"])
        if c and l["cumple"] and medidas[c["medidor"]] >= c["desde"]:
            l["dudoso"] = True
            l["contraste"] = f"{c['medidor']} = {medidas[c['medidor']]}"


def _fraccion(l: dict) -> float:
    """Cuánto de la línea se cumple, 0-1. Un noul suma entero o nada."""
    if l["tipo"] == "noul":
        return 1.0 if l["cumple"] else 0.0
    return l["valor"] / l["maximo"]


def nota_calidad(lineas: list[dict]) -> dict:
    elim = [l for l in lineas if l["gravedad"] == "eliminatoria"]
    if any(not l["cumple"] and not l["dudoso"] for l in elim):
        return {"nota_calidad": 0.0, "eliminada": True, "estado": "ok"}
    estado = "revision" if any(l["dudoso"] for l in elim) else "ok"
    grad = [l for l in lineas if l["gravedad"] != "eliminatoria"]
    for l in grad:
        l.setdefault("peso", 1)
    nota = 10 * sum(l["peso"] * _fraccion(l) for l in grad) / sum(l["peso"] for l in grad)
    return {"nota_calidad": round(nota, 2), "eliminada": False, "estado": estado}


def medidas_kpi(medidas: dict, ans: dict, kpis: dict, form: dict) -> list[dict]:
    """Una fila por KPI con la medida de esta llamada, sin nota: los KPIs se juzgan en media.

    resuelto queda en 1/0 y satisfacción en 1/0 (satisfecho o no), para que su
    media sea directamente el porcentaje que compara el objetivo del servicio.
    """
    filas = []
    for m in kpis["medidores"]:
        if m["fuente"] == "medido":
            filas.append({"kpi_id": m["id"], "fuente": "medido", "valor": medidas[m["id"]], "dudoso": False})
        elif m["tipo"] == "noul":
            p = ans[m["id"]]["noul"]
            filas.append({"kpi_id": m["id"], "fuente": "jev", "valor": float(p >= form["umbral_noul"]),
                          "dudoso": _dudoso_noul(p, form)})
        else:
            a = ans[m["id"]]
            filas.append({"kpi_id": m["id"], "fuente": "jev", "valor": float(a["score"] >= m["satisfecho_desde"]),
                          "dudoso": a["confidence"] < form["confianza_minima"]})
    return filas


def sellar_evidencia(ans: dict, fallos: list[dict], llamada: dict, *, ejemplo: bool = False) -> None:
    """Añade turno y cita a cada fallo, en sitio. La cita sale de la transcripción.

    Con ejemplo=True son líneas cumplidas: sin turno claro no hay ejemplo, pero
    la línea no pasa a dudosa.
    """
    por_n = {t["n"]: t for t in llamada["turnos"]}
    for f in fallos:
        a = ans[f["linea_id"]]
        n, p = a["choice"], a["probabilities"][a["choice"]]
        if n == "ninguno" or p < 0.5:
            f.update(turno=None, cita=None, **({} if ejemplo else {"dudoso": True}))
        else:
            f.update(turno=n, cita=por_n[n]["texto"])
