"""
crear_skills.py — Genera procedimientos reutilizables desde notas de conocimiento.

Flujo:
1. Selecciona notas candidatas en LLM-Memoria/Hechos.
2. Recupera contexto relacionado desde el índice.
3. Pide al LLM una propuesta de skill en JSON.
4. Valida las seis secciones obligatorias.
5. Comprueba duplicados semánticos.
6. Publica en skills/ mediante escritor.py.

El LLM no elige rutas ni escribe archivos.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from config import cargar_config, preparar_carpetas
from embeddings import embed_one
from eventos import emitir_evento
from heartbeat import latir
from incidencias import registrar
from llm import chat_json
from memoria import buscar_hibrido, conectar, inicializar_db
from metricas import medir
from util import (
    leer_json,
    ruta_relativa_segura,
    slugify,
    timestamp_iso,
    escribir_json_atomico,
)

ESTADO_RELATIVO = ".memoria/skills_estado.json"

SECCIONES_OBLIGATORIAS = [
    "objetivo",
    "prerrequisitos",
    "pasos",
    "validacion",
    "errores_comunes",
    "referencias",
]

PROMPT_SISTEMA = """Eres un creador de procedimientos técnicos reutilizables.

Tu trabajo es convertir conocimiento documentado en un skill accionable.

Reglas absolutas:
- No inventes pasos que no se apoyen razonablemente en el material.
- No incluyas secretos, tokens, contraseñas ni rutas personales.
- Usa pasos concretos, verificables y ordenados.
- Si el material no contiene un procedimiento claro, marca util=false.
- Devuelve exclusivamente un objeto JSON válido.

El JSON debe tener exactamente esta forma:
{
  "util": true,
  "titulo": "string corto y específico",
  "proposito": "1 o 2 frases",
  "prerrequisitos": ["string"],
  "pasos": ["string"],
  "validacion": ["string"],
  "errores_comunes": [
    {"problema": "string", "solucion": "string"}
  ],
  "referencias": ["ruta o concepto"],
  "tags": ["string"],
  "confianza": 0.0,
  "motivo_descarte": ""
}
"""

PROMPT_USUARIO = """Nota fuente:
---
{nota}
---

Contexto relacionado de la memoria:
---
{contexto}
---

