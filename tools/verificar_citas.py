"""Comprueba que cada cita de formulario.json y kpis.json está literal en su fuente.

    python tools/verificar_citas.py

Descarga cada documento de config/fuentes.json a data/fuentes/ (una vez),
extrae el texto (pypdf para los PDF) y busca cada campo `dice` con
`text_norm.is_literal`: literal sobre texto normalizado, sin umbral de
parecido. Los `resumen` son paráfrasis nuestras y no se comprueban.

Sale con 1 si alguna cita no aparece. Es el mismo guardarraíl que el pipeline
aplica a las citas de las llamadas, aplicado a nuestro propio formulario.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from kit.limpieza.text_norm import is_literal   # noqa: E402


def texto(doc_id: str, doc: dict, carpeta: Path) -> str:
    carpeta.mkdir(parents=True, exist_ok=True)
    cache = carpeta / f"{doc_id}.txt"
    if cache.is_file():
        return cache.read_text(encoding="utf-8")
    req = urllib.request.Request(doc["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    if doc["formato"] == "pdf":
        import io
        import pypdf
        lector = pypdf.PdfReader(io.BytesIO(raw))
        t = "\n".join(p.extract_text() or "" for p in lector.pages)
    else:
        t = raw.decode("utf-8")
    cache.write_text(t, encoding="utf-8")
    return t


def citas(config: Path):
    form = json.loads((config / "formulario.json").read_text(encoding="utf-8"))
    kpis = json.loads((config / "kpis.json").read_text(encoding="utf-8"))
    for l in form["lineas"]:
        for c in l["fuentes"]:
            yield l["id"], c
    for m in kpis["medidores"]:
        yield m["id"], m["cita"]
        if "cita_margen" in m:
            yield m["id"], m["cita_margen"]


def main() -> int:
    config = RAIZ / "config"
    docs = json.loads((config / "fuentes.json").read_text(encoding="utf-8"))["docs"]
    textos: dict[str, str] = {}
    fallos = total = 0
    for item, c in citas(config):
        if "dice" not in c:
            continue
        if c["doc"] not in textos:
            textos[c["doc"]] = texto(c["doc"], docs[c["doc"]], RAIZ / "data" / "fuentes")
        total += 1
        ok = is_literal(c["dice"], textos[c["doc"]])
        fallos += not ok
        print(f"{'ok ' if ok else 'NO '} {item:<15} {c['doc']:<8} {c['donde']:<35} {c['dice'][:50]}")
    print(f"{total - fallos}/{total} citas literales")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
