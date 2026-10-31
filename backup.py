"""
backup.py — Copias de seguridad, verificación real y restauración.

Qué respalda (todo en un .zip con manifiesto SHA-256):
    indice/indice.sqlite   copia consistente (API de backup de SQLite)
    datos/LLM-Memoria/     notas generadas
    datos/Perfil/
    datos/skills/
    datos/Sistema/         (sin backups/, logs/, restauraciones/, *.lock, *.bak)

Dónde:  Sistema/backups/backup-AAAAMMDD-HHMMSS.zip

Retención (reglas.json -> "backup", valores por defecto):
    diarios: 7     un backup por día durante los últimos 7 días
    semanales: 4   uno por semana ISO durante 4 semanas
    mensuales: 6   uno por mes durante 6 meses

Principios:
    - Restaurar NUNCA sobrescribe la bóveda: extrae a una carpeta aparte
      (Sistema/restauraciones/<fecha>/) y verifica hashes. Copiar de vuelta
      es una decisión humana.
    - --verificar hace una restauración real a una carpeta temporal:
      hashes + PRAGMA integrity_check + conteo de chunks.

Uso:
    python backup.py --crear [--dry-run] [--no-podar]
    python backup.py --listar
    python backup.py --verificar [ARCHIVO]
    python backup.py --restaurar ARCHIVO [--destino DIR]
    python backup.py --podar [--dry-run]

Código de salida: 0 correcto, 2 con fallos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from config import cargar_config, preparar_carpetas
from eventos import emitir_evento
from heartbeat import latir
from incidencias import registrar
from metricas import medir
from util import leer_json, timestamp_iso

PATRON = re.compile(r"^backup-(\d{8})-(\d{6})\.zip$")
DEFAULT_RETENCION = {"diarios": 7, "semanales": 4, "mensuales": 6}
EXCLUIR_EN_SISTEMA = {"backups", "logs", "restauraciones"}
EXCLUIR_SUFIJOS = (".lock", ".bak", ".tmp")


class ErrorBackup(RuntimeError):
    pass


# ---------------------------------------------------------------- utilidades


def _sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)

    return h.hexdigest()


def _retencion(config) -> dict[str, int]:
    reglas = leer_json(config.reglas_path, {}) or {}
    cfg = reglas.get("backup", {}) if isinstance(reglas, dict) else {}
    salida = dict(DEFAULT_RETENCION)

    for clave in salida:
        try:
            salida[clave] = max(0, int(cfg.get(clave, salida[clave])))
        except (TypeError, ValueError):
            pass

    return salida


def _fecha_de(nombre: str) -> datetime | None:
    m = PATRON.match(nombre)

    if not m:
        return None

    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def listar_backups(config=None) -> list[Path]:
    config = config or cargar_config()

    if not config.backups_path.exists():
        return []

    return sorted(
        (p for p in config.backups_path.iterdir() if PATRON.match(p.name)),
        key=lambda p: p.name,
    )


def _archivos_a_respaldar(config) -> list[tuple[Path, str]]:
    """Devuelve pares (ruta_real, ruta_en_zip) para los directorios de datos."""
    boveda = config.boveda
    carpetas = [
        config.notas,
        config.perfil,
        boveda / "skills",
        config.sistema,
    ]
    pares: list[tuple[Path, str]] = []

    for carpeta in carpetas:
        if not carpeta.exists():
            continue

        for ruta in sorted(carpeta.rglob("*")):
            if not ruta.is_file():
                continue

            if ruta.name.endswith(EXCLUIR_SUFIJOS):
                continue

            relativa = ruta.relative_to(boveda)

            if carpeta == config.sistema and relativa.parts[1:2] and (
                relativa.parts[1] in EXCLUIR_EN_SISTEMA
            ):
                continue

            pares.append((ruta, "datos/" + relativa.as_posix()))

    return pares


def _copiar_sqlite(origen: Path, destino: Path) -> int:
    """Copia consistente; devuelve el número de chunks copiados."""
    src = sqlite3.connect(origen, timeout=30.0)
    dst = sqlite3.connect(destino)

    try:
        src.backup(dst)
        fila = dst.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'chunks'"
        ).fetchone()
        if fila and fila[0]:
            return int(dst.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        return 0
    finally:
        dst.close()
        src.close()


# -------------------------------------------------------------------- crear


def crear_backup(*, dry_run: bool = False) -> dict[str, Any]:
    config = cargar_config()
    preparar_carpetas(config)
    config.backups_path.mkdir(parents=True, exist_ok=True)

    pares = _archivos_a_respaldar(config)
    estado = {
        "archivos": len(pares),
        "con_indice": config.db_path.exists(),
        "dry_run": dry_run,
    }

    if dry_run:
        estado["destino"] = None
        return estado

    sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destino = config.backups_path / f"backup-{sello}.zip"
    temporal = destino.with_suffix(".zip.tmp")

    manifiesto: dict[str, Any] = {
        "version": 1,
        "creado": timestamp_iso(),
        "boveda": str(config.boveda),
        "archivos": {},
        "chunks": 0,
    }

    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zf:
                if config.db_path.exists():
                    copia = Path(tmp) / "indice.sqlite"
                    manifiesto["chunks"] = _copiar_sqlite(config.db_path, copia)
                    manifiesto["archivos"]["indice/indice.sqlite"] = {
                        "sha256": _sha256(copia),
                        "bytes": copia.stat().st_size,
                    }
                    zf.write(copia, "indice/indice.sqlite")

                for ruta, nombre in pares:
                    try:
                        manifiesto["archivos"][nombre] = {
                            "sha256": _sha256(ruta),
                            "bytes": ruta.stat().st_size,
                        }
                        zf.write(ruta, nombre)
                    except FileNotFoundError:
                        # Un archivo desapareció durante el backup: no es fatal.
                        manifiesto["archivos"].pop(nombre, None)

                zf.writestr(
                    "manifest.json",
                    json.dumps(manifiesto, ensure_ascii=False, indent=2),
                )

            os.replace(temporal, destino)
        finally:
            if temporal.exists():
                temporal.unlink()

    return {
        **estado,
        "destino": str(destino),
        "bytes": destino.stat().st_size,
        "chunks": manifiesto["chunks"],
    }


# ---------------------------------------------------------- verificar / restaurar


def _extraer_seguro(zf: zipfile.ZipFile, destino: Path) -> None:
    base = destino.resolve()

    for miembro in zf.infolist():
        objetivo = (base / miembro.filename).resolve()

        if base != objetivo and base not in objetivo.parents:
            raise ErrorBackup(f"Ruta insegura en el backup: {miembro.filename}")

    zf.extractall(base)


def _verificar_extraido(raiz: Path) -> dict[str, Any]:
    manifiesto_path = raiz / "manifest.json"

    if not manifiesto_path.exists():
        raise ErrorBackup("El backup no contiene manifest.json")

    manifiesto = json.loads(manifiesto_path.read_text(encoding="utf-8"))
    faltantes, corruptos = [], []

    for nombre, info in manifiesto.get("archivos", {}).items():
        path = raiz / nombre

        if not path.exists():
            faltantes.append(nombre)
        elif _sha256(path) != info.get("sha256"):
            corruptos.append(nombre)

    integridad = None
    chunks = None
    sqlite_path = raiz / "indice" / "indice.sqlite"

    if sqlite_path.exists():
        con = sqlite3.connect(sqlite_path)
        try:
            integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
            tiene = con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = 'chunks'"
            ).fetchone()[0]
            chunks = int(con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]) if tiene else 0
        finally:
            con.close()

    ok = (
        not faltantes
        and not corruptos
        and integridad in (None, "ok")
        and (chunks is None or chunks == manifiesto.get("chunks"))
    )

    return {
        "ok": ok,
        "archivos": len(manifiesto.get("archivos", {})),
        "faltantes": faltantes,
        "corruptos": corruptos,
        "integridad_sqlite": integridad,
        "chunks": chunks,
        "chunks_esperados": manifiesto.get("chunks"),
    }


def verificar_backup(archivo: Path | None = None) -> dict[str, Any]:
    config = cargar_config()
    archivo = archivo or (listar_backups(config) or [None])[-1]

    if archivo is None or not Path(archivo).exists():
        raise ErrorBackup("No hay backup que verificar")

    archivo = Path(archivo)

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(archivo) as zf:
            roto = zf.testzip()

            if roto:
                return {"ok": False, "archivo": str(archivo), "zip_corrupto": roto}

            _extraer_seguro(zf, Path(tmp))

        resultado = _verificar_extraido(Path(tmp))

    return {"archivo": str(archivo), **resultado}


def restaurar_backup(archivo: Path, destino: Path | None = None) -> dict[str, Any]:
    config = cargar_config()
    archivo = Path(archivo)

    if not archivo.exists():
        raise ErrorBackup(f"No existe: {archivo}")

    if destino is None:
        sello = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destino = config.sistema / "restauraciones" / sello

    destino = Path(destino)

    if destino.exists() and any(destino.iterdir()):
        raise ErrorBackup(f"El destino no está vacío: {destino}")

    destino.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archivo) as zf:
        _extraer_seguro(zf, destino)

    resultado = _verificar_extraido(destino)

    return {"archivo": str(archivo), "destino": str(destino), **resultado}


# --------------------------------------------------------------------- podar


def calcular_poda(
    nombres: list[str], retencion: dict[str, int], hoy: date | None = None
) -> tuple[list[str], list[str]]:
    """Devuelve (conservar, eliminar). Función pura, fácil de probar."""
    hoy = hoy or date.today()
    fechados = sorted(
        ((n, _fecha_de(n)) for n in nombres if _fecha_de(n)),
        key=lambda par: par[1],  # type: ignore[arg-type,return-value]
        reverse=True,
    )
    conservar: set[str] = set()
    dias: set[date] = set()
    semanas: set[tuple[int, int]] = set()
    meses: set[tuple[int, int]] = set()

    for nombre, fecha in fechados:  # del más nuevo al más viejo
        d = fecha.date()  # type: ignore[union-attr]
        edad = (hoy - d).days
        iso = d.isocalendar()
        semana = (iso[0], iso[1])
        mes = (d.year, d.month)

        if edad < retencion["diarios"] and d not in dias:
            dias.add(d)
            conservar.add(nombre)

        if edad < retencion["semanales"] * 7 and semana not in semanas:
            semanas.add(semana)
            conservar.add(nombre)

        if edad < retencion["mensuales"] * 31 and mes not in meses:
            meses.add(mes)
            conservar.add(nombre)

    if fechados:  # nunca dejar al sistema sin ningún backup
        conservar.add(fechados[0][0])

    eliminar = [n for n, _ in fechados if n not in conservar]
    return sorted(conservar), sorted(eliminar)


def podar(*, dry_run: bool = False) -> dict[str, Any]:
    config = cargar_config()
    nombres = [p.name for p in listar_backups(config)]
    conservar, eliminar = calcular_poda(nombres, _retencion(config))

    if not dry_run:
        for nombre in eliminar:
            (config.backups_path / nombre).unlink(missing_ok=True)

    return {"conservados": len(conservar), "eliminados": eliminar, "dry_run": dry_run}


# ----------------------------------------------------------------------- CLI


def main() -> int:
    parser = argparse.ArgumentParser(description="Backups de memoria_vectorial.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--crear", action="store_true")
    grupo.add_argument("--listar", action="store_true")
    grupo.add_argument("--verificar", nargs="?", const="__ultimo__", metavar="ARCHIVO")
    grupo.add_argument("--restaurar", metavar="ARCHIVO")
    grupo.add_argument("--podar", action="store_true")
    parser.add_argument("--destino", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-podar", action="store_true")
    args = parser.parse_args()

    config = cargar_config()
    latir("backup")

    try:
        if args.listar:
            for p in listar_backups(config):
                print(f"{p.name}  {p.stat().st_size / 1024:.0f} KiB")
            return 0

        if args.crear:
            with medir("backup", "crear"):
                resultado = crear_backup(dry_run=args.dry_run)

            if not args.dry_run and not args.no_podar:
                resultado["poda"] = podar()

            if not args.dry_run:
                verif = verificar_backup(Path(resultado["destino"]))
                resultado["verificacion"] = verif

                if not verif["ok"]:
                    registrar(
                        "backup",
                        "El backup recién creado no pasó la verificación",
                        gravedad="alta",
                        detalle=verif,
                    )
                    emitir_evento("backup.error", gravedad="alta", payload=verif)
                    print(json.dumps(resultado, ensure_ascii=False, indent=2))
                    return 2

                emitir_evento("backup.ok", payload={"destino": resultado["destino"]})

            print(json.dumps(resultado, ensure_ascii=False, indent=2))
            return 0

        if args.verificar:
            archivo = None if args.verificar == "__ultimo__" else Path(args.verificar)
            resultado = verificar_backup(archivo)
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
            return 0 if resultado["ok"] else 2

        if args.restaurar:
            destino = Path(args.destino) if args.destino else None
            resultado = restaurar_backup(Path(args.restaurar), destino)
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
            print(
                "\nRestaurado en una carpeta aparte. Revisa el contenido y copia a mano "
                "lo que necesites a la bóveda: este script nunca sobrescribe."
            )
            return 0 if resultado["ok"] else 2

        if args.podar:
            print(json.dumps(podar(dry_run=args.dry_run), ensure_ascii=False, indent=2))
            return 0

    except (ErrorBackup, OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
        registrar("backup", f"Fallo de backup: {exc}", gravedad="alta")
        emitir_evento("backup.error", gravedad="alta", payload={"error": str(exc)})
        print(f"Error: {exc}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
