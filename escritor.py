"""
escritor.py — Puerta única de escritura en la bóveda.

Reglas:
- Ningún otro módulo debe usar Path.write_text, unlink o shutil directamente.
- Toda escritura deja auditoría.
- Sobrescribir crea .bak.
- Eliminar mueve a Sistema/papelera.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import cargar_config, preparar_carpetas
from util import (
    append_jsonl,
    lock_archivo,
    ruta_relativa_segura,
    slugify,
    timestamp_iso,
    escribir_texto_atomico,
)


@dataclass(frozen=True)
class ResultadoEscritura:
    ok: bool
    operacion: str
    ruta: Path
    mensaje: str
    backup: Path | None = None


def _hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _auditar(
    config,
    operacion: str,
    ruta: Path,
    actor: str,
    motivo: str,
    detalle: dict[str, Any] | None = None,
) -> None:
    registro = {
        "ts": timestamp_iso(),
        "operacion": operacion,
        "ruta": str(ruta.relative_to(config.boveda)),
        "actor": actor,
        "motivo": motivo,
        "detalle": detalle or {},
    }

    append_jsonl(config.auditoria_path, registro)


def _backup_si_existe(ruta: Path) -> Path | None:
    if not ruta.exists():
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = ruta.with_suffix(ruta.suffix + f".{stamp}.bak")
    shutil.copy2(ruta, backup)
    return backup


def crear_nota(
    titulo: str,
    cuerpo: str,
    *,
    carpeta: str = "",
    tags: list[str] | None = None,
    fuente: str = "local",
    confianza: float = 0.8,
    actor: str = "sistema",
    motivo: str = "creacion",
    sobrescribir: bool = False,
) -> ResultadoEscritura:
    config = cargar_config()
    preparar_carpetas(config)

    titulo_limpio = titulo.strip()
    if not titulo_limpio:
        raise ValueError("El título no puede estar vacío")

    slug = slugify(titulo_limpio)
    destino = config.boveda / carpeta / f"{slug}.md" if carpeta else config.boveda / f"{slug}.md"
    destino = ruta_relativa_segura(destino, config.boveda)

    if destino.exists() and not sobrescribir:
        return ResultadoEscritura(
            ok=False,
            operacion="crear",
            ruta=destino,
            mensaje="La nota ya existe y sobrescribir=False",
        )

    tags = tags or []
    frontmatter = [
        "---",
        f"titulo: {json.dumps(titulo_limpio, ensure_ascii=False)}",
        f"creado: {timestamp_iso()}",
        f"actualizado: {timestamp_iso()}",
        f"fuente: {fuente}",
        f"confianza: {confianza}",
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
        "estado: borrador",
        "---",
        "",
    ]

    contenido = "\n".join(frontmatter) + cuerpo.strip() + "\n"

    with lock_archivo(destino):
        backup = _backup_si_existe(destino) if destino.exists() else None
        escribir_texto_atomico(destino, contenido)

    _auditar(
        config,
        "crear",
        destino,
        actor,
        motivo,
        {
            "hash": _hash_texto(contenido),
            "backup": str(backup) if backup else None,
        },
    )

    return ResultadoEscritura(
        ok=True,
        operacion="crear",
        ruta=destino,
        mensaje="Nota creada",
        backup=backup,
    )


def editar_nota(
    ruta_relativa: str | Path,
    buscar: str,
    reemplazar: str,
    *,
    actor: str = "sistema",
    motivo: str = "edicion",
) -> ResultadoEscritura:
    config = cargar_config()
    destino = ruta_relativa_segura(ruta_relativa, config.boveda)

    if not destino.exists():
        return ResultadoEscritura(
            ok=False,
            operacion="editar",
            ruta=destino,
            mensaje="La nota no existe",
        )

    texto = destino.read_text(encoding="utf-8")

    if buscar not in texto:
        return ResultadoEscritura(
            ok=False,
            operacion="editar",
            ruta=destino,
            mensaje="El texto buscado no aparece en la nota",
        )

    nuevo_texto = texto.replace(buscar, reemplazar)

    with lock_archivo(destino):
        backup = _backup_si_existe(destino)
        escribir_texto_atomico(destino, nuevo_texto)

    _auditar(
        config,
        "editar",
        destino,
        actor,
        motivo,
        {
            "hash_anterior": _hash_texto(texto),
            "hash_nuevo": _hash_texto(nuevo_texto),
            "backup": str(backup) if backup else None,
        },
    )

    return ResultadoEscritura(
        ok=True,
        operacion="editar",
        ruta=destino,
        mensaje="Nota editada",
        backup=backup,
    )


def actualizar_frontmatter(
    ruta_relativa: str | Path,
    cambios: dict[str, Any],
    *,
    actor: str = "sistema",
    motivo: str = "frontmatter",
    backup: bool = True,
) -> ResultadoEscritura:
    """
    Añade o reemplaza claves del frontmatter de una nota, sin tocar el cuerpo.

    Los valores se escriben tal cual (str) o como JSON (listas, dicts, números,
    booleanos). Si la nota no tiene frontmatter, se crea uno nuevo.
    La operación queda auditada; el .bak puede omitirse con backup=False
    para campos de mantenimiento (por ejemplo, el calendario de repaso).
    """
    config = cargar_config()
    destino = ruta_relativa_segura(ruta_relativa, config.boveda)

    if not destino.exists():
        return ResultadoEscritura(
            ok=False,
            operacion="frontmatter",
            ruta=destino,
            mensaje="La nota no existe",
        )

    texto = destino.read_text(encoding="utf-8")
    lineas = texto.split("\n")

    if lineas and lineas[0].strip() == "---":
        try:
            fin = next(i for i in range(1, len(lineas)) if lineas[i].strip() == "---")
        except StopIteration:
            fin = None
    else:
        fin = None

    def _valor(v: Any) -> str:
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)

    if fin is None:
        cabecera = [f"{k}: {_valor(v)}" for k, v in cambios.items()]
        nuevo_texto = "\n".join(["---", *cabecera, "---", ""]) + texto
    else:
        bloque = lineas[1:fin]
        pendientes = dict(cambios)
        nuevas: list[str] = []

        for linea in bloque:
            clave = linea.split(":", 1)[0].strip() if ":" in linea else None
            if clave in pendientes:
                nuevas.append(f"{clave}: {_valor(pendientes.pop(clave))}")
            else:
                nuevas.append(linea)

        for clave, valor in pendientes.items():
            nuevas.append(f"{clave}: {_valor(valor)}")

        nuevo_texto = "\n".join([lineas[0], *nuevas, *lineas[fin:]])

    if nuevo_texto == texto:
        return ResultadoEscritura(
            ok=True,
            operacion="frontmatter",
            ruta=destino,
            mensaje="Sin cambios",
        )

    with lock_archivo(destino):
        copia = _backup_si_existe(destino) if backup else None
        escribir_texto_atomico(destino, nuevo_texto)

    _auditar(
        config,
        "frontmatter",
        destino,
        actor,
        motivo,
        {
            "claves": sorted(cambios),
            "hash_anterior": _hash_texto(texto),
            "hash_nuevo": _hash_texto(nuevo_texto),
            "backup": str(copia) if copia else None,
        },
    )

    return ResultadoEscritura(
        ok=True,
        operacion="frontmatter",
        ruta=destino,
        mensaje="Frontmatter actualizado",
        backup=copia,
    )


def escribir_json_auditado(
    ruta_relativa: str | Path,
    data: Any,
    *,
    actor: str = "sistema",
    motivo: str = "json",
    backup: bool = True,
) -> ResultadoEscritura:
    """
    Escribe un archivo .json dentro de la bóveda de forma atómica, con lock,
    backup opcional y registro en auditoría. Es la puerta única para JSON de
    la bóveda (por ejemplo, Perfil/*.json).
    """
    config = cargar_config()
    destino = ruta_relativa_segura(ruta_relativa, config.boveda)

    if destino.suffix.lower() != ".json":
        raise ValueError("escribir_json_auditado solo escribe archivos .json")

    contenido = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    anterior = destino.read_text(encoding="utf-8") if destino.exists() else None

    if anterior == contenido:
        return ResultadoEscritura(
            ok=True,
            operacion="json",
            ruta=destino,
            mensaje="Sin cambios",
        )

    with lock_archivo(destino):
        copia = _backup_si_existe(destino) if (backup and anterior is not None) else None
        escribir_texto_atomico(destino, contenido)

    _auditar(
        config,
        "json",
        destino,
        actor,
        motivo,
        {
            "hash": _hash_texto(contenido),
            "backup": str(copia) if copia else None,
        },
    )

    return ResultadoEscritura(
        ok=True,
        operacion="json",
        ruta=destino,
        mensaje="JSON escrito",
        backup=copia,
    )


def mover_nota(
    origen_relativo: str | Path,
    destino_relativo: str | Path,
    *,
    actor: str = "sistema",
    motivo: str = "movimiento",
) -> ResultadoEscritura:
    config = cargar_config()

    origen = ruta_relativa_segura(origen_relativo, config.boveda)
    destino = ruta_relativa_segura(destino_relativo, config.boveda)

    if not origen.exists():
        return ResultadoEscritura(
            ok=False,
            operacion="mover",
            ruta=origen,
            mensaje="El origen no existe",
        )

    if destino.exists():
        return ResultadoEscritura(
            ok=False,
            operacion="mover",
            ruta=destino,
            mensaje="El destino ya existe",
        )

    destino.parent.mkdir(parents=True, exist_ok=True)

    with lock_archivo(origen), lock_archivo(destino):
        shutil.move(str(origen), str(destino))

    _auditar(
        config,
        "mover",
        destino,
        actor,
        motivo,
        {"origen": str(origen.relative_to(config.boveda))},
    )

    return ResultadoEscritura(
        ok=True,
        operacion="mover",
        ruta=destino,
        mensaje="Nota movida",
    )


def eliminar_nota(
    ruta_relativa: str | Path,
    *,
    actor: str = "sistema",
    motivo: str = "eliminacion",
) -> ResultadoEscritura:
    """
    Nunca borra: mueve a Sistema/papelera conservando la ruta original.
    """
    config = cargar_config()
    preparar_carpetas(config)

    origen = ruta_relativa_segura(ruta_relativa, config.boveda)

    if not origen.exists():
        return ResultadoEscritura(
            ok=False,
            operacion="eliminar",
            ruta=origen,
            mensaje="La nota no existe",
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ruta_papelera = config.papelera_path / stamp / origen.relative_to(config.boveda)
    ruta_papelera.parent.mkdir(parents=True, exist_ok=True)

    with lock_archivo(origen):
        shutil.move(str(origen), str(ruta_papelera))

    _auditar(
        config,
        "eliminar",
        origen,
        actor,
        motivo,
        {"papelera": str(ruta_papelera.relative_to(config.boveda))},
    )

    return ResultadoEscritura(
        ok=True,
        operacion="eliminar",
        ruta=origen,
        mensaje="Nota movida a papelera",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Puerta única de escritura.")
    sub = parser.add_subparsers(dest="comando", required=True)

    crear = sub.add_parser("crear")
    crear.add_argument("--titulo", required=True)
    crear.add_argument("--cuerpo", required=True)
    crear.add_argument("--carpeta", default="")
    crear.add_argument("--tags", default="")
    crear.add_argument("--fuente", default="local")
    crear.add_argument("--confianza", type=float, default=0.8)

    editar = sub.add_parser("editar")
    editar.add_argument("--ruta", required=True)
    editar.add_argument("--buscar", required=True)
    editar.add_argument("--reemplazar", required=True)

    mover = sub.add_parser("mover")
    mover.add_argument("--origen", required=True)
    mover.add_argument("--destino", required=True)

    eliminar = sub.add_parser("eliminar")
    eliminar.add_argument("--ruta", required=True)

    args = parser.parse_args()

    if args.comando == "crear":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        resultado = crear_nota(
            args.titulo,
            args.cuerpo,
            carpeta=args.carpeta,
            tags=tags,
            fuente=args.fuente,
            confianza=args.confianza,
        )
    elif args.comando == "editar":
        resultado = editar_nota(args.ruta, args.buscar, args.reemplazar)
    elif args.comando == "mover":
        resultado = mover_nota(args.origen, args.destino)
    else:
        resultado = eliminar_nota(args.ruta)

    print(json.dumps({
        "ok": resultado.ok,
        "operacion": resultado.operacion,
        "ruta": str(resultado.ruta),
        "mensaje": resultado.mensaje,
        "backup": str(resultado.backup) if resultado.backup else None,
    }, ensure_ascii=False, indent=2))

    return 0 if resultado.ok else 1


if __name__ == "__main__":
    sys.exit(main())
