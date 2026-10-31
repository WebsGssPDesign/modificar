"""
util.py — Primitivas seguras para memoria_vectorial.

Reglas:
- Nunca escribir directamente un archivo final.
- Usar archivo temporal en el mismo directorio y os.replace().
- Los locks son cooperativos y por recurso.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator


def ruta_dentro_de(ruta: Path, base: Path) -> bool:
    try:
        ruta.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def ruta_relativa_segura(ruta: str | Path, base: Path) -> Path:
    """
    Convierte una ruta relativa a la bóveda y rechaza escapes como ../.
    """
    base = base.resolve()
    candidata = (base / str(ruta)).resolve()

    if not ruta_dentro_de(candidata, base):
        raise ValueError(f"Ruta fuera de la bóveda: {ruta}")

    return candidata


def escribir_texto_atomico(path: Path, texto: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )

    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()
        raise


def leer_json(path: Path, default: Any = None) -> Any:
    path = Path(path)

    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def escribir_json_atomico(path: Path, data: Any, indent: int = 2) -> None:
    texto = json.dumps(
        data,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
    )
    escribir_texto_atomico(path, texto + "\n")


def append_jsonl(path: Path, registro: dict[str, Any]) -> None:
    """
    Append atómico lógico para JSONL.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    linea = json.dumps(
        registro,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(linea + "\n")
        f.flush()
        os.fsync(f.fileno())


@contextlib.contextmanager
def lock_archivo(
    path: Path,
    timeout: float = 10.0,
    intervalo: float = 0.05,
) -> Iterator[Path]:
    """
    Lock cooperativo basado en creación exclusiva de archivo.

    No es un lock del contenido del archivo: es un lock por recurso.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")

    inicio = time.monotonic()

    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() - inicio >= timeout:
                raise TimeoutError(f"No se pudo obtener lock: {lock_path}")

            time.sleep(intervalo)

    try:
        yield lock_path
    finally:
        with contextlib.suppress(FileNotFoundError):
            lock_path.unlink()


def timestamp_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(texto: str, max_len: int = 80) -> str:
    reemplazos = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ü": "u", "ñ": "n",
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
        "Ü": "U", "Ñ": "N",
    }

    resultado = "".join(reemplazos.get(ch, ch) for ch in texto)
    permitidos = []

    for ch in resultado.lower():
        if ch.isalnum():
            permitidos.append(ch)
        elif ch in {" ", "-", "_", "."}:
            permitidos.append("-")

    slug = "".join(permitidos)

    while "--" in slug:
        slug = slug.replace("--", "-")

    return slug.strip("-")[:max_len] or "sin-titulo"

def proceso_vivo(pid: int) -> bool:
    """Verifica si un proceso local con un PID específico sigue activo."""
    try:
        import psutil  # ← import lazy, solo cuando se usa
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except ImportError:
        # psutil no está instalado: asumimos que el proceso no está vivo
        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False