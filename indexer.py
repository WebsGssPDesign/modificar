"""
indexer.py — Indexa y consulta la memoria vectorial.

Comandos:
    python indexer.py --index
    python indexer.py --search "consulta"
    python indexer.py --status
    python indexer.py --reindex
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from config import cargar_config, preparar_carpetas
from eventos import emitir_evento
from heartbeat import latir
from incidencias import registrar
from memoria import buscar_hibrido, estado_indice, indexar_boveda
from metricas import medir


def _imprimir_resultados(resultados: list) -> None:
    if not resultados:
        print("Sin resultados.")
        return

    for i, resultado in enumerate(resultados, start=1):
        print(f"\n[{i}] score={resultado.score:.6f} metodo={resultado.metodo}")
        print(f"    archivo: {resultado.ruta}")
        print(f"    titulo : {resultado.titulo}")
        print(f"    seccion: {resultado.encabezado or '-'}")
        print(f"    fts    : {resultado.rank_fts or '-'} | vector: {resultado.rank_vec or '-'}")
        print("    " + resultado.contenido[:280].replace("\n", " "))


def _firma_boveda(config) -> tuple[int, float]:
    """Firma barata (nº de archivos, mtime máximo) para detectar cambios."""
    from memoria import _archivos_candidatos

    archivos = _archivos_candidatos(config)
    mtime = max((ruta.stat().st_mtime for ruta in archivos), default=0.0)
    return len(archivos), mtime


def vigilar_boveda(*, intervalo: float = 30.0, max_ciclos: int | None = None) -> int:
    """
    Reindexa de forma incremental cuando cambia la bóveda.
    Se detiene limpiamente cuando existe el archivo .memoria/STOP.
    """
    config = cargar_config()
    preparar_carpetas(config)
    stop = config.memoria_dir / "STOP"
    ultima: tuple[int, float] | None = None
    ciclos = 0
    fallos_seguidos = 0

    print(f"Vigilando {config.boveda} cada {intervalo:.0f}s. Para detener: crea {stop}")

    while True:
        if stop.exists():
            latir("indexer.watch", estado="detenido")
            print("STOP detectado. Saliendo.")
            return 0

        latir("indexer.watch")

        try:
            firma = _firma_boveda(config)

            if firma != ultima:
                with medir("indexer", "watch") as registro:
                    stats = indexar_boveda(recalcular_embeddings=True)
                    registro["salida"] = stats

                ultima = firma
                fallos_seguidos = 0

                if stats["chunks_nuevos"] or stats["chunks_eliminados"] or stats["errores"]:
                    emitir_evento("indexer.index.ok", payload=stats)

        except Exception as exc:  # el watcher nunca debe morir por un fallo puntual
            fallos_seguidos += 1
            registrar(
                "indexer.watch",
                f"Fallo en vigilancia: {exc}",
                gravedad="media" if fallos_seguidos < 5 else "alta",
            )

        ciclos += 1

        if max_ciclos is not None and ciclos >= max_ciclos:
            return 0

        espera = intervalo * min(2 ** fallos_seguidos, 8) if fallos_seguidos else intervalo
        time.sleep(espera)


def main() -> int:
    parser = argparse.ArgumentParser(description="Índice de memoria vectorial.")
    parser.add_argument("--index", action="store_true", help="Indexa cambios.")
    parser.add_argument("--reindex", action="store_true", help="Fuerza recalcular embeddings.")
    parser.add_argument("--search", metavar="CONSULTA", help="Búsqueda híbrida.")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--candidatos", type=int, default=30)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--modelo", default=None)
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Vigila la bóveda y reindexa al detectar cambios. Parada limpia: crear .memoria/STOP.",
    )
    parser.add_argument("--intervalo", type=float, default=30.0, help="Segundos entre revisiones.")

    args = parser.parse_args()

    config = cargar_config()
    preparar_carpetas(config)

    if args.check:
        print(f"Bóveda: {config.boveda}")
        print(f"SQLite: {config.db_path}")
        print(f"min_sim: {config.min_sim.valor}")
        print(f"pool: {config.pool.valor}")
        return 0

    if args.status:
        print(json.dumps(estado_indice(), ensure_ascii=False, indent=2))
        return 0

    if args.search:
        inicio = time.perf_counter()

        try:
            resultados = buscar_hibrido(
                args.search,
                k=args.k,
                candidatos=args.candidatos,
                modelo=args.modelo,
            )
        except Exception as exc:
            incidencia_id = registrar(
                "indexer.search",
                f"Búsqueda fallida: {exc}",
                gravedad="alta",
            )

            emitir_evento(
                "indexer.search.error",
                gravedad="alta",
                payload={"incidencia": incidencia_id, "error": str(exc)},
            )

            print(f"Error en búsqueda: {exc}")
            return 2

        duracion = time.perf_counter() - inicio

        _imprimir_resultados(resultados)
        print(f"\n{len(resultados)} resultados en {duracion:.3f}s")
        return 0

    if args.watch:
        return vigilar_boveda(intervalo=args.intervalo)

    if args.index or args.reindex:
        latir("indexer", detalle={"modo": "reindex" if args.reindex else "index"})

        try:
            with medir("indexer", "boveda") as registro:
                stats = indexar_boveda(
                    recalcular_embeddings=True,
                    forzar=args.reindex,
                )
                registro["salida"] = stats

        except Exception as exc:
            incidencia_id = registrar(
                "indexer.index",
                f"Indexación fallida: {exc}",
                gravedad="alta",
            )

            emitir_evento(
                "indexer.index.error",
                gravedad="alta",
                payload={"incidencia": incidencia_id, "error": str(exc)},
            )

            print(f"Error durante la indexación: {exc}")
            return 2

        emitir_evento("indexer.index.ok", payload=stats)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
