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


def _clave_dedupe(modulo: str, mensaje: str) -> str:
    return f"{modulo}::{mensaje}"


def registrar(
    modulo: str,
    mensaje: str,
    gravedad: str = "media",
    detalle: dict[str, Any] | str | None = None,
) -> str:
    """Registra una incidencia y devuelve su id.

    Dedupe por (modulo, mensaje): si ya existe una incidencia abierta con el
    mismo modulo y mensaje, se incrementa `reintentos` en lugar de duplicarla.
    `gravedad` y `detalle` pueden pasarse posicionales o por nombre (los dos
    estilos conviven en el proyecto). Si `detalle` viene como texto libre
    (p. ej. una URL), se guarda como {"fuente": <texto>}.
    """
    if isinstance(detalle, str):
        detalle = {"fuente": detalle}

    config = cargar_config()
    data = _leer_incidencias(config)

    clave = _clave_dedupe(modulo, mensaje)
    for incidencia in data["incidencias"].values():
        if (
            # `reintentando` lo usa marcar() para un ciclo propio y ya sumó su
            # incremento; acá solo se agrupan las incidencias que vuelven a
            # aparecer sin haber sido re-marcadas.
            incidencia.get("estado") in {"abierta", "aislada"}
            and incidencia.get("modulo") == modulo
            and incidencia.get("mensaje") == mensaje
        ):
            # Contador de ocurrencias: la primera vez arranca en 1 y cada
            # repetición suma 1 (2 registros del mismo error -> reintentos 2).
            # Empezar en 0 hacía que el contador llegara tarde: con N registros
            # marcaba N-1, así que un fallo aislado nunca subía de 0 y el umbral
            # de aislamiento (§ fallos_para_aislar) se desfasaba en uno.
            incidencia["reintentos"] = int(incidencia.get("reintentos", 1)) + 1
            incidencia["actualizada"] = timestamp_iso()
            if detalle:
                incidencia.setdefault("detalle", {}).update(detalle)
            _guardar_incidencias(config, data)
            return incidencia["id"]

    incidencia_id = str(uuid.uuid4())

    data["incidencias"][incidencia_id] = {
        "id": incidencia_id,
        "ts": timestamp_iso(),
        "modulo": modulo,
        "mensaje": mensaje,
        "gravedad": gravedad,
        "estado": "abierta",
        # Ocurrencia 1 = visto una vez. El contador es de ocurrencias totales,
        # no de "reintentos posteriores al primero": así N registros del mismo
        # error marcan N, y el umbral de aislamiento se cuenta sin desfase.
        "reintentos": 1,
        "detalle": detalle or {},
        "clave": clave,
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


def abiertas(modulo: str | None = None) -> list[dict[str, Any]]:
    config = cargar_config()
    data = _leer_incidencias(config)

    return [
        incidencia
        for incidencia in data["incidencias"].values()
        if incidencia.get("estado") in {"abierta", "reintentando", "aislada"}
        and (modulo is None or incidencia.get("modulo") == modulo)
    ]


def cerrar(modulo: str, mensaje: str) -> bool:
    """Cierra la incidencia abierta de `modulo` con ese `mensaje`.

    Devuelve True si encontró y cerró alguna; False en caso contrario.
    """
    config = cargar_config()
    data = _leer_incidencias(config)
    encontro = False

    for incidencia in data["incidencias"].values():
        if (
            incidencia.get("estado") in {"abierta", "reintentando", "aislada"}
            and incidencia.get("modulo") == modulo
            and incidencia.get("mensaje") == mensaje
        ):
            incidencia["estado"] = "cerrada"
            incidencia["actualizada"] = timestamp_iso()
            encontro = True

    if encontro:
        _guardar_incidencias(config, data)
    return encontro


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