Convierte esta nota en un skill reutilizable.
Si no hay un procedimiento suficientemente claro, marca util=false.
"""


@dataclass
class Skill:
    util: bool
    titulo: str
    proposito: str
    prerrequisitos: list[str]
    pasos: list[str]
    validacion: list[str]
    errores_comunes: list[dict[str, str]]
    referencias: list[str]
    tags: list[str]
    confianza: float
    motivo_descarte: str


def _estado_path(config) -> Path:
    return config.memoria_dir / "skills_estado.json"


def _cargar_estado(config) -> dict[str, Any]:
    data = leer_json(_estado_path(config), {})

    if not isinstance(data, dict):
        return {"skills": {}, "actualizado": None}

    data.setdefault("skills", {})
    return data


def _guardar_estado(config, estado: dict[str, Any]) -> None:
    estado["actualizado"] = timestamp_iso()
    escribir_json_atomico(_estado_path(config), estado)


def _contexto(consulta: str, k: int = 5) -> str:
    try:
        resultados = buscar_hibrido(consulta, k=k, candidatos=20)
    except Exception:
        return "No hay contexto disponible."

    if not resultados:
        return "No hay contexto disponible."

    bloques = []

    for resultado in resultados:
        bloques.append(
            f"Fuente: {resultado.ruta}\n"
            f"Título: {resultado.titulo}\n"
            f"Contenido: {resultado.contenido[:800]}"
        )

    return "\n\n---\n\n".join(bloques)


def _lista_texto(valor: Any) -> list[str]:
    if not isinstance(valor, list):
        return []

    return [str(item).strip() for item in valor if str(item).strip()]


def _validar_skill(datos: dict[str, Any]) -> Skill:
    util = bool(datos.get("util", False))

    errores_raw = datos.get("errores_comunes", [])
    errores: list[dict[str, str]] = []

    if isinstance(errores_raw, list):
        for item in errores_raw:
            if isinstance(item, dict):
                problema = str(item.get("problema", "")).strip()
                solucion = str(item.get("solucion", "")).strip()

                if problema and solucion:
                    errores.append(
                        {"problema": problema, "solucion": solucion}
                    )

    try:
        confianza = float(datos.get("confianza", 0.0))
    except (TypeError, ValueError):
        confianza = 0.0

    return Skill(
        util=util,
        titulo=str(datos.get("titulo", "")).strip(),
        proposito=str(datos.get("proposito", "")).strip(),
        prerrequisitos=_lista_texto(datos.get("prerrequisitos", [])),
        pasos=_lista_texto(datos.get("pasos", [])),
        validacion=_lista_texto(datos.get("validacion", [])),
        errores_comunes=errores,
        referencias=_lista_texto(datos.get("referencias", [])),
        tags=_lista_texto(datos.get("tags", [])),
        confianza=max(0.0, min(1.0, confianza)),
        motivo_descarte=str(datos.get("motivo_descarte", "")).strip(),
    )


def _skill_completo(skill: Skill) -> bool:
    return all(
        [
            skill.titulo,
            skill.proposito,
            skill.prerrequisitos,
            skill.pasos,
            skill.validacion,
            skill.errores_comunes,
            skill.referencias,
        ]
    )


def _texto_skill(skill: Skill) -> str:
    return "\n".join(
        [
            skill.titulo,
            skill.proposito,
            *skill.prerrequisitos,
            *skill.pasos,
            *skill.validacion,
            *skill.referencias,
        ]
    )


def _es_duplicado(
    connection,
    skill: Skill,
    *,
    umbral: float = 0.90,
) -> tuple[bool, float | None]:
    try:
        vector = embed_one(_texto_skill(skill))
    except Exception:
        return False, None

    filas = connection.execute(
        "SELECT embedding FROM chunks WHERE embedding IS NOT NULL"
    ).fetchall()

    vectores = []

    for fila in filas:
        existente = np.frombuffer(fila["embedding"], dtype=np.float32)

        if existente.size != vector.size:
            continue

        norma = np.linalg.norm(existente)

        if norma == 0.0:
            continue

        vectores.append(existente / norma)

    if not vectores:
        return False, None

    similitudes = np.vstack(vectores) @ vector
    maxima = float(np.max(similitudes))

    return maxima >= umbral, maxima


def _cuerpo_skill(
    skill: Skill,
    ruta_fuente: str,
) -> str:
    prerrequisitos = "\n".join(f"- {x}" for x in skill.prerrequisitos)
    pasos = "\n".join(f"{i}. {x}" for i, x in enumerate(skill.pasos, start=1))
    validacion = "\n".join(f"- {x}" for x in skill.validacion)
    referencias = "\n".join(f"- {x}" for x in skill.referencias)

    errores = []

    for error in skill.errores_comunes:
        errores.append(
            f"- **Problema:** {error['problema']}\n"
            f"  **Solución:** {error['solucion']}"
        )

    errores_texto = "\n".join(errores) or "- No se identificaron errores comunes."

    return f"""## Objetivo

{skill.proposito}

## Prerrequisitos

{prerrequisitos}

## Pasos

{pasos}

## Validación

{validacion}

## Errores comunes

{errores_texto}

## Referencias

{referencias}

- Nota fuente: `{ruta_fuente}`

## Estado

