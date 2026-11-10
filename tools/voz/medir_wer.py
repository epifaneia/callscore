"""WER de faster-whisper sobre las llamadas sintetizadas, contra su guion.

    python tools/voz/medir_wer.py            # todo lo que haya en data/voz/

Por llamada y condición (limpio / teléfono): WER por canal y total, y
cuántos turnos reconstruye s1 frente a los del guion. Normalización mínima y
declarada: minúsculas, sin tildes y sin puntuación. Las cifras NO se pasan a
palabras: si el guion dice "treinta y nueve" y Whisper escribe "39", cuenta
como error, porque así llegaría a Jev. Por eso se dan dos cifras: WER
total, y errores de palabra (los que no tocan ningún número).

Salida: tabla por pantalla y data/voz/informe.md con las diferencias.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from kit.limpieza.text_norm import normalize        # noqa: E402
from pipeline import s1_limpieza as s1                # noqa: E402


NUMERALES = set("""cero uno una dos tres cuatro cinco seis siete ocho nueve diez once doce trece
catorce quince dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres
veinticuatro veinticinco veintiseis veintisiete veintiocho veintinueve treinta cuarenta cincuenta
sesenta setenta ochenta noventa cien ciento doscientos trescientos cuatrocientos quinientos
seiscientos setecientos ochocientos novecientos mil""".split())


def es_cifra(dif: str) -> bool:
    """Una diferencia es de cifras si toca un numeral escrito o un token con dígitos."""
    return any(lado in NUMERALES or re.search(r"\d", lado) for lado in dif.split(" → "))


def palabras(texto: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", normalize(texto)[0]).split()


def alinear(ref: list[str], hip: list[str]) -> tuple[int, list[str]]:
    """Distancia de edición en palabras y la lista de diferencias."""
    n, m = len(ref), len(hip)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hip[j - 1]))
    difs, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hip[j - 1]):
            if ref[i - 1] != hip[j - 1]:
                difs.append(f"{ref[i - 1]} → {hip[j - 1]}")
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            difs.append(f"{ref[i - 1]} → ∅")
            i -= 1
        else:
            difs.append(f"∅ → {hip[j - 1]}")
            j -= 1
    return d[n][m], difs[::-1]


def main() -> int:
    filas, detalle = [], []
    for verdad_path in sorted((RAIZ / "data" / "voz").glob("*/verdad.json")):
        verdad = json.loads(verdad_path.read_text(encoding="utf-8"))
        for condicion in ("limpio", "telefono"):
            wav = verdad_path.parent / f"{verdad['id']}_{condicion}.wav"
            hip = s1.transcribir(wav)
            errores = total = de_palabra = 0
            for h in s1.CANALES:
                ref_h = palabras(" ".join(t["texto"] for t in verdad["turnos"] if t["hablante"] == h))
                hip_h = palabras(" ".join(t["texto"] for t in hip["turnos"] if t["hablante"] == h))
                e, difs = alinear(ref_h, hip_h)
                errores, total = errores + e, total + len(ref_h)
                de_palabra += sum(not es_cifra(x) for x in difs)
                detalle.append(f"- {verdad['id']} · {condicion} · {h}: "
                               f"{e}/{len(ref_h)} — {'; '.join(difs) or 'sin diferencias'}")
            filas.append((condicion, errores, total, de_palabra, len(verdad["turnos"]), len(hip["turnos"])))
            print(f"{verdad['id']}  {condicion:<9} WER {100 * errores / total:5.1f} %  "
                  f"palabra {100 * de_palabra / total:4.1f} %  turnos {len(hip['turnos'])}/{len(verdad['turnos'])}")

    out = ["# WER de faster-whisper (large-v3-turbo, CPU int8) sobre voz Kokoro-82M", "",
           "| condición | palabras | WER total | errores de palabra (sin cifras) | turnos |",
           "|---|---|---|---|---|"]
    for cond in ("limpio", "telefono"):
        sel = [f for f in filas if f[0] == cond]
        e, t, p, tv, th = (sum(f[i] for f in sel) for i in (1, 2, 3, 4, 5))
        if t:
            out.append(f"| {cond} | {t} | {100 * e / t:.1f} % | {100 * p / t:.1f} % | {th}/{tv} |")
            print(f"TOTAL {cond:<9} WER {100 * e / t:5.1f} %  palabra {100 * p / t:4.1f} %  turnos {th}/{tv}")
    out += ["", "## Diferencias", ""] + detalle
    (RAIZ / "data" / "voz" / "informe.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
