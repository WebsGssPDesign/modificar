"""
memoria.py — Núcleo de memoria vectorial.

Responsabilidades:
- Crear y mantener SQLite + FTS5.
- Convertir Markdown en chunks.
- Guardar embeddings.
- Buscar por texto, semántica y método híbrido RRF.

No decide qué aprender ni escribe notas: eso corresponde a otras fases.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from config import cargar_config
from embeddings import embed_one, embed_texts, modelo_actual
from incidencias import registrar
from util import lock_archivo, timestamp_iso

SCHEMA_VERSION = 1

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    id: str
    ruta: str
    titulo: str
    encabezado: str
    contenido: str
    orden: int
    hash_archivo: str
    actualizado: str


@dataclass(frozen=True)
class Resultado:
    chunk_id: str
    ruta: str
    titulo: str
    encabezado: str
    contenido: str
    score: float
    metodo: str
    rank_fts: int | None = None
    rank_vec: int | None = None


def conectar(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")

    return connection


def inicializar_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS archivos (
            ruta TEXT PRIMARY KEY,
            hash TEXT NOT NULL,
            titulo TEXT NOT NULL,
            actualizado TEXT NOT NULL,
            chunks INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            ruta TEXT NOT NULL,
            titulo TEXT NOT NULL,
            encabezado TEXT NOT NULL,
            contenido TEXT NOT NULL,
            orden INTEGER NOT NULL,
            hash_archivo TEXT NOT NULL,
            embedding BLOB,
            modelo_embedding TEXT,
            actualizado TEXT NOT NULL,
            FOREIGN KEY (ruta) REFERENCES archivos(ruta) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_ruta ON chunks(ruta);
        CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(hash_archivo);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            titulo,
            encabezado,
            contenido,
            content='chunks',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        );

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, titulo, encabezado, contenido)
            VALUES (new.rowid, new.titulo, new.encabezado, new.contenido);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, titulo, encabezado, contenido)
            VALUES ('delete', old.rowid, old.titulo, old.encabezado, old.contenido);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, titulo, encabezado, contenido)
            VALUES ('delete', old.rowid, old.titulo, old.encabezado, old.contenido);
            INSERT INTO chunks_fts(rowid, titulo, encabezado, contenido)
            VALUES (new.rowid, new.titulo, new.encabezado, new.contenido);
        END;
        """
    )

    connection.execute(
        """
        INSERT INTO meta(clave, valor)
        VALUES ('schema_version', ?)
        ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
        """,
        (str(SCHEMA_VERSION),),
    )

    connection.commit()


