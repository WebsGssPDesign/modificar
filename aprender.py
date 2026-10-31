"""
aprender.py — Aprendizaje local desde documentos de la bóveda.

Flujo:
1. Selecciona archivos Markdown permitidos.
2. Comprueba si ya fueron procesados.
3. Recupera contexto similar desde el índice.
4. Pide al LLM una propuesta JSON.
5. Comprueba duplicados semánticos.
6. Publica la nota solo mediante escritor.py.

El LLM no elige rutas ni escribe archivos.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
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
from memoria import (
    buscar_hibrido,
    conectar,
    extraer_chunks,
    inicializar_db,
)
from metricas import medir
from util import (
    leer_json,
    lock_archivo,
    ruta_relativa_segura,
    slugify,
    timestamp_iso,
    escribir_json_atomico,
)

ESTADO_PATH = Path(".memoria") / "aprender_estado.json"

PROMPT_SISTEMA = """Eres un extractor de conocimiento para un segundo cerebro técnico personal.

Reglas absolutas:
- No inventes información.
- No incluyas opiniones no presentes en el documento.
- No repitas texto literal extenso.
- Devuelve exclusivamente un objeto JSON válido.
- Si el documento no contiene conocimiento útil, marca util=False.

Debes identificar conocimiento reutilizable: decisiones, procedimientos, conceptos,
configuraciones, errores y soluciones, límites, relaciones entre tecnologías o lecciones.

El JSON debe tener esta forma:
{
  "util": true,
  "titulo": "string corto y específico",
  "resumen": "2 o 3 frases",
  "hechos": ["hecho breve 1", "hecho breve 2"],
  "tags": ["tag1", "tag2"],
  "entidades": ["React", "SQLite"],
  "confianza": 0.0,
  "motivo_descarte": ""
}
"""

PROMPT_USUARIO = """Documento:
---
{documento}
---

Contexto ya existente en la memoria:
---
{contexto}
---

Perfil e intereses del usuario:
---
{perfil}
---

Extrae el conocimiento nuevo y relevante.
Si el documento repite lo que ya está en el contexto, marca util=false y explica el motivo.
"""


@dataclass
class Propuesta:
    util: bool
    titulo: str
    resumen: str
    hechos: list[str]
    tags: list[str]
    entidades: list[str]
    confianza: float
    motivo_descarte: str


def _cargar_estado(config) -> dict[str, Any]:
    estado_path = config.memoria_dir / "aprender_estado.json"
    data = leer_json(estado_path, {})

    if not isinstance(data, dict):
        return {"archivos": {}, "actualizado": None}

    data.setdefault("archivos", {})
    return data


def _guardar_estado(config, estado: dict[str, Any]) -> None:
    estado["actualizado"] = timestamp_iso()
    escribir_json_atomico(
        config.memoria_dir / "aprender_estado.json",
        estado,
    )


def _recortar_documento(texto: str, max_chars: int) -> str:
    texto = texto.strip()

    if len(texto) <= max_chars:
        return texto

    cabeza = texto[: int(max_chars * 0.7)]
    cola = texto[-int(max_chars * 0.3) :]

    return f"{cabeza}\n\n... [contenido intermedio omitido] ...\n\n{cola}"


def _contexto_memoria(consulta: str, k: int = 5) -> str:
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
            f"Contenido: {resultado.contenido[:700]}"
        )

    return "\n\n---\n\n".join(bloques)


def _perfil_contexto(config) -> str:
    perfil_path = config.perfil / "perfil_usuario.json"

    if not perfil_path.exists():
        return "No hay perfil disponible."

    try:
        data = json.loads(perfil_path.read_text(encoding="utf-8"))
        return json.dumps(data, ensure_ascii=False, indent=2)
    except (OSError, json.JSONDecodeError):
        return "No hay perfil disponible."


def _validar_propuesta(datos: dict[str, Any]) -> Propuesta:
    util = bool(datos.get("util", False))

    titulo = str(datos.get("titulo", "")).strip()
    resumen = str(datos.get("resumen", "")).strip()
    hechos = [str(x).strip() for x in datos.get("hechos", []) if str(x).strip()]
    tags = [str(x).strip() for x in datos.get("tags", []) if str(x).strip()]
    entidades = [str(x).strip() for x in datos.get("entidades", []) if str(x).strip()]

    try:
        confianza = float(datos.get("confianza", 0.0))
    except (TypeError, ValueError):
        confianza = 0.0

    confianza = max(0.0, min(1.0, confianza))
    motivo = str(datos.get("motivo_descarte", "")).strip()

    return Propuesta(
        util=util,
        titulo=titulo,
        resumen=resumen,
        hechos=hechos,
        tags=tags,
        entidades=entidades,
        confianza=confianza,
        motivo_descarte=motivo,
    )


def _es_duplicado(
    connection,
    propuesta: Propuesta,
    *,
    umbral: float = 0.88,
) -> tuple[bool, float | None]:
    """
    Compara el resumen propuesto con los embeddings existentes.
    """
    texto = f"{propuesta.titulo}\n{propuesta.resumen}\n" + "\n".join(propuesta.hechos)

    try:
        vector = embed_one(texto)
    except Exception:
        return False, None

    filas = connection.execute(
        "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
    ).fetchall()

    if not filas:
        return False, None

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


def _cuerpo_nota(
    propuesta: Propuesta,
    ruta_fuente: str,
) -> str:
    hechos = "\n".join(f"- {hecho}" for hecho in propuesta.hechos) or "- Sin hechos extraídos."
    entidades = ", ".join(
        f"[[{e.replace('[', '').replace(']', '').replace('|', ' ').strip()}]]"
        for e in propuesta.entidades
        if e.strip()
    ) or "-"

    return f"""## Resumen

