"""
estado.py — Diagnóstico único del sistema.

Responde en un solo vistazo: ¿está vivo?, ¿qué hay indexado?, ¿qué falla?,
¿qué se aprendió por última vez? No necesita LM Studio ni red.

Modos:
    python estado.py              resumen legible
    python estado.py --json       salida estructurada (n8n, scripts)
    python estado.py --tablero    además publica LLM-Memoria/estado.md (vía escritor)
    python estado.py --abrir      publica y abre estado.md con la app del sistema

Código de salida: 0 normal, 1 atención, 2 crítico.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any

from config import cargar_config
from heartbeat import segundos_sin_latir
from incidencias import abiertas
from memoria import estado_indice
from util import leer_json, timestamp_iso

HEARTBEAT_MAX_SEGUNDOS = 900
LINEAS_EVENTOS = 3000
GRAVEDADES_MALAS = {"alta", "critica", "critico", "error"}
EVENTOS_APRENDIZAJE = (
    "aprender.ciclo.ok",
    "aprender_web.publicado",
    "crear_skills.ciclo.ok",
)


def _ultimas_lineas_json(path: Path, limite: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    cola: deque[str] = deque(maxlen=limite)

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for linea in f:
            cola.append(linea)

    salida = []

    for linea in cola:
        try:
            dato = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(dato, dict):
            salida.append(dato)

    return salida


def _heartbeat(config) -> dict[str, Any]:
    segundos = segundos_sin_latir()
    datos = leer_json(config.heartbeat_path, {}) or {}

    if segundos is None:
        estado = "sin_latidos"
    elif segundos > HEARTBEAT_MAX_SEGUNDOS:
        estado = "silencioso"
    else:
        estado = "ok"

    return {
        "estado": estado,
        "segundos": None if segundos is None else round(segundos, 1),
        "paso": datos.get("paso"),
        "ultimo": datos.get("iso"),
    }


def _incidencias() -> dict[str, Any]:
    lista = abiertas()
    por_gravedad: dict[str, int] = {}

    for item in lista:
        gravedad = str(item.get("gravedad", "media"))
        por_gravedad[gravedad] = por_gravedad.get(gravedad, 0) + 1

    recientes = sorted(lista, key=lambda i: i.get("ts", ""), reverse=True)[:5]

    return {
        "abiertas": len(lista),
        "por_gravedad": por_gravedad,
        "recientes": [
            {
                "id": i.get("id"),
                "modulo": i.get("modulo"),
                "gravedad": i.get("gravedad"),
                "estado": i.get("estado"),
                "mensaje": str(i.get("mensaje", ""))[:160],
            }
            for i in recientes
        ],
    }


def _aprendizaje(eventos: list[dict[str, Any]]) -> dict[str, Any]:
    for evento in reversed(eventos):
        if evento.get("tipo") in EVENTOS_APRENDIZAJE:
            return {
                "tipo": evento.get("tipo"),
                "ts": evento.get("ts"),
                "payload": evento.get("payload", {}),
            }

    return {"tipo": None, "ts": None, "payload": {}}


def _errores(config, eventos: list[dict[str, Any]], limite: int = 5) -> dict[str, Any]:
    eventos_malos = [
        {
            "ts": e.get("ts"),
            "tipo": e.get("tipo"),
            "gravedad": e.get("gravedad"),
            "detalle": str(e.get("payload", {}).get("error", ""))[:160],
        }
        for e in eventos
        if str(e.get("gravedad", "info")).lower() in GRAVEDADES_MALAS
        or str(e.get("tipo", "")).endswith(".error")
    ][-limite:]

    metricas = [
        {
            "ts": m.get("ts"),
            "modulo": m.get("modulo"),
            "entrada": m.get("entrada"),
            "error": str(m.get("error", ""))[:160],
        }
        for m in _ultimas_lineas_json(config.metricas_path, LINEAS_EVENTOS)
        if m.get("resultado") == "error"
    ][-limite:]

    return {"eventos": eventos_malos, "metricas": metricas}


def _veredicto(datos: dict[str, Any]) -> str:
    gravedades = datos["incidencias"]["por_gravedad"]

    if datos["heartbeat"]["estado"] == "silencioso":
        return "critico"
    if gravedades.get("critica") or gravedades.get("critico"):
        return "critico"
    if not datos["indice"].get("existe"):
        return "atencion"
    if datos["indice"]["chunks"] > datos["indice"]["con_embedding"]:
        return "atencion"
    if datos["incidencias"]["abiertas"] or datos["errores"]["eventos"]:
        return "atencion"
    if datos["heartbeat"]["estado"] == "sin_latidos":
        return "atencion"

    return "ok"


def recolectar() -> dict[str, Any]:
    config = cargar_config()
    eventos = _ultimas_lineas_json(config.eventos_path, LINEAS_EVENTOS)

    datos = {
        "generado": timestamp_iso(),
        "boveda": str(config.boveda),
        "heartbeat": _heartbeat(config),
        "indice": estado_indice(),
        "incidencias": _incidencias(),
        "ultimo_aprendizaje": _aprendizaje(eventos),
        "errores": _errores(config, eventos),
    }
    datos["veredicto"] = _veredicto(datos)

    return datos


def render_texto(d: dict[str, Any]) -> str:
    hb = d["heartbeat"]
    ix = d["indice"]
    inc = d["incidencias"]
    ap = d["ultimo_aprendizaje"]
    lineas = [
        f"Estado general : {d['veredicto'].upper()}",
        f"Generado       : {d['generado']}",
        f"Bóveda         : {d['boveda']}",
        "",
        f"Heartbeat      : {hb['estado']} (paso={hb['paso']}, hace {hb['segundos']} s)",
        f"Índice         : {ix.get('archivos', 0)} archivos, {ix.get('chunks', 0)} chunks, "
        f"{ix.get('con_embedding', 0)} con embedding",
        f"Incidencias    : {inc['abiertas']} abiertas {inc['por_gravedad'] or ''}",
        f"Últ. aprendizaje: {ap['tipo'] or 'ninguno'} {ap['ts'] or ''}",
    ]

    for i in inc["recientes"]:
        lineas.append(f"  - [{i['gravedad']}] {i['modulo']}: {i['mensaje']}")

    if d["errores"]["eventos"] or d["errores"]["metricas"]:
        lineas += ["", "Errores recientes:"]
        for e in d["errores"]["eventos"]:
            lineas.append(f"  - evento {e['tipo']} ({e['ts']}) {e['detalle']}")
        for m in d["errores"]["metricas"]:
            lineas.append(f"  - métrica {m['modulo']}/{m['entrada']} ({m['ts']}) {m['error']}")

    return "\n".join(lineas)


def render_markdown(d: dict[str, Any]) -> str:
    hb = d["heartbeat"]
    ix = d["indice"]
    inc = d["incidencias"]
    ap = d["ultimo_aprendizaje"]
    lineas = [
        f"# Estado del sistema: {d['veredicto'].upper()}",
        "",
        f"Generado: {d['generado']}",
        "",
        "| Componente | Estado |",
        "|---|---|",
        f"| Heartbeat | {hb['estado']} (paso `{hb['paso']}`, hace {hb['segundos']} s) |",
        f"| Índice | {ix.get('archivos', 0)} archivos / {ix.get('chunks', 0)} chunks / "
        f"{ix.get('con_embedding', 0)} con embedding |",
        f"| Incidencias abiertas | {inc['abiertas']} |",
        f"| Último aprendizaje | {ap['tipo'] or 'ninguno'} {ap['ts'] or ''} |",
        "",
        "## Incidencias recientes",
        "",
    ]

    if inc["recientes"]:
        for i in inc["recientes"]:
            lineas.append(f"- **{i['gravedad']}** `{i['modulo']}`: {i['mensaje']}")
    else:
        lineas.append("Ninguna.")

    lineas += ["", "## Errores recientes", ""]
    errores = d["errores"]

    if errores["eventos"] or errores["metricas"]:
        for e in errores["eventos"]:
            lineas.append(f"- evento `{e['tipo']}` ({e['ts']}) {e['detalle']}")
        for m in errores["metricas"]:
            lineas.append(f"- métrica `{m['modulo']}/{m['entrada']}` ({m['ts']}) {m['error']}")
    else:
        lineas.append("Ninguno.")

    return "\n".join(lineas) + "\n"


def publicar_tablero(datos: dict[str, Any]) -> Path:
    from escritor import crear_nota

    config = cargar_config()
    resultado = crear_nota(
        "Estado",
        render_markdown(datos),
        carpeta=str(config.notas.relative_to(config.boveda).as_posix()),
        tags=["sistema", "estado"],
        fuente="estado",
        confianza=1.0,
        actor="estado",
        motivo="diagnostico",
        sobrescribir=True,
    )

    if not resultado.ok:
        raise RuntimeError(resultado.mensaje)

    return resultado.ruta


def abrir(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError as exc:
        print(f"No se pudo abrir {path}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico único.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--tablero", action="store_true")
    parser.add_argument("--abrir", action="store_true")
    args = parser.parse_args()

    datos = recolectar()
    ruta_tablero: Path | None = None

    if args.tablero or args.abrir:
        ruta_tablero = publicar_tablero(datos)

    if args.json:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    else:
        print(render_texto(datos))
        if ruta_tablero:
            print(f"\nTablero: {ruta_tablero}")

    if args.abrir and ruta_tablero:
        abrir(ruta_tablero)

    return {"ok": 0, "atencion": 1, "critico": 2}[datos["veredicto"]]


if __name__ == "__main__":
    sys.exit(main())