def _hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _leer_frontmatter(texto: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(texto)

    if not match:
        return {}, texto

    frontmatter_raw = match.group(1)
    cuerpo = texto[match.end():]

    datos: dict[str, Any] = {}

    for linea in frontmatter_raw.splitlines():
        if ":" not in linea:
            continue

        clave, valor = linea.split(":", 1)
        datos[clave.strip().lower()] = valor.strip().strip('"').strip("'")

    return datos, cuerpo


def _quitar_codigo_excesivo(texto: str, max_lineas_codigo: int = 40) -> str:
    """
    Conserva bloques de código cortos, pero evita que un archivo enorme
    de código domine el índice.
    """
    lineas = texto.splitlines()
    salida: list[str] = []
    dentro_codigo = False
    contador = 0

    for linea in lineas:
        if linea.strip().startswith("```"):
            contador = 0
            dentro_codigo = not dentro_codigo
            salida.append(linea)
            continue

        if dentro_codigo:
            contador += 1

            if contador <= max_lineas_codigo:
                salida.append(linea)
            elif contador == max_lineas_codigo + 1:
                salida.append("... [código truncado] ...")

            continue

        salida.append(linea)

    return "\n".join(salida)


def dividir_en_chunks(
    texto: str,
    *,
    max_chars: int = 1200,
    solapamiento: int = 150,
) -> list[str]:
    """
    Divide por encabezados y, si un bloque sigue siendo largo, por párrafos.
    """
    texto = _quitar_codigo_excesivo(texto).strip()

    if not texto:
        return []

    bloques: list[str] = []
    ultimo_fin = 0
    encabezados = list(HEADING_RE.finditer(texto))

    if not encabezados:
        bloques.append(texto)
    else:
        primero = encabezados[0]

        if primero.start() > 0:
            bloques.append(texto[: primero.start()].strip())

        for i, match in enumerate(encabezados):
            inicio = match.start()
            fin = encabezados[i + 1].start() if i + 1 < len(encabezados) else len(texto)
            bloque = texto[inicio:fin].strip()

            if bloque:
                bloques.append(bloque)

    chunks: list[str] = []

    for bloque in bloques:
        if len(bloque) <= max_chars:
            chunks.append(bloque)
            continue

        parrafos = [p.strip() for p in bloque.split("\n\n") if p.strip()]
        actual = ""

        for parrafo in parrafos:
            candidato = f"{actual}\n\n{parrafo}".strip() if actual else parrafo

            if len(candidato) <= max_chars:
                actual = candidato
                continue

            if actual:
                chunks.append(actual)

            if len(parrafo) <= max_chars:
                actual = parrafo
                continue

            inicio = 0

            while inicio < len(parrafo):
                fin = min(inicio + max_chars, len(parrafo))
                chunks.append(parrafo[inicio:fin].strip())
                inicio = fin - solapamiento if fin < len(parrafo) else fin

            actual = ""

        if actual:
            chunks.append(actual)

    return [chunk for chunk in chunks if chunk.strip()]


def _titulo_de_archivo(ruta: Path, frontmatter: dict[str, Any]) -> str:
    if "titulo" in frontmatter:
        return str(frontmatter["titulo"])

    if "title" in frontmatter:
        return str(frontmatter["title"])

    return ruta.stem


def _encabezado_de_chunk(chunk: str) -> str:
    match = HEADING_RE.search(chunk)
    return match.group(2).strip() if match else ""


def extraer_chunks(
    ruta: Path,
    *,
    max_chars: int = 1200,
) -> tuple[str, list[Chunk]]:
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    frontmatter, cuerpo = _leer_frontmatter(texto)

    hash_archivo = _hash_texto(texto)
    titulo = _titulo_de_archivo(ruta, frontmatter)
    partes = dividir_en_chunks(cuerpo, max_chars=max_chars)

    try:
        ruta_relativa = ruta.relative_to(cargar_config().boveda).as_posix()
    except ValueError:
        ruta_relativa = ruta.as_posix()

    chunks = [
        Chunk(
            id=hashlib.sha1(
                f"{ruta_relativa}:{i}:{_hash_texto(parte)}".encode("utf-8")
            ).hexdigest(),
            ruta=ruta_relativa,
            titulo=titulo,
            encabezado=_encabezado_de_chunk(parte),
            contenido=parte,
            orden=i,
            hash_archivo=hash_archivo,
            actualizado=timestamp_iso(),
        )
        for i, parte in enumerate(partes)
    ]

    return hash_archivo, chunks


def _debe_indexar(
    ruta: Path,
    config,
    carpetas_excluidas: set[str],
    archivos_ignorados: set[str],
) -> bool:
    if ruta.suffix.lower() not in {".md", ".markdown", ".txt"}:
        return False

    relativa = ruta.relative_to(config.boveda).as_posix()
    nombre = ruta.name

    if nombre.lower() in archivos_ignorados:
        return False

    for carpeta in carpetas_excluidas:
        carpeta_limpia = carpeta.strip("/\\").replace("\\", "/")

        if relativa == carpeta_limpia or relativa.startswith(carpeta_limpia + "/"):
            return False

    return True


def _archivos_candidatos(config) -> list[Path]:
    carpetas_excluidas = set(config.indice_excluir)
    archivos_ignorados = {nombre.lower() for nombre in config.indice_ignorar_archivos}

    return [
        ruta
        for ruta in config.boveda.rglob("*")
        if ruta.is_file() and _debe_indexar(ruta, config, carpetas_excluidas, archivos_ignorados)
    ]


def indexar_archivo(
    connection: sqlite3.Connection,
    ruta: Path,
    *,
    recalcular_embeddings: bool = True,
    batch_size: int = 16,
    forzar: bool = False,
) -> tuple[int, int]:
    """
    Indexa o actualiza un archivo. Devuelve (chunks_nuevos, chunks_eliminados).
    """
    config = cargar_config()
    hash_archivo, chunks = extraer_chunks(ruta)

    ruta_relativa = ruta.relative_to(config.boveda).as_posix()
    titulo = chunks[0].titulo if chunks else ruta.stem

    anterior = connection.execute(
        "SELECT hash FROM archivos WHERE ruta = ?",
        (ruta_relativa,),
    ).fetchone()

    if not forzar and anterior and anterior["hash"] == hash_archivo:
        return 0, 0

    chunks_anteriores = connection.execute(
        "SELECT COUNT(*) AS total FROM chunks WHERE ruta = ?",
        (ruta_relativa,),
    ).fetchone()["total"]

    connection.execute("DELETE FROM chunks WHERE ruta = ?", (ruta_relativa,))
    connection.execute("DELETE FROM archivos WHERE ruta = ?", (ruta_relativa,))

    if not chunks:
        connection.commit()
        return 0, int(chunks_anteriores)

    connection.execute(
        """
        INSERT INTO archivos(ruta, hash, titulo, actualizado, chunks)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ruta_relativa, hash_archivo, titulo, timestamp_iso(), len(chunks)),
    )

    embeddings = None

    if recalcular_embeddings:
        textos = [chunk.contenido for chunk in chunks]
        embeddings = embed_texts(textos)

    for i, chunk in enumerate(chunks):
        embedding_blob = None
        modelo_embedding = None

        if embeddings is not None:
            embedding_blob = embeddings[i].astype(np.float32).tobytes()
            modelo_embedding = modelo_actual()

        connection.execute(
            """
            INSERT INTO chunks(
                id, ruta, titulo, encabezado, contenido, orden,
                hash_archivo, embedding, modelo_embedding, actualizado
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.id,
                chunk.ruta,
                chunk.titulo,
                chunk.encabezado,
                chunk.contenido,
                chunk.orden,
                chunk.hash_archivo,
                embedding_blob,
                modelo_embedding,
                chunk.actualizado,
            ),
        )

    connection.commit()
    return len(chunks), int(chunks_anteriores)


def _podar_huerfanos(connection, config, archivos: list[Path], stats: dict[str, int]) -> None:
    """Elimina del índice los archivos que ya no existen o quedaron excluidos."""
    vigentes = {ruta.relative_to(config.boveda).as_posix() for ruta in archivos}
    indexados = [fila["ruta"] for fila in connection.execute("SELECT ruta FROM archivos")]

    for ruta in indexados:
        if ruta in vigentes:
            continue

        total = connection.execute(
            "SELECT COUNT(*) AS total FROM chunks WHERE ruta = ?", (ruta,)
        ).fetchone()["total"]
        connection.execute("DELETE FROM chunks WHERE ruta = ?", (ruta,))
        connection.execute("DELETE FROM archivos WHERE ruta = ?", (ruta,))
        stats["archivos_eliminados"] += 1
        stats["chunks_eliminados"] += int(total)

    connection.commit()


def indexar_boveda(
    *,
    recalcular_embeddings: bool = True,
    batch_size: int = 16,
    forzar: bool = False,
) -> dict[str, int]:
    config = cargar_config()
    archivos = _archivos_candidatos(config)

    stats = {
        "archivos": 0,
        "archivos_actualizados": 0,
        "chunks_nuevos": 0,
        "chunks_eliminados": 0,
        "archivos_eliminados": 0,
        "errores": 0,
    }

    with lock_archivo(config.db_path, timeout=30.0):
        connection = conectar(config.db_path)

        try:
            inicializar_db(connection)

            for ruta in archivos:
                stats["archivos"] += 1

                try:
                    nuevos, eliminados = indexar_archivo(
                        connection,
                        ruta,
                        recalcular_embeddings=recalcular_embeddings,
                        batch_size=batch_size,
                        forzar=forzar,
                    )

                    if nuevos or eliminados:
                        stats["archivos_actualizados"] += 1
                        stats["chunks_nuevos"] += nuevos
                        stats["chunks_eliminados"] += eliminados

                except Exception as exc:
                    stats["errores"] += 1
                    registrar(
                        "memoria.indexar",
                        f"Fallo al indexar {ruta.name}: {exc}",
                        gravedad="media",
                        detalle={"ruta": str(ruta)},
                    )

            _podar_huerfanos(connection, config, archivos, stats)

        finally:
            connection.close()

    return stats


def _escape_fts(consulta: str) -> str:
    """
    Convierte una consulta libre en una consulta FTS5 tolerante.
    """
    terminos = re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ]+", consulta)

    if not terminos:
        return ""

    return " OR ".join(f'"{termino}"' for termino in terminos)


