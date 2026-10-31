"""
repaso.py — Repetición espaciada para las notas generadas.

Campos en el frontmatter de cada nota (LLM-Memoria/Hechos y LLM-Memoria/Web):
    repasar: 2026-11-02        próxima fecha de repaso
    repaso_estado: sin-revisar | revisada
    repaso_nivel: 0            índice en la escalera de intervalos

Escalera (reglas.json -> tablero.repaso_dias, def. 1, 3, 7, 21, 60 días):
    repasar bien  -> sube un nivel y se agenda con el intervalo siguiente
    olvidada      -> vuelve al nivel 0
    pasado el último nivel, el intervalo final se repite

Salida visible: LLM-Memoria/Revision/Cola.md (notas vencidas, la más atrasada primero).

Uso:
    python repaso.py                       inicializa notas nuevas y genera la cola
    python repaso.py --inicializar
    python repaso.py --cola [--dry-run]
    python repaso.py --marcar LLM-Memoria/Hechos/nota.md
    python repaso.py --marcar RUTA --olvidada
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from config import cargar_config, preparar_carpetas
from escritor import actualizar_frontmatter, crear_nota
from eventos import emitir_evento
from heartbeat import latir
from metricas import medir
from util import ruta_relativa_segura

SUBCARPETAS = ("Hechos", "Web")
ACTOR = "repaso"
RE_FECHA = re.compile(r"^repasar:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
RE_NIVEL = re.compile(r"^repaso_nivel:\s*(\d+)\s*$", re.MULTILINE)
RE_TITULO = re.compile(r'^titulo:\s*"?(.*?)"?\s*$', re.MULTILINE)


def _dias(config) -> list[int]:
    dias = [int(d) for d in config.repaso_dias if int(d) > 0]
    return dias or [1, 3, 7, 21, 60]


def intervalo_para(nivel: int, dias: list[int]) -> int:
    return dias[min(max(nivel, 0), len(dias) - 1)]


def _notas(config) -> list[Path]:
    rutas: list[Path] = []

    for sub in SUBCARPETAS:
        carpeta = config.notas / sub

        if carpeta.exists():
            rutas.extend(sorted(carpeta.rglob("*.md")))

    return rutas


def _estado(ruta: Path) -> dict[str, Any]:
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    f = RE_FECHA.search(texto)
    n = RE_NIVEL.search(texto)
    t = RE_TITULO.search(texto)

    try:
        fecha = date.fromisoformat(f.group(1)) if f else None
    except ValueError:
        fecha = None

    return {
        "fecha": fecha,
        "nivel": int(n.group(1)) if n else 0,
        "titulo": t.group(1) if t and t.group(1) else ruta.stem,
    }


def inicializar(*, hoy: date | None = None, dry_run: bool = False) -> list[str]:
    config = cargar_config()
    hoy = hoy or date.today()
    dias = _dias(config)
    nuevas: list[str] = []

    for ruta in _notas(config):
        if _estado(ruta)["fecha"] is not None:
            continue

        relativa = ruta.relative_to(config.boveda).as_posix()
        nuevas.append(relativa)

        if dry_run:
            continue

        actualizar_frontmatter(
            relativa,
            {
                "repasar": (hoy + timedelta(days=dias[0])).isoformat(),
                "repaso_estado": "sin-revisar",
                "repaso_nivel": 0,
            },
            actor=ACTOR,
            motivo="repaso_init",
            backup=False,
        )

    return nuevas


def vencidas(*, hoy: date | None = None) -> list[dict[str, Any]]:
    config = cargar_config()
    hoy = hoy or date.today()
    salida = []

    for ruta in _notas(config):
        est = _estado(ruta)

        if est["fecha"] is not None and est["fecha"] <= hoy:
            salida.append(
                {
                    "ruta": ruta.relative_to(config.boveda).as_posix(),
                    "stem": ruta.stem,
                    "titulo": est["titulo"],
                    "nivel": est["nivel"],
                    "fecha": est["fecha"].isoformat(),
                    "atraso": (hoy - est["fecha"]).days,
                }
            )

    return sorted(salida, key=lambda n: (-n["atraso"], n["ruta"]))


def render_cola(pendientes: list[dict[str, Any]], hoy: date) -> str:
    lineas = [f"Notas para repasar a fecha {hoy.isoformat()}: **{len(pendientes)}**.", ""]

    if not pendientes:
        lineas.append("Nada pendiente. 🎉")
    else:
        lineas += ["| Nota | Nivel | Atraso (días) |", "|---|---|---|"]

        for n in pendientes:
            lineas.append(f"| [[{n['stem']}\\|{n['titulo']}]] | {n['nivel']} | {n['atraso']} |")

    lineas += [
        "",
        "Para marcar una nota: `python repaso.py --marcar <ruta>` "
        "(o `--olvidada` si no la recordabas).",
    ]
    return "\n".join(lineas) + "\n"


def generar_cola(*, hoy: date | None = None, dry_run: bool = False) -> dict[str, Any]:
    config = cargar_config()
    preparar_carpetas(config)
    hoy = hoy or date.today()
    pendientes = vencidas(hoy=hoy)
    destino = None

    if not dry_run:
        carpeta = (config.notas / "Revision").relative_to(config.boveda).as_posix()
        r = crear_nota(
            "Cola",
            render_cola(pendientes, hoy),
            carpeta=carpeta,
            tags=["repaso"],
            fuente="repaso",
            confianza=1.0,
            actor=ACTOR,
            motivo="cola_repaso",
            sobrescribir=True,
        )
        destino = str(r.ruta) if r.ok else None

    return {"pendientes": len(pendientes), "cola": destino, "dry_run": dry_run}


def marcar(
    ruta_relativa: str, *, olvidada: bool = False, hoy: date | None = None
) -> dict[str, Any]:
    config = cargar_config()
    hoy = hoy or date.today()
    ruta = ruta_relativa_segura(ruta_relativa, config.boveda)

    if not ruta.exists():
        raise FileNotFoundError(f"No existe la nota: {ruta_relativa}")

    dias = _dias(config)
    actual = _estado(ruta)
    nivel = 0 if olvidada else actual["nivel"] + 1
    proxima = hoy + timedelta(days=intervalo_para(nivel, dias))

    r = actualizar_frontmatter(
        ruta_relativa,
        {
            "repasar": proxima.isoformat(),
            "repaso_estado": "revisada",
            "repaso_nivel": nivel,
        },
        actor=ACTOR,
        motivo="repaso_marcar",
        backup=False,
    )

    if not r.ok:
        raise RuntimeError(r.mensaje)

    return {"ruta": ruta_relativa, "nivel": nivel, "proxima": proxima.isoformat()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Repetición espaciada.")
    parser.add_argument("--inicializar", action="store_true")
    parser.add_argument("--cola", action="store_true")
    parser.add_argument("--marcar", metavar="RUTA")
    parser.add_argument("--olvidada", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    latir("repaso")

    try:
        if args.marcar:
            print(json.dumps(marcar(args.marcar, olvidada=args.olvidada), ensure_ascii=False, indent=2))
            return 0

        with medir("repaso", "ciclo") as registro:
            nuevas = inicializar(dry_run=args.dry_run) if not args.cola else []
            resultado: dict[str, Any] = {"inicializadas": len(nuevas)}

            if not args.inicializar:
                resultado.update(generar_cola(dry_run=args.dry_run))

            registro["salida"] = resultado

        if not args.dry_run:
            emitir_evento("repaso.ciclo.ok", payload=resultado)

        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 0

    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
