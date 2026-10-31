"""
metricas.py — Registro de rendimiento por unidad de trabajo.
"""

from __future__ import annotations

import argparse
import sys
import time
from contextlib import contextmanager
from typing import Any, Iterator

from config import cargar_config
from util import append_jsonl, timestamp_iso


@contextmanager
def medir(
    modulo: str,
    entrada: str,
    *,
    actor: str = "sistema",
    detalle: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    config = cargar_config()
    inicio = time.perf_counter()
    registro: dict[str, Any] = {
        "resultado": "ok",
        "salida": None,
        "error": None,
    }

    try:
        yield registro
    except Exception as exc:
        registro["resultado"] = "error"
        registro["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        duracion = time.perf_counter() - inicio

        linea = {
            "ts": timestamp_iso(),
            "modulo": modulo,
            "actor": actor,
            "entrada": entrada,
            "segundos": round(duracion, 4),
            "resultado": registro["resultado"],
            "salida": registro["salida"],
            "error": registro["error"],
            "detalle": detalle or {},
        }

        append_jsonl(config.metricas_path, linea)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba una medición.")
    parser.add_argument("--modulo", default="prueba")
    parser.add_argument("--entrada", default="demo")

    args = parser.parse_args()

    with medir(args.modulo, args.entrada) as registro:
        registro["salida"] = "medición de prueba"

    print("Métrica registrada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