def buscar_fts(
    connection: sqlite3.Connection,
    consulta: str,
    *,
    k: int = 20,
) -> list[tuple[str, float]]:
    consulta_fts = _escape_fts(consulta)

    if not consulta_fts:
        return []

    filas = connection.execute(
        """
        SELECT
            c.id,
            bm25(chunks_fts, 3.0, 2.0, 1.0) AS score
        FROM chunks_fts
        JOIN chunks c ON c.rowid = chunks_fts.rowid
        WHERE chunks_fts MATCH ?
        ORDER BY score
        LIMIT ?
        """,
        (consulta_fts, k),
    ).fetchall()

    return [(fila["id"], float(fila["score"])) for fila in filas]


def buscar_vectorial(
    connection: sqlite3.Connection,
    consulta: str,
    *,
    k: int = 20,
    modelo: str | None = None,
) -> list[tuple[str, float]]:
    vector_consulta = embed_one(consulta, modelo=modelo)

    filas = connection.execute(
        """
        SELECT id, embedding
        FROM chunks
        WHERE embedding IS NOT NULL
        """
    ).fetchall()

    if not filas:
        return []

    ids: list[str] = []
    vectores: list[np.ndarray] = []

    for fila in filas:
        vector = np.frombuffer(fila["embedding"], dtype=np.float32)

        if vector.size != vector_consulta.size:
            continue

        norma = np.linalg.norm(vector)

        if norma == 0.0:
            continue

        ids.append(fila["id"])
        vectores.append(vector / norma)

    if not ids:
        return []

    matriz = np.vstack(vectores)
    similitudes = matriz @ vector_consulta
    orden = np.argsort(-similitudes)[:k]

    return [(ids[i], float(similitudes[i])) for i in orden]


