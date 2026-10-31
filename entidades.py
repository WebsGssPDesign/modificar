"""
entidades.py — Grafo de entidades para Obsidian, sin ruido.

Lee las notas generadas (LLM-Memoria/Hechos y LLM-Memoria/Web), cuenta qué
entidades aparecen en su sección "## Entidades" y crea una nota por entidad en
LLM-Memoria/Entidades/ con:
    - backlinks a las notas que la mencionan
    - relaciones con otras entidades que comparten notas

Reglas anti-ruido:
    - Una entidad necesita al menos --min-menciones notas (def. 2).
    - Se descartan nombres vacíos, numéricos, demasiado largos o de relleno.
    - Máximo 8 relaciones por entidad (las más fuertes).
    - Una entidad que deja de cumplir el umbral NO se borra: se reporta como
      obsoleta y solo se mueve a la papelera con --limpiar.
    - Las notas de entidad solo se reescriben si su contenido cambió.

Uso:
    python entidades.py --dry-run
    python entidades.py
    python entidades.py --min-menciones 3 --json
    python entidades.py --limpiar
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from config import cargar_config, preparar_carpetas
from eventos import emitir_evento
from heartbeat import latir
from metricas import medir
from util import slugify

SUBCARPETAS_FUENTE = ("Hechos", "Web")
CARPETA_ENTIDADES = "Entidades"
MAX_RELACIONES = 8
MAX_LARGO_NOMBRE = 60
RELLENO = {"-", "n/a", "na", "ninguna", "ninguno", "sin entidades", "ninguna entidad"}
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")


def _seccion_entidades(texto: str) -> str:
    m = re.search(r"^## Entidades\s*\n(.*?)(?=^## |\Z)", texto, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() if m else ""


def _extraer_entidades(texto: str) -> list[str]:
    seccion = _seccion_entidades(texto)

    if not seccion:
        return []

    enlaces = [e.strip() for e in WIKILINK.findall(seccion)]
    crudas = enlaces or [p.strip() for p in re.split(r"[,\n;]", seccion)]
    salida: list[str] = []

    for nombre in crudas:
        nombre = re.sub(r"\s+", " ", nombre.strip(" -*`"))
        clave = nombre.casefold()

        if not nombre or clave in RELLENO:
            continue
        if len(nombre) > MAX_LARGO_NOMBRE or nombre.replace(".", "").isdigit():
            continue
        if not slugify(nombre):
            continue
        if nombre not in salida:
            salida.append(nombre)

    return salida


def _titulo(texto: str, ruta: Path) -> str:
    m = re.search(r'^titulo:\s*"?(.*?)"?\s*$', texto, re.MULTILINE)
    return m.group(1) if m and m.group(1) else ruta.stem


def _leer_notas(config) -> list[dict[str, Any]]:
    notas = []

    for sub in SUBCARPETAS_FUENTE:
        carpeta = config.notas / sub

        if not carpeta.exists():
            continue

        for ruta in sorted(carpeta.rglob("*.md")):
            try:
                texto = ruta.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            entidades = _extraer_entidades(texto)

            if entidades:
                notas.append(
                    {
                        "stem": ruta.stem,
                        "titulo": _titulo(texto, ruta),
                        "entidades": entidades,
                    }
                )

    return notas


def construir_grafo(
    notas: list[dict[str, Any]], *, min_menciones: int = 2
) -> dict[str, Any]:
    """Función pura: notas -> entidades con menciones y relaciones."""
    formas: dict[str, Counter] = defaultdict(Counter)
    menciones: dict[str, list[dict[str, str]]] = defaultdict(list)

    for nota in notas:
        vistas: set[str] = set()

        for nombre in nota["entidades"]:
            clave = nombre.casefold()
            formas[clave][nombre] += 1

            if clave in vistas:
                continue

            vistas.add(clave)
            menciones[clave].append({"stem": nota["stem"], "titulo": nota["titulo"]})

    elegidas = {c for c, lista in menciones.items() if len(lista) >= min_menciones}

    # colisiones de slug: se queda la entidad más mencionada
    por_slug: dict[str, list[str]] = defaultdict(list)

    for clave in elegidas:
        por_slug[slugify(formas[clave].most_common(1)[0][0])].append(clave)

    colisiones: list[list[str]] = []
    finales: set[str] = set()

    for slug, claves in por_slug.items():
        claves.sort(key=lambda c: (-len(menciones[c]), c))
        finales.add(claves[0])

        if len(claves) > 1:
            colisiones.append([formas[c].most_common(1)[0][0] for c in claves])

    co: Counter = Counter()

    for nota in notas:
        presentes = sorted({n.casefold() for n in nota["entidades"]} & finales)

        for a, b in combinations(presentes, 2):
            co[(a, b)] += 1

    relaciones: dict[str, list[tuple[str, int]]] = defaultdict(list)

    for (a, b), peso in co.items():
        relaciones[a].append((b, peso))
        relaciones[b].append((a, peso))

    entidades = {}

    for clave in finales:
        nombre = formas[clave].most_common(1)[0][0]
        rels = sorted(relaciones[clave], key=lambda par: (-par[1], par[0]))[:MAX_RELACIONES]
        entidades[clave] = {
            "nombre": nombre,
            "slug": slugify(nombre),
            "menciones": sorted(menciones[clave], key=lambda m: m["stem"]),
            "relaciones": [
                {"nombre": formas[otra].most_common(1)[0][0], "slug": slugify(formas[otra].most_common(1)[0][0]), "peso": peso}
                for otra, peso in rels
                if otra in finales
            ],
        }

    return {"entidades": entidades, "colisiones": colisiones}


def render_nota(entidad: dict[str, Any]) -> str:
    lineas = [f"Entidad mencionada en {len(entidad['menciones'])} notas.", "", "## Menciones", ""]

    for m in entidad["menciones"]:
        lineas.append(f"- [[{m['stem']}|{m['titulo']}]]")

    lineas += ["", "## Relacionadas", ""]

    if entidad["relaciones"]:
        for r in entidad["relaciones"]:
            lineas.append(f"- [[{r['slug']}|{r['nombre']}]] ({r['peso']} notas en común)")
    else:
        lineas.append("- Sin relaciones.")

    return "\n".join(lineas) + "\n"


def _cuerpo_existente(ruta: Path) -> str | None:
    if not ruta.exists():
        return None

    texto = ruta.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n.*?\n---\s*\n?", texto, re.DOTALL)
    return (texto[m.end():] if m else texto).strip()


def generar(
    *, min_menciones: int = 2, dry_run: bool = False, limpiar: bool = False
) -> dict[str, Any]:
    from escritor import actualizar_frontmatter, crear_nota, eliminar_nota

    config = cargar_config()
    preparar_carpetas(config)
    carpeta_rel = (config.notas / CARPETA_ENTIDADES).relative_to(config.boveda).as_posix()
    carpeta_abs = config.boveda / carpeta_rel

    notas = _leer_notas(config)
    grafo = construir_grafo(notas, min_menciones=min_menciones)
    resultado: dict[str, Any] = {
        "notas_leidas": len(notas),
        "entidades": len(grafo["entidades"]),
        "creadas": [],
        "actualizadas": [],
        "sin_cambios": 0,
        "obsoletas": [],
        "colisiones": grafo["colisiones"],
        "dry_run": dry_run,
    }

    esperadas = set()

    for entidad in sorted(grafo["entidades"].values(), key=lambda e: e["slug"]):
        esperadas.add(entidad["slug"] + ".md")
        destino = carpeta_abs / f"{entidad['slug']}.md"
        cuerpo = render_nota(entidad)
        existente = _cuerpo_existente(destino)

        if existente is not None and existente == cuerpo.strip():
            resultado["sin_cambios"] += 1
            continue

        clave = "actualizadas" if existente is not None else "creadas"
        resultado[clave].append(entidad["nombre"])

        if dry_run:
            continue

        r = crear_nota(
            entidad["nombre"],
            cuerpo,
            carpeta=carpeta_rel,
            tags=["entidad"],
            fuente="entidades",
            confianza=1.0,
            actor="entidades",
            motivo="grafo",
            sobrescribir=True,
        )

        if r.ok:
            actualizar_frontmatter(
                r.ruta.relative_to(config.boveda),
                {
                    "aliases": [entidad["nombre"]],
                    "tipo": "entidad",
                    "menciones": len(entidad["menciones"]),
                },
                actor="entidades",
                motivo="grafo",
                backup=False,
            )

    if carpeta_abs.exists():
        for ruta in sorted(carpeta_abs.glob("*.md")):
            if ruta.name not in esperadas:
                resultado["obsoletas"].append(ruta.name)

                if limpiar and not dry_run:
                    eliminar_nota(
                        ruta.relative_to(config.boveda),
                        actor="entidades",
                        motivo="entidad_obsoleta",
                    )

    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el grafo de entidades.")
    parser.add_argument("--min-menciones", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limpiar", action="store_true", help="Mueve a la papelera las obsoletas.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    latir("entidades")

    with medir("entidades", "generar") as registro:
        resultado = generar(
            min_menciones=max(1, args.min_menciones),
            dry_run=args.dry_run,
            limpiar=args.limpiar,
        )
        registro["salida"] = {k: v for k, v in resultado.items() if not isinstance(v, list)}

    if not args.dry_run:
        emitir_evento(
            "entidades.ciclo.ok",
            payload={
                "entidades": resultado["entidades"],
                "creadas": len(resultado["creadas"]),
                "actualizadas": len(resultado["actualizadas"]),
            },
        )

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print(
            f"Notas leídas: {resultado['notas_leidas']} | Entidades: {resultado['entidades']} | "
            f"Creadas: {len(resultado['creadas'])} | Actualizadas: {len(resultado['actualizadas'])} | "
            f"Sin cambios: {resultado['sin_cambios']} | Obsoletas: {len(resultado['obsoletas'])}"
        )

        if resultado["colisiones"]:
            print(f"Colisiones de nombre (se conservó la más mencionada): {resultado['colisiones']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