- Skill generado automáticamente.
- Requiere revisión humana antes de considerarse definitivo.
"""


def crear_skill_de_nota(
    ruta: Path,
    *,
    modelo: str | None = None,
    umbral_duplicado: float = 0.90,
    dry_run: bool = False,
) -> dict[str, Any]:
    config = cargar_config()
    preparar_carpetas(config)

    ruta_relativa = ruta.relative_to(config.boveda).as_posix()

    try:
        nota = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "ruta": ruta_relativa,
            "resultado": "error",
            "motivo": str(exc),
        }

    if len(nota.strip()) < 300:
        return {
            "ruta": ruta_relativa,
            "resultado": "omitido",
            "motivo": "Nota demasiado corta para generar un skill",
        }

    contexto = _contexto(ruta.stem + "\n" + nota[:1200])

    prompt = PROMPT_USUARIO.format(
        nota=nota[:8000],
        contexto=contexto,
    )

    try:
        datos = chat_json(
            PROMPT_SISTEMA,
            prompt,
            modelo=modelo,
            max_tokens=1800,
            entrada_metrica=f"crear_skills:{ruta_relativa}",
        )
    except Exception as exc:
        incidencia_id = registrar(
            "crear_skills",
            f"No se pudo procesar {ruta_relativa}: {exc}",
            gravedad="media",
        )

        emitir_evento(
            "crear_skills.error",
            gravedad="media",
            payload={
                "incidencia": incidencia_id,
                "archivo": ruta_relativa,
            },
        )

        return {
            "ruta": ruta_relativa,
            "resultado": "error",
            "motivo": str(exc),
        }

    skill = _validar_skill(datos)

    if not skill.util:
        return {
            "ruta": ruta_relativa,
            "resultado": "descartado",
            "motivo": skill.motivo_descarte or "No hay procedimiento claro",
        }

    if not _skill_completo(skill):
        faltan = [
            seccion
            for seccion, vacia in {
                "titulo": not skill.titulo,
                "proposito": not skill.proposito,
                "prerrequisitos": not skill.prerrequisitos,
                "pasos": not skill.pasos,
                "validacion": not skill.validacion,
                "errores_comunes": not skill.errores_comunes,
                "referencias": not skill.referencias,
            }.items()
            if vacia
        ]

        return {
            "ruta": ruta_relativa,
            "resultado": "descartado",
            "motivo": f"Skill incompleto; faltan: {', '.join(faltan)}",
        }

    if skill.confianza < 0.60:
        return {
            "ruta": ruta_relativa,
            "resultado": "descartado",
            "motivo": f"Confianza insuficiente: {skill.confianza:.2f}",
        }

    connection = conectar(config.db_path)
    inicializar_db(connection)

    try:
        duplicado, similitud = _es_duplicado(
            connection,
            skill,
            umbral=umbral_duplicado,
        )
    finally:
        connection.close()

    if duplicado:
        return {
            "ruta": ruta_relativa,
            "resultado": "duplicado",
            "motivo": f"Similitud máxima: {similitud:.3f}",
        }

    titulo = skill.titulo
    cuerpo = _cuerpo_skill(skill, ruta_relativa)
    carpeta = "skills"

    if dry_run:
        return {
            "ruta": ruta_relativa,
            "resultado": "propuesto",
            "titulo": titulo,
            "confianza": skill.confianza,
            "similitud_maxima": similitud,
            "carpeta_destino": carpeta,
        }

    from escritor import crear_nota

    resultado = crear_nota(
        titulo,
        cuerpo,
        carpeta=carpeta,
        tags=skill.tags,
        fuente=ruta_relativa,
        confianza=skill.confianza,
        actor="crear_skills",
        motivo="generacion_skill",
    )

    if not resultado.ok:
        return {
            "ruta": ruta_relativa,
            "resultado": "no_publicado",
            "motivo": resultado.mensaje,
        }

    return {
        "ruta": ruta_relativa,
        "resultado": "publicado",
        "skill": str(resultado.ruta.relative_to(config.boveda)),
        "confianza": skill.confianza,
        "similitud_maxima": similitud,
    }


def _notas_candidatas(config) -> list[Path]:
    carpeta = config.boveda / "LLM-Memoria" / "Hechos"

    if not carpeta.exists():
        return []

    return sorted(
        ruta
        for ruta in carpeta.rglob("*")
        if ruta.is_file() and ruta.suffix.lower() in {".md", ".markdown"}
    )


def crear_skills(
    *,
    modelo: str | None = None,
    max_skills: int | None = None,
    umbral_duplicado: float = 0.90,
    dry_run: bool = False,
    regenerar: bool = False,
) -> dict[str, Any]:
    config = cargar_config()
    estado = _cargar_estado(config)

    notas = _notas_candidatas(config)

    if max_skills:
        notas = notas[:max_skills]

    resumen = {
        "candidatas": len(notas),
        "procesadas": 0,
        "publicados": 0,
        "propuestos": 0,
        "duplicados": 0,
        "descartados": 0,
        "errores": 0,
        "omitidos": 0,
        "resultados": [],
    }

    latir(
        "crear_skills",
        detalle={
            "candidatas": len(notas),
            "dry_run": dry_run,
            "regenerar": regenerar,
        },
    )

    for ruta in notas:
        ruta_relativa = ruta.relative_to(config.boveda).as_posix()
        previo = estado["skills"].get(ruta_relativa, {})

        if (
            not regenerar
            and previo.get("resultado") in {"publicado", "descartado", "duplicado"}
        ):
            resumen["omitidos"] += 1
            continue

        resumen["procesadas"] += 1

        with medir("crear_skills", ruta_relativa) as metrica:
            resultado = crear_skill_de_nota(
                ruta,
                modelo=modelo,
                umbral_duplicado=umbral_duplicado,
                dry_run=dry_run,
            )

        metrica["salida"] = resultado
        resumen["resultados"].append(resultado)

        estado["skills"][ruta_relativa] = {
            "ts": timestamp_iso(),
            "resultado": resultado["resultado"],
            "motivo": resultado.get("motivo"),
        }

        if resultado["resultado"] == "publicado":
            estado["skills"][ruta_relativa]["skill"] = resultado.get("skill")
            resumen["publicados"] += 1
        elif resultado["resultado"] == "propuesto":
            resumen["propuestos"] += 1
        elif resultado["resultado"] == "duplicado":
            resumen["duplicados"] += 1
        elif resultado["resultado"] == "descartado":
            resumen["descartados"] += 1
        elif resultado["resultado"] == "omitido":
            resumen["omitidos"] += 1
        else:
            resumen["errores"] += 1

        _guardar_estado(config, estado)

    emitir_evento(
        "crear_skills.ciclo.ok",
        payload={
            "dry_run": dry_run,
            "procesadas": resumen["procesadas"],
            "publicados": resumen["publicados"],
            "duplicados": resumen["duplicados"],
            "errores": resumen["errores"],
        },
    )

    return resumen


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera skills desde notas de conocimiento.")
    parser.add_argument("--modelo", default=None)
    parser.add_argument("--max", type=int, default=None)
    parser.add_argument("--umbral-duplicado", type=float, default=0.90)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--regenerar", action="store_true")
    parser.add_argument("--check", action="store_true")

    args = parser.parse_args()

    config = cargar_config()
    preparar_carpetas(config)

    if args.check:
        print(f"Bóveda: {config.boveda}")
        print(f"Carpeta de skills: {config.boveda / 'skills'}")
        print(f"Modelo: {args.modelo or 'autodetectado'}")
        print(f"Umbral duplicado: {args.umbral_duplicado}")
        return 0

    try:
        resumen = crear_skills(
            modelo=args.modelo,
            max_skills=args.max,
            umbral_duplicado=args.umbral_duplicado,
            dry_run=args.dry_run,
            regenerar=args.regenerar,
        )
    except Exception as exc:
        print(f"Error general: {exc}")
        return 2

    print(json.dumps(resumen, ensure_ascii=False, indent=2))

    if resumen["errores"]:
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
