"""
analisis.py — Análisis de cobertura, huecos y conocimiento.

Genera datos para:
- Huecos.md
- Conocimiento.md
- Tablero.md

No escribe notas directamente: devuelve estructuras que tablero.py publica.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import cargar_config
from memoria import conectar, inicializar_db
from util import leer_json, timestamp_iso

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


@dataclass
class Analisis:
    generado: str
    total_archivos: int
    total_chunks: int
    total_notas_generadas: int
    temas: list[dict[str, Any]]
    huecos: list[dict[str, Any]]
    emergentes: list[dict[str, Any]]
    activas: list[dict[str, Any]]
    dominadas: list[dict[str, Any]]
    huerfanas: list[str]


def _tags_de_frontmatter(texto: str) -> list[str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", texto, re.DOTALL)

    if not match:
        return []

    frontmatter = match.group(1)
    tags: list[str] = []
    dentro_tags = False

    for linea in frontmatter.splitlines():
        limpia = linea.strip()

        if limpia.startswith("tags:"):
            valor = limpia.split(":", 1)[1].strip()
            dentro_tags = not valor
            tags.extend(t.strip().strip("\"'") for t in valor.strip("[]").split(",") if t.strip().strip("\"'"))
            continue

        if dentro_tags and limpia.startswith("- "):
            tags.append(limpia[2:].strip().strip("\"'"))
            continue

        if dentro_tags and not limpia.startswith("- "):
            dentro_tags = False

    return tags


def _entidades_de_texto(texto: str) -> list[str]:
    return [match.strip() for match in WIKILINK_RE.findall(texto)]


CARPETAS_CONOCIMIENTO = ("Hechos", "Web")


def _leer_notas_generadas(config) -> list[dict[str, Any]]:
    """Notas aprendidas por el sistema: locales (Hechos) y de la web (Web)."""
    notas: list[dict[str, Any]] = []

    rutas = []

    for nombre in CARPETAS_CONOCIMIENTO:
        carpeta = config.boveda / "LLM-Memoria" / nombre

        if carpeta.exists():
            rutas.extend(sorted(carpeta.rglob("*.md")))

    for ruta in rutas:
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        tags = _tags_de_frontmatter(texto)
        entidades = _entidades_de_texto(texto)

        confianza = 0.0
        match_confianza = re.search(r"^confianza:\s*([0-9.]+)", texto, re.MULTILINE)

        if match_confianza:
            try:
                confianza = float(match_confianza.group(1))
            except ValueError:
                pass

        notas.append(
            {
                "ruta": ruta.relative_to(config.boveda).as_posix(),
                "titulo": ruta.stem,
                "tags": tags,
                "entidades": entidades,
                "confianza": confianza,
                "texto": texto,
            }
        )

    return notas


def _perfil_intereses(config) -> list[str]:
    """Nombres de los intereses (formato viejo o nuevo de intereses.json)."""
    from perfil import _normalizar_intereses

    ruta = config.perfil / "intereses.json"

    if not ruta.exists():
        return []

    return [i["nombre"] for i in _normalizar_intereses(leer_json(ruta, []))]


def _normalizar(texto: str) -> str:
    return texto.strip().lower()


def analizar() -> Analisis:
    config = cargar_config()
    estado = leer_json(config.memoria_dir / "indice_estado.json", {})

    connection = conectar(config.db_path)
    inicializar_db(connection)

    try:
        total_archivos = connection.execute(
            "SELECT COUNT(*) AS total FROM archivos"
        ).fetchone()["total"]

        total_chunks = connection.execute(
            "SELECT COUNT(*) AS total FROM chunks"
        ).fetchone()["total"]
    finally:
        connection.close()

    notas = _leer_notas_generadas(config)
    intereses = _perfil_intereses(config)

    contador_temas: Counter[str] = Counter()
    confianza_tema: defaultdict[str, list[float]] = defaultdict(list)
    entidades: Counter[str] = Counter()

    for nota in notas:
        for tag in nota["tags"]:
            tema = _normalizar(tag)
            contador_temas[tema] += 1
            confianza_tema[tema].append(nota["confianza"])

        for entidad in nota["entidades"]:
            entidades[_normalizar(entidad)] += 1

    temas = []

    for tema, cantidad in contador_temas.most_common():
        confianzas = confianza_tema[tema]
        temas.append(
            {
                "tema": tema,
                "notas": cantidad,
                "confianza_media": round(sum(confianzas) / len(confianzas), 3),
                "entidades": [
                    entidad
                    for entidad, veces in entidades.items()
                    if _normalizar(entidad) == tema or tema in _normalizar(entidad)
                ],
            }
        )

    huecos = []

    for interes in intereses:
        clave = _normalizar(interes)
        coincidencias = sum(
            1
            for tema in contador_temas
            if clave in tema or tema in clave
        )

        if coincidencias == 0:
            huecos.append(
                {
                    "interes": interes,
                    "motivo": "Sin notas ni tags relacionados",
                }
            )
        elif coincidencias == 1:
            huecos.append(
                {
                    "interes": interes,
                    "motivo": "Solo una nota relacionada; cobertura muy baja",
                }
            )

    emergentes = [
        tema
        for tema in temas
        if 2 <= tema["notas"] <= 4
    ]

    activas = [
        tema
        for tema in temas
        if 5 <= tema["notas"] <= 9
    ]

    dominadas = [
        tema
        for tema in temas
        if tema["notas"] >= 10 and tema["confianza_media"] >= 0.75
    ]

    rutas_notas = {nota["ruta"] for nota in notas}
    huerfanas = []

    for nota in notas:
        enlaces = [
            enlace.strip()
            for enlace in nota["entidades"]
            if enlace.strip()
        ]

        if not enlaces and nota["confianza"] < 0.8:
            huerfanas.append(nota["ruta"])

    return Analisis(
        generado=timestamp_iso(),
        total_archivos=int(total_archivos),
        total_chunks=int(total_chunks),
        total_notas_generadas=len(notas),
        temas=temas,
        huecos=huecos,
        emergentes=emergentes,
        activas=activas,
        dominadas=dominadas,
        huerfanas=huerfanas,
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Analiza cobertura y huecos.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--revisar", action="store_true")

    args = parser.parse_args()
    analisis = analizar()

    if args.json:
        print(
            json.dumps(
                analisis.__dict__,
                ensure_ascii=False,
                indent=2,
                default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
            )
        )
        return 0

    print(f"Archivos indexados: {analisis.total_archivos}")
    print(f"Chunks: {analisis.total_chunks}")
    print(f"Notas generadas: {analisis.total_notas_generadas}")
    print(f"Temas detectados: {len(analisis.temas)}")
    print(f"Huecos: {len(analisis.huecos)}")
    print(f"Notas huérfanas: {len(analisis.huerfanas)}")

    return 0


if __name__ == "__main__":
    main()
