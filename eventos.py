"""
eventos.py — Bus append-only de eventos del sistema.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Any

from config import cargar_config
from util import append_jsonl, timestamp_iso


def emitir_evento(
    tipo: str,
    *,
    actor: str = "sistema",
    payload: dict[str, Any] | None = None,
    gravedad: str = "info",
) -> dict[str, Any]:
    config = cargar_config()

    evento = {
        "id": str(uuid.uuid4()),
        "ts": timestamp_iso(),
        "tipo": tipo,
        "actor": actor,
        "gravedad": gravedad,
        "payload": payload or {},
    }

    append_jsonl(config.eventos_path, evento)
    return evento


def main() -> int:
    parser = argparse.ArgumentParser(description="Emite un evento de prueba.")
    parser.add_argument("--tipo", required=True)
    parser.add_argument("--actor", default="cli")
    parser.add_argument("--gravedad", default="info")
    parser.add_argument("--payload", default="{}")

    args = parser.parse_args()

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError:
        print("El payload debe ser JSON válido.")
        return 2

    evento = emitir_evento(
        args.tipo,
        actor=args.actor,
        gravedad=args.gravedad,
        payload=payload,
    )

    print(f"Evento emitido: {evento['id']}")
    return 0


if __name__ == "__main__":
    import json

    sys.exit(main())
