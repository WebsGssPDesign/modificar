"""
logger.py — Logging estructurado (JSON lines) con rotación.

Salida:
    Sistema/logs/memoria.jsonl   (rotación por tamaño, 5 copias)

Configuración (variables de entorno):
    MEMORIA_LOG_NIVEL    DEBUG | INFO | WARNING | ERROR | CRITICAL  (def. INFO)
    MEMORIA_LOG_CONSOLA  1 | 0   copia legible por stderr            (def. 0)

Uso en un módulo:
    from logger import get_logger
    log = get_logger("aprender")
    log.info("ciclo terminado", extra={"datos": {"publicados": 3}})

Sustitución gradual de print(): los módulos existentes siguen usando print
para su salida de CLI; el logger es para trazas internas y diagnóstico.
El logger nunca lanza excepciones hacia el pipeline: si no puede escribir,
degrada a stderr.

Uso por línea de comandos:
    python logger.py --probar
    python logger.py --tail 20 [--nivel WARNING] [--modulo aprender]
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAIZ = "memoria"
MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 5
NIVELES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class FormatoJSON(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        registro: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(
                timespec="seconds"
            ),
            "nivel": record.levelname,
            "modulo": record.name.removeprefix(RAIZ + "."),
            "mensaje": record.getMessage(),
        }

        datos = getattr(record, "datos", None)
        if datos:
            registro["datos"] = datos

        if record.exc_info:
            registro["excepcion"] = self.formatException(record.exc_info)

        return json.dumps(registro, ensure_ascii=False, default=str)


def _nivel_desde_entorno() -> int:
    nombre = os.environ.get("MEMORIA_LOG_NIVEL", "INFO").strip().upper()
    return getattr(logging, nombre if nombre in NIVELES else "INFO")


def _ruta_log() -> Path:
    from config import cargar_config

    return cargar_config().sistema / "logs" / "memoria.jsonl"


def _configurar() -> logging.Logger:
    raiz = logging.getLogger(RAIZ)
    raiz.setLevel(_nivel_desde_entorno())
    raiz.propagate = False

    try:
        destino = _ruta_log()
    except Exception:  # configuración inválida: degradar a stderr
        destino = None

    actuales = {
        getattr(h, "_memoria_destino", None): h for h in list(raiz.handlers)
    }

    if destino is not None and str(destino) not in actuales:
        for h in list(raiz.handlers):
            if getattr(h, "_memoria_tipo", "") == "archivo":
                raiz.removeHandler(h)
                h.close()

        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                destino, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
            )
            handler.setFormatter(FormatoJSON())
            handler._memoria_tipo = "archivo"  # type: ignore[attr-defined]
            handler._memoria_destino = str(destino)  # type: ignore[attr-defined]
            raiz.addHandler(handler)
        except OSError:
            pass

    consola_activa = os.environ.get("MEMORIA_LOG_CONSOLA", "0") == "1"
    hay_consola = any(
        getattr(h, "_memoria_tipo", "") == "consola" for h in raiz.handlers
    )
    sin_handlers = not raiz.handlers

    if (consola_activa or sin_handlers) and not hay_consola:
        consola = logging.StreamHandler(sys.stderr)
        consola.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
        consola._memoria_tipo = "consola"  # type: ignore[attr-defined]
        raiz.addHandler(consola)

    for h in raiz.handlers:
        h.setLevel(logging.NOTSET)

    return raiz


def get_logger(nombre: str) -> logging.Logger:
    _configurar()
    return logging.getLogger(f"{RAIZ}.{nombre}")


def cerrar() -> None:
    """Cierra los handlers (necesario en Windows antes de borrar la carpeta)."""
    raiz = logging.getLogger(RAIZ)
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
        h.close()


def leer_log(
    limite: int = 20,
    *,
    nivel_minimo: str = "DEBUG",
    modulo: str | None = None,
) -> list[dict[str, Any]]:
    ruta = _ruta_log()

    if not ruta.exists():
        return []

    minimo = NIVELES.index(nivel_minimo.upper()) if nivel_minimo.upper() in NIVELES else 0
    salida: list[dict[str, Any]] = []

    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            registro = json.loads(linea)
        except json.JSONDecodeError:
            continue

        if registro.get("nivel") not in NIVELES:
            continue
        if NIVELES.index(registro["nivel"]) < minimo:
            continue
        if modulo and registro.get("modulo") != modulo:
            continue

        salida.append(registro)

    return salida[-limite:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Logging estructurado.")
    parser.add_argument("--probar", action="store_true", help="Escribe una línea de prueba.")
    parser.add_argument("--tail", type=int, metavar="N", help="Muestra las últimas N líneas.")
    parser.add_argument("--nivel", default="DEBUG")
    parser.add_argument("--modulo", default=None)
    args = parser.parse_args()

    if args.probar:
        log = get_logger("logger")
        log.info("prueba de logging", extra={"datos": {"ok": True}})
        print(f"Escrito en: {_ruta_log()}")
        return 0

    if args.tail:
        for registro in leer_log(args.tail, nivel_minimo=args.nivel, modulo=args.modulo):
            print(
                f"{registro['ts']} {registro['nivel']:<8} "
                f"{registro['modulo']}: {registro['mensaje']}"
            )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
