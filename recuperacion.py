"""
recuperacion.py — Mejoras de recuperación sobre la búsqueda híbrida.

No modifica el índice ni memoria.py: envuelve buscar_hibrido() y añade, de forma
determinista (sin LLM, sin dependencias):

    1. Filtro por ámbito: solo rutas que empiecen por uno de los prefijos dados
       (por ejemplo "LLM-Memoria/Hechos" o "Notas/Python").
    2. Fecha de vigencia: si la nota tiene `vigente_hasta: AAAA-MM-DD` en su
       frontmatter y ya pasó, se excluye (o se marca con --incluir-vencidos).
    3. Reranking léxico ligero: sube los resultados cuyo título o encabezado
       contiene términos de la consulta.

Pendiente a propósito (requiere LLM y decisiones de diseño): detección de
contradicciones y resúmenes por documento.

Uso:
    python recuperacion.py "como crear un indice" --ambito LLM-Memoria --k 5
    python recuperacion.py "consulta" --incluir-vencidos
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Iterable

from config import cargar_config
from memoria import Resultado, buscar_hibrido

SOBREMUESTREO = 4
PESO_RERANK = 0.5
RE_VIGENCIA = re.compile(r"^vigente_hasta:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
RE_TERMINO = re.compile(r"[\wáéíóúüñÁÉÍÓÚÜÑ]{3,}")


def _terminos(texto: str) -> set[str]:
    return {t.casefold() for t in RE_TERMINO.findall(texto)}


def _en_ambito(ruta: str, ambitos: list[str]) -> bool:
    if not ambitos:
        return True

    ruta = ruta.replace("\\", "/")

    return any(
        ruta == a.strip("/") or ruta.startswith(a.strip("/") + "/") for a in ambitos
    )


def _vigente_hasta(boveda: Path, ruta: str, cache: dict[str, date | None]) -> date | None:
    if ruta in cache:
        return cache[ruta]

    valor: date | None = None

    try:
        texto = (boveda / ruta).read_text(encoding="utf-8", errors="replace")
        m = RE_VIGENCIA.search(texto[:2000])
        valor = date.fromisoformat(m.group(1)) if m else None
    except (OSError, ValueError):
        valor = None

    cache[ruta] = valor
    return valor


def reordenar(consulta: str, resultados: Iterable[Resultado]) -> list[Resultado]:
    """Función pura: sube los resultados con coincidencias léxicas en título/encabezado."""
    q = _terminos(consulta)
    salida = []

    for r in resultados:
        if q:
            cabecera = _terminos(f"{r.titulo} {r.encabezado}")
            solape = len(q & cabecera) / len(q)
        else:
            solape = 0.0

        salida.append(replace(r, score=round(r.score * (1 + PESO_RERANK * solape), 6)))

    return sorted(salida, key=lambda r: -r.score)


def buscar(
    consulta: str,
    *,
    k: int = 10,
    ambitos: list[str] | None = None,
    incluir_vencidos: bool = False,
    hoy: date | None = None,
    modelo: str | None = None,
) -> list[Resultado]:
    config = cargar_config()
    hoy = hoy or date.today()
    ambitos = ambitos or []
    cache: dict[str, date | None] = {}

    candidatos = buscar_hibrido(
        consulta, k=max(k * SOBREMUESTREO, 20), modelo=modelo
    )
    filtrados = []

    for r in candidatos:
        if not _en_ambito(r.ruta, ambitos):
            continue

        limite = _vigente_hasta(config.boveda, r.ruta, cache)

        if limite is not None and limite < hoy and not incluir_vencidos:
            continue

        filtrados.append(r)

    return reordenar(consulta, filtrados)[:k]


def main() -> int:
    parser = argparse.ArgumentParser(description="Búsqueda con filtros y reranking.")
    parser.add_argument("consulta")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--ambito", action="append", default=[], help="Prefijo de ruta; repetible.")
    parser.add_argument("--incluir-vencidos", action="store_true")
    parser.add_argument("--modelo", default=None)
    args = parser.parse_args()

    resultados = buscar(
        args.consulta,
        k=args.k,
        ambitos=args.ambito,
        incluir_vencidos=args.incluir_vencidos,
        modelo=args.modelo,
    )

    if not resultados:
        print("Sin resultados.")
        return 0

    for i, r in enumerate(resultados, start=1):
        print(f"[{i}] {r.score:.6f} {r.ruta} · {r.titulo} · {r.encabezado or '-'}")
        print("    " + r.contenido[:240].replace("\n", " "))

    return 0


if __name__ == "__main__":
    sys.exit(main())