def _rrf(
    resultados: list[list[tuple[str, float]]],
    *,
    k: int = 60,
    limite: int = 20,
) -> list[tuple[str, float, dict[str, int | None]]]:
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int | None]] = {}

    for metodo, resultados_metodo in zip(("fts", "vec"), resultados):
        for rank, (chunk_id, _score) in enumerate(resultados_metodo, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            ranks.setdefault(chunk_id, {})[metodo] = rank

    orden = sorted(scores.items(), key=lambda item: -item[1])[:limite]
    return [(chunk_id, score, ranks.get(chunk_id, {})) for chunk_id, score in orden]


def buscar_hibrido(
    consulta: str,
    *,
    k: int = 10,
    candidatos: int = 30,
    modelo: str | None = None,
) -> list[Resultado]:
    config = cargar_config()

    with lock_archivo(config.db_path, timeout=10.0):
        connection = conectar(config.db_path)

        try:
            inicializar_db(connection)

            fts = buscar_fts(connection, consulta, k=candidatos)
            vec = buscar_vectorial(connection, consulta, k=candidatos, modelo=modelo)

            fusion = _rrf([fts, vec], limite=k)

            resultados: list[Resultado] = []

            for chunk_id, score, ranks in fusion:
                fila = connection.execute(
                    """
                    SELECT id, ruta, titulo, encabezado, contenido
                    FROM chunks
                    WHERE id = ?
                    """,
                    (chunk_id,),
                ).fetchone()

                if not fila:
                    continue

                resultados.append(
                    Resultado(
                        chunk_id=fila["id"],
                        ruta=fila["ruta"],
                        titulo=fila["titulo"],
                        encabezado=fila["encabezado"],
                        contenido=fila["contenido"],
                        score=round(score, 6),
                        metodo="hibrido",
                        rank_fts=ranks.get("fts"),
                        rank_vec=ranks.get("vec"),
                    )
                )

            return resultados

        finally:
            connection.close()


def estado_indice() -> dict[str, Any]:
    config = cargar_config()

    if not config.db_path.exists():
        return {
            "archivos": 0,
            "chunks": 0,
            "con_embedding": 0,
            "db": str(config.db_path),
            "existe": False,
        }

    connection = conectar(config.db_path)
    inicializar_db(connection)

    try:
        archivos = connection.execute("SELECT COUNT(*) AS total FROM archivos").fetchone()["total"]
        chunks = connection.execute("SELECT COUNT(*) AS total FROM chunks").fetchone()["total"]
        con_embedding = connection.execute(
            "SELECT COUNT(*) AS total FROM chunks WHERE embedding IS NOT NULL"
        ).fetchone()["total"]

        return {
            "archivos": int(archivos),
            "chunks": int(chunks),
            "con_embedding": int(con_embedding),
            "db": str(config.db_path),
            "existe": True,
        }
    finally:
        connection.close()