{propuesta.resumen}

## Hechos

{hechos}

## Entidades

{entidades}

## Fuente

- `{ruta_fuente}`

## Estado

- Extraído automáticamente.
- Requiere revisión humana antes de considerarlo conocimiento consolidado.
"""


def aprender_archivo(
    ruta: Path,
    *,
    modelo: str | None = None,
    max_chars: int = 6000,
    umbral_duplicado: float = 0.88,
    dry_run: bool = False,
) -> dict[str, Any]:
    config = cargar_config()
    preparar_carpetas(config)

    ruta_relativa = ruta.relative_to(config.boveda).as_posix()
    texto = ruta.read_text(encoding="utf-8", errors="replace")

    if not texto.strip():
        return {
            "ruta": ruta_relativa,
            "resultado": "omitido",
            "motivo": "archivo vacío",
        }

    documento = _recortar_documento(texto, max_chars)
    contexto = _contexto_memoria(ruta.stem + " " + documento[:1000])
    perfil = _perfil_contexto(config)

    prompt = PROMPT_USUARIO.format(
        documento=documento,
        contexto=contexto,
        perfil=perfil,
    )

    try:
        datos = chat_json(
            PROMPT_SISTEMA,
            prompt,
            modelo=modelo,
            entrada_metrica=f"aprender:{ruta_relativa}",
        )
    except Exception as exc:
        incidencia_id = registrar(
            "aprender",
            f"No se pudo procesar {ruta_relativa}: {exc}",
            gravedad="media",
        )

        emitir_evento(
            "aprender.error",
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

    propuesta = _validar_propuesta(datos)

    if not propuesta.util:
        return {
            "ruta": ruta_relativa,
            "resultado": "descartado",
            "motivo": propuesta.motivo_descarte or "El modelo consideró el documento no útil",
        }

    if not propuesta.titulo or not propuesta.resumen:
        return {
            "ruta": ruta_relativa,
            "resultado": "descartado",
            "motivo": "Propuesta incompleta",
        }

    if propuesta.confianza < 0.55:
        return {
            "ruta": ruta_relativa,
            "resultado": "descartado",
            "motivo": f"Confianza insuficiente: {propuesta.confianza:.2f}",
        }

    connection = conectar(config.db_path)
    inicializar_db(connection)

    try:
        duplicado, similitud = _es_duplicado(
            connection,
            propuesta,
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

    carpeta = "LLM-Memoria/Hechos"
    titulo = propuesta.titulo
    cuerpo = _cuerpo_nota(propuesta, ruta_relativa)

    if dry_run:
        return {
            "ruta": ruta_relativa,
            "resultado": "propuesto",
            "titulo": titulo,
            "confianza": propuesta.confianza,
            "similitud_maxima": similitud,
            "carpeta_destino": carpeta,
        }

    from escritor import crear_nota

    resultado = crear_nota(
        titulo,
        cuerpo,
        carpeta=carpeta,
        tags=propuesta.tags,
        fuente=ruta_relativa,
        confianza=propuesta.confianza,
        actor="aprender",
        motivo="aprendizaje_local",
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
        "nota": str(resultado.ruta.relative_to(config.boveda)),
        "confianza": propuesta.confianza,
        "similitud_maxima": similitud,
    }


def _archivos_candidatos(config) -> list[Path]:
    excluidas = {
        carpeta.strip("/\\").replace("\\", "/")
        for carpeta in config.aprender_excluir
    }

    candidatos: list[Path] = []

    for ruta in config.boveda.rglob("*"):
        if not ruta.is_file() or ruta.suffix.lower() not in {".md", ".markdown", ".txt"}:
            continue

        relativa = ruta.relative_to(config.boveda).as_posix()

        if any(
            relativa == carpeta or relativa.startswith(carpeta + "/")
            for carpeta in excluidas
        ):
            continue

        candidatos.append(ruta)

    return sorted(candidatos)


def aprender_boveda(
    *,
    modelo: str | None = None,
    max_archivos: int | None = None,
    max_chars: int = 6000,
    umbral_duplicado: float = 0.88,
    dry_run: bool = False,
    reintentar_fallidos: bool = False,
) -> dict[str, Any]:
    config = cargar_config()
    estado = _cargar_estado(config)

    archivos = _archivos_candidatos(config)

    if max_archivos:
        archivos = archivos[:max_archivos]

    resumen = {
        "procesados": 0,
        "publicados": 0,
        "duplicados": 0,
        "descartados": 0,
        "errores": 0,
        "omitidos": 0,
        "propuestos": 0,
        "resultados": [],
    }

    latir("aprender", detalle={"archivos": len(archivos), "dry_run": dry_run})

    for ruta in archivos:
        ruta_relativa = ruta.relative_to(config.boveda).as_posix()
        registro_estado = estado["archivos"].get(ruta_relativa, {})

        if (
            not reintentar_fallidos
            and registro_estado.get("resultado") in {"publicado", "descartado", "duplicado"}
        ):
            resumen["omitidos"] += 1
            continue

        resumen["procesados"] += 1

        with medir("aprender", ruta_relativa) as metrica:
            resultado = aprender_archivo(
                ruta,
                modelo=modelo,
                max_chars=max_chars,
                umbral_duplicado=umbral_duplicado,
                dry_run=dry_run,
            )

        metrica["salida"] = resultado
        resumen["resultados"].append(resultado)

        estado_archivo = {
            "ts": timestamp_iso(),
            "resultado": resultado["resultado"],
            "motivo": resultado.get("motivo"),
        }

        if resultado["resultado"] == "publicado":
            estado_archivo["nota"] = resultado.get("nota")
            resumen["publicados"] += 1
        elif resultado["resultado"] == "duplicado":
            resumen["duplicados"] += 1
        elif resultado["resultado"] == "descartado":
            resumen["descartados"] += 1
        elif resultado["resultado"] == "propuesto":
            resumen["propuestos"] += 1
        elif resultado["resultado"] == "omitido":
            resumen["omitidos"] += 1
        else:
            resumen["errores"] += 1

        estado["archivos"][ruta_relativa] = estado_archivo
        _guardar_estado(config, estado)

    emitir_evento(
        "aprender.ciclo.ok",
        payload={
            "dry_run": dry_run,
            "procesados": resumen["procesados"],
            "publicados": resumen["publicados"],
            "duplicados": resumen["duplicados"],
            "errores": resumen["errores"],
        },
    )

    return resumen


def main() -> int:
    parser = argparse.ArgumentParser(description="Aprendizaje local desde la bóveda.")
    parser.add_argument("--modelo", default=None)
    parser.add_argument("--max", type=int, default=None)
    parser.add_argument("--max-chars", type=int, default=6000)
    parser.add_argument("--umbral-duplicado", type=float, default=0.88)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--check", action="store_true")

    args = parser.parse_args()

    config = cargar_config()
    preparar_carpetas(config)

    if args.check:
        print(f"Bóveda: {config.boveda}")
        print(f"Notas: {config.notas}")
        print(f"Modelo: {args.modelo or 'autodetectado'}")
        print(f"Máx. caracteres: {args.max_chars}")
        print(f"Umbral duplicado: {args.umbral_duplicado}")
        return 0

    try:
        resumen = aprender_boveda(
            modelo=args.modelo,
            max_archivos=args.max,
            max_chars=args.max_chars,
            umbral_duplicado=args.umbral_duplicado,
            dry_run=args.dry_run,
            reintentar_fallidos=args.retry_failed,
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
