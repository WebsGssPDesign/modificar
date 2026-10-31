"""
heartbeat.py — Latido del pipeline.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from config import cargar_config
from util import escribir_json_atomico


def latir(
    paso: str,
    *,
    estado: str = "activo",
    detalle: dict[str, Any] | None = None,
) -> None:
    config = cargar_config()

    data = {
        "ts": time.time(),
        "iso": __import__("util").timestamp_iso(),
        "paso": paso,
        "estado": estado,
        "pid": None,
        "detalle": detalle or {},
    }

    escribir_json_atomico(config.heartbeat_path, data)


def segundos_sin_latir() -> float | None:
    config = cargar_config()
    data = __import__("util").leer_json(config.heartbeat_path, {})

    if not data or "ts" not in data:
        return None

    return max(0.0, time.time() - float(data["ts"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Actualiza o consulta el heartbeat.")
    parser.add_argument("--paso", default="prueba")
    parser.add_argument("--estado", default="activo")
    parser.add_argument("--consultar", action="store_true")

    args = parser.parse_args()

    if args.consultar:
        segundos = segundos_sin_latir()

        if segundos is None:
            print("No hay heartbeat.")
            return 1

        print(f"Segundos desde el último latido: {segundos:.1f}")
        return 0

    latir(args.paso, estado=args.estado)
    print("Heartbeat actualizado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
