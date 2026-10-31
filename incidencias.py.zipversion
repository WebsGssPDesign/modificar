"""
incidencias.py — Registro de fallos con ciclo de vida.

Estados:
    abierta -> reintentando -> aislada -> resuelta
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Any

from config import cargar_config
from util import leer_json, escribir_json_atomico, timestamp_iso


def _leer_incidencias(config) -> dict[str, Any]:
    data = leer_json(config.incidencias_path, {})

    if not isinstance(data, dict):
        data = {}

    if not isinstance(data.get("incidencias"), dict):
        data["incidencias"] = {}

    return data


def _guardar_incidencias(config, data: dict[str, Any]) -> None:
    escribir_json_atomico(config.incidencias_path, data)


def registrar(
    modulo: str,
    mensaje: str,
    *,
    gravedad: str = "media",
    detalle: dict[str, Any] | None = None,
) -> str:
    config = cargar_config()
    data = _leer_incidencias(config)

    incidencia_id = str(uuid.uuid4())

    data["incidencias"][incidencia_id] = {
        "id": incidencia_id,
        "ts": timestamp_iso(),
        "modulo": modulo,
        "mensaje": mensaje,
        "gravedad": gravedad,
        "estado": "abierta",
        "reintentos": 0,
        "detalle": detalle or {},
    }

    _guardar_incidencias(config, data)
    return incidencia_id


def marcar(
    incidencia_id: str,
    estado: str,
    *,
    detalle: dict[str, Any] | None = None,
) -> bool:
    config = cargar_config()
    data = _leer_incidencias(config)

    incidencia = data["incidencias"].get(incidencia_id)

    if not incidencia:
        return False

    incidencia["estado"] = estado
    incidencia["actualizada"] = timestamp_iso()

    if estado == "reintentando":
        incidencia["reintentos"] = int(incidencia.get("reintentos", 0)) + 1

    if detalle:
        incidencia.setdefault("detalle", {}).update(detalle)

    _guardar_incidencias(config, data)
    return True


def abiertas() -> list[dict[str, Any]]:
    config = cargar_config()
    data = _leer_incidencias(config)

    return [
        incidencia
        for incidencia in data["incidencias"].values()
        if incidencia.get("estado") in {"abierta", "reintentando", "aislada"}
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Gestiona incidencias.")
    sub = parser.add_subparsers(dest="comando", required=True)

    registrar_parser = sub.add_parser("registrar")
    registrar_parser.add_argument("--modulo", required=True)
    registrar_parser.add_argument("--mensaje", required=True)
    registrar_parser.add_argument("--gravedad", default="media")

    marcar_parser = sub.add_parser("marcar")
    marcar_parser.add_argument("--id", required=True)
    marcar_parser.add_argument("--estado", required=True)

    sub.add_parser("abiertas")

    args = parser.parse_args()

    if args.comando == "registrar":
        incidencia_id = registrar(args.modulo, args.mensaje, gravedad=args.gravedad)
        print(f"Incidencia registrada: {incidencia_id}")
        return 0

    if args.comando == "marcar":
        ok = marcar(args.id, args.estado)
        print("Actualizada." if ok else "No encontrada.")
        return 0 if ok else 1

    for incidencia in abiertas():
        print(f"{incidencia['id']} [{incidencia['estado']}] {incidencia['modulo']}: {incidencia['mensaje']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
