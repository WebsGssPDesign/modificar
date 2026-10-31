"""
guardian.py — Vigilancia del sistema en modo observación.

Comprobaciones:
1. Configuración y rutas.
2. Heartbeat del pipeline.
3. Integridad básica de SQLite.
4. Incidencias abiertas o aisladas.
5. Límites de aprendizaje web.
6. Notas generadas sin fuente o sin confianza.
7. Chunks sin embedding.
8. Archivos indexados que ya no existen.
9. Propuestas de reparación.

Regla:
- Por defecto solo observa.
- No borra, no edita notas y no reindexa sin confirmación explícita.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import cargar_config, preparar_carpetas, validar_config
from eventos import emitir_evento
from heartbeat import latir, segundos_sin_latir
from incidencias import abiertas, registrar
from memoria import conectar, inicializar_db
from metricas import medir
from util import (
    leer_json,
    ruta_relativa_segura,
    timestamp_iso,
    escribir_texto_atomico,
)

HEARTBEAT_MAX_SEGUNDOS = 900
WEB_HORA_ALERTA = 0.8
WEB_DIA_ALERTA = 0.8
MIN_CONFIANZA_NOTA = 0.55


@dataclass
class Hallazgo:
    codigo: str
    gravedad: str  # info | aviso | critico
    mensaje: str
    detalle: dict[str, Any] = field(default_factory=dict)
    reparacion_propuesta: str = ""


@dataclass
class Informe:
    generado: str
    modo: str
    ok: bool
    hallazgos: list[Hallazgo]
    estadisticas: dict[str, Any]

    @property
    def criticos(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad == "critico"]

    @property
    def avisos(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad == "aviso"]


def _check_configuracion() -> list[Hallazgo]:
    config = cargar_config()
    errores = validar_config(config)

    return [
        Hallazgo(
            codigo="config_invalida",
            gravedad="critico",
            mensaje=error,
        )
        for error in errores
    ]


def _check_heartbeat() -> list[Hallazgo]:
    segundos = segundos_sin_latir()

    if segundos is None:
        return [
            Hallazgo(
                codigo="heartbeat_ausente",
                gravedad="aviso",
                mensaje="No hay heartbeat registrado.",
                reparacion_propuesta=(
                    "Ejecutar el pipeline o crear un heartbeat inicial."
                ),
            )
        ]

    if segundos > HEARTBEAT_MAX_SEGUNDOS:
        return [
            Hallazgo(
                codigo="heartbeat_silencioso",
                gravedad="aviso",
                mensaje=(
                    f"El pipeline lleva {segundos:.0f}s sin latir "
                    f"(límite: {HEARTBEAT_MAX_SEGUNDOS}s)."
                ),
                detalle={"segundos": segundos},
                reparacion_propuesta=(
                    "Comprobar si iniciar.ps1, indexer o aprender siguen activos."
                ),
            )
        ]

    return []


def _check_sqlite() -> list[Hallazgo]:
    config = cargar_config()
    hallazgos: list[Hallazgo] = []

    if not config.db_path.exists():
        return [
            Hallazgo(
                codigo="sqlite_ausente",
                gravedad="aviso",
                mensaje="El índice SQLite aún no existe.",
                reparacion_propuesta="Ejecutar: python indexer.py --index",
            )
        ]

    connection = conectar(config.db_path)

    try:
        filas = connection.execute("PRAGMA quick_check").fetchall()
        resultado = [fila[0] for fila in filas]

        if resultado != ["ok"]:
            hallazgos.append(
                Hallazgo(
                    codigo="sqlite_integridad",
                    gravedad="critico",
                    mensaje="SQLite reporta problemas de integridad.",
                    detalle={"resultado": resultado[:10]},
                    reparacion_propuesta=(
                        "Hacer backup, detener procesos y reconstruir el índice."
                    ),
                )
            )

        chunks_sin_embedding = connection.execute(
            "SELECT COUNT(*) AS total FROM chunks WHERE embedding IS NULL"
        ).fetchone()["total"]

        if chunks_sin_embedding:
            hallazgos.append(
                Hallazgo(
                    codigo="chunks_sin_embedding",
                    gravedad="aviso",
                    mensaje=f"{chunks_sin_embedding} chunks no tienen embedding.",
                    detalle={"chunks": int(chunks_sin_embedding)},
                    reparacion_propuesta=(
                        "Ejecutar: python indexer.py --reindex"
                    ),
                )
            )

        archivos_huerfanos = connection.execute(
            """
            SELECT ruta
            FROM archivos
            """
        ).fetchall()

        inexistentes = []

        for fila in archivos_huerfanos:
            ruta = config.boveda / fila["ruta"]

            if not ruta.exists():
                inexistentes.append(fila["ruta"])

        if inexistentes:
            hallazgos.append(
                Hallazgo(
                    codigo="archivos_indexados_inexistentes",
                    gravedad="aviso",
                    mensaje=f"{len(inexistentes)} archivos indexados ya no existen.",
                    detalle={"ejemplos": inexistentes[:10]},
                    reparacion_propuesta=(
                        "Ejecutar una indexación incremental para limpiar el índice."
                    ),
                )
            )

    except sqlite3.Error as exc:
        hallazgos.append(
            Hallazgo(
                codigo="sqlite_error",
                gravedad="critico",
                mensaje=f"Error al consultar SQLite: {exc}",
            )
        )
    finally:
        connection.close()

    return hallazgos


def _check_incidencias() -> list[Hallazgo]:
    incidencias = abiertas()

    criticas = [
        i for i in incidencias if i.get("gravedad") == "alta"
    ]

    hallazgos: list[Hallazgo] = []

    if criticas:
        hallazgos.append(
            Hallazgo(
                codigo="incidencias_criticas",
                gravedad="critico",
                mensaje=f"Hay {len(criticas)} incidencias de gravedad alta.",
                detalle={
                    "ejemplos": [
                        {
                            "id": i["id"],
                            "modulo": i.get("modulo"),
                            "mensaje": i.get("mensaje"),
                        }
                        for i in criticas[:5]
                    ]
                },
                reparacion_propuesta=(
                    "Revisar incidencias, corregir la causa y marcar como resueltas."
                ),
            )
        )

    if len(incidencias) > len(criticas):
        hallazgos.append(
            Hallazgo(
                codigo="incidencias_abiertas",
                gravedad="aviso",
                mensaje=f"Hay {len(incidencias) - len(criticas)} incidencias no críticas.",
            )
        )

    return hallazgos


def _check_web(config) -> list[Hallazgo]:
    estado_path = config.memoria_dir / "web_estado.json"
    estado = leer_json(estado_path, {"hora": [], "dia": []})

    ahora = time.time()
    hora = [ts for ts in estado.get("hora", []) if ahora - ts < 3600]
    dia = [ts for ts in estado.get("dia", []) if ahora - ts < 86400]

    max_hora = int(config.web_max_por_hora.valor)
    max_dia = int(config.web_max_por_dia.valor)

    hallazgos: list[Hallazgo] = []

    if len(hora) >= max_hora * WEB_HORA_ALERTA:
        hallazgos.append(
            Hallazgo(
                codigo="web_limite_hora",
                gravedad="aviso",
                mensaje=(
                    f"Uso web alto: {len(hora)}/{max_hora} peticiones en la última hora."
                ),
                reparacion_propuesta="Reducir frecuencia o ampliar el intervalo entre ciclos.",
            )
        )

    if len(dia) >= max_dia * WEB_DIA_ALERTA:
        hallazgos.append(
            Hallazgo(
                codigo="web_limite_dia",
                gravedad="aviso",
                mensaje=(
                    f"Uso web alto: {len(dia)}/{max_dia} peticiones en las últimas 24h."
                ),
                reparacion_propuesta="Pausar aprendizaje web hasta mañana.",
            )
        )

    return hallazgos


def _check_notas_generadas(config) -> list[Hallazgo]:
    carpeta = config.boveda / "LLM-Memoria" / "Hechos"
    hallazgos: list[Hallazgo] = []

    if not carpeta.exists():
        return hallazgos

    sin_fuente: list[str] = []
    baja_confianza: list[str] = []

    for ruta in carpeta.rglob("*.md"):
        try:
            texto = ruta.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        relativa = ruta.relative_to(config.boveda).as_posix()

        if "## Fuente" not in texto and "fuente:" not in texto:
            sin_fuente.append(relativa)

        import re

        match = re.search(r"^confianza:\s*([0-9.]+)", texto, re.MULTILINE)

        if match:
            try:
                confianza = float(match.group(1))

                if confianza < MIN_CONFIANZA_NOTA:
                    baja_confianza.append(relativa)
            except ValueError:
                baja_confianza.append(relativa)

    if sin_fuente:
        hallazgos.append(
            Hallazgo(
                codigo="notas_sin_fuente",
                gravedad="aviso",
                mensaje=f"{len(sin_fuente)} notas generadas no declaran fuente.",
                detalle={"ejemplos": sin_fuente[:10]},
                reparacion_propuesta=(
                    "Revisar el módulo que las creó; no editar notas automáticamente."
                ),
            )
        )

    if baja_confianza:
        hallazgos.append(
            Hallazgo(
                codigo="notas_baja_confianza",
                gravedad="aviso",
                mensaje=f"{len(baja_confianza)} notas tienen confianza baja.",
                detalle={"ejemplos": baja_confianza[:10]},
                reparacion_propuesta=(
                    "Enviar a revisión humana; no promoverlas a conocimiento consolidado."
                ),
            )
        )

    return hallazgos


def _check_espacio(config) -> list[Hallazgo]:
    import shutil

    total, usado, libre = shutil.disk_usage(config.boveda)
    porcentaje_libre = libre / total

    if porcentaje_libre < 0.10:
        return [
            Hallazgo(
                codigo="disco_poco_espacio",
                gravedad="critico",
                mensaje=f"Queda solo {porcentaje_libre:.1%} de espacio libre.",
                reparacion_propuesta="Liberar espacio antes de seguir indexando.",
            )
        ]

    return []


def generar_propuestas(config, informe: Informe) -> str:
    if not informe.avisos and not informe.criticos:
        return "No hay propuestas pendientes."

    lineas = ["# Propuestas del guardian", ""]

    for hallazgo in informe.criticos + informe.avisos:
        lineas.extend(
            [
                f"## [{hallazgo.gravedad.upper()}] {hallazgo.codigo}",
                "",
                hallazgo.mensaje,
                "",
            ]
        )

        if hallazgo.detalle:
            lineas.append(
                "```json\n"
                + json.dumps(hallazgo.detalle, ensure_ascii=False, indent=2)
                + "\n```"
            )
            lineas.append("")

        if hallazgo.reparacion_propuesta:
            lineas.extend(
                [
                    "**Reparación propuesta:**",
                    "",
                    hallazgo.reparacion_propuesta,
                    "",
                ]
            )

    return "\n".join(lineas)


def vigilar(*, aplicar: bool = False) -> Informe:
    config = cargar_config()
    preparar_carpetas(config)

    # El heartbeat se evalúa ANTES de que el propio guardian lata; si no, el
    # latido de esta ejecución taparía siempre un pipeline caído.
    hallazgos_heartbeat = _check_heartbeat()

    latir("guardian", detalle={"modo": "reparar" if aplicar else "observacion"})

    hallazgos: list[Hallazgo] = []

    hallazgos.extend(_check_configuracion())
    hallazgos.extend(hallazgos_heartbeat)
    hallazgos.extend(_check_sqlite())
    hallazgos.extend(_check_incidencias())
    hallazgos.extend(_check_web(config))
    hallazgos.extend(_check_notas_generadas(config))
    hallazgos.extend(_check_espacio(config))

    informe = Informe(
        generado=timestamp_iso(),
        modo="reparar" if aplicar else "observacion",
        ok=not any(h.gravedad == "critico" for h in hallazgos),
        hallazgos=hallazgos,
        estadisticas=estado_resumen(config),
    )

    with medir("guardian", "vigilancia") as metrica:
        metrica["salida"] = {
            "ok": informe.ok,
            "criticos": len(informe.criticos),
            "avisos": len(informe.avisos),
        }

    # Propuestas siempre; reparación automática no en esta fase.
    propuestas = generar_propuestas(config, informe)
    escribir_texto_atomico(
        config.sistema / "propuestas.md",
        propuestas,
    )

    if hallazgos:
        emitir_evento(
            "guardian.hallazgos",
            gravedad="critico" if informe.criticos else "aviso",
            payload={
                "criticos": len(informe.criticos),
                "avisos": len(informe.avisos),
                "codigos": [h.codigo for h in hallazgos],
            },
        )

        for hallazgo in informe.criticos:
            registrar(
                "guardian",
                hallazgo.mensaje,
                gravedad="alta",
                detalle=hallazgo.detalle,
            )

    return informe


def estado_resumen(config) -> dict[str, Any]:
    if not config.db_path.exists():
        return {
            "archivos": 0,
            "chunks": 0,
            "con_embedding": 0,
        }

    connection = conectar(config.db_path)
    inicializar_db(connection)

    try:
        archivos = connection.execute(
            "SELECT COUNT(*) AS total FROM archivos"
        ).fetchone()["total"]

        chunks = connection.execute(
            "SELECT COUNT(*) AS total FROM chunks"
        ).fetchone()["total"]

        con_embedding = connection.execute(
            "SELECT COUNT(*) AS total FROM chunks WHERE embedding IS NOT NULL"
        ).fetchone()["total"]

        return {
            "archivos": int(archivos),
            "chunks": int(chunks),
            "con_embedding": int(con_embedding),
        }
    finally:
        connection.close()


def _imprimir_informe(informe: Informe) -> None:
    print(f"Guardian: {informe.modo}")
    print(f"Generado: {informe.generado}")
    print(f"Estado general: {'OK' if informe.ok else 'CON PROBLEMAS'}")
    print(f"Críticos: {len(informe.criticos)} | Avisos: {len(informe.avisos)}")

    for hallazgo in informe.criticos + informe.avisos:
        print(f"\n[{hallazgo.gravedad.upper()}] {hallazgo.codigo}")
        print(f"  {hallazgo.mensaje}")

        if hallazgo.reparacion_propuesta:
            print(f"  Propuesta: {hallazgo.reparacion_propuesta}")

    print("\nPropuestas guardadas en: Sistema/propuestas.md")


def main() -> int:
    parser = argparse.ArgumentParser(description="Vigila la salud de memoria_vectorial.")
    parser.add_argument("--una-vez", action="store_true")
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")

    args = parser.parse_args()

    config = cargar_config()
    preparar_carpetas(config)

    if args.check:
        print(f"Bóveda: {config.boveda}")
        print(f"Modo guardian: {config.guardian_modo.valor}")
        print(f"Reparaciones permitidas: {config.guardian_reparaciones}")
        return 0

    if args.aplicar and config.guardian_modo.valor != "reparar":
        print(
            "guardian.modo es 'observacion'; "
            "no se aplicarán reparaciones aunque se use --aplicar."
        )

    informe = vigilar(aplicar=args.aplicar)

    if args.json:
        print(
            json.dumps(
                {
                    "generado": informe.generado,
                    "modo": informe.modo,
                    "ok": informe.ok,
                    "criticos": len(informe.criticos),
                    "avisos": len(informe.avisos),
                    "hallazgos": [
                        {
                            "codigo": h.codigo,
                            "gravedad": h.gravedad,
                            "mensaje": h.mensaje,
                            "detalle": h.detalle,
                            "reparacion_propuesta": h.reparacion_propuesta,
                        }
                        for h in informe.hallazgos
                    ],
                    "estadisticas": informe.estadisticas,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _imprimir_informe(informe)

    return 0 if informe.ok else 2


if __name__ == "__main__":
    sys.exit(main())
