"""
n8n_puente.py — Puente de eventos hacia n8n (webhook), solo biblioteca estándar.

Lee Sistema/eventos.jsonl de forma incremental (offset en .memoria/n8n_estado.json)
y envía a un webhook de n8n únicamente lo que merece atención:

    - eventos con gravedad alta/crítica o tipo terminado en ".error"
    - escrituras hechas por el agente MCP (mcp.anotar_memoria, mcp.editar_nota,
      mcp.mover_nota, mcp.eliminar_nota)
    - opcionalmente (--huecos) un resumen de huecos de conocimiento relevantes

Configuración (variables de entorno):
    N8N_WEBHOOK_URL     URL del webhook de n8n (obligatoria salvo --dry-run)
    N8N_WEBHOOK_TOKEN   si existe, se envía en la cabecera X-Memoria-Token

Garantías:
    - Si el envío falla, el offset NO avanza: el siguiente ciclo reintenta.
    - El contenido de notas nunca se envía; solo metadatos del evento.
    - --dry-run muestra lo que se enviaría sin enviar ni avanzar el offset.

Ejemplo de flujo en n8n: Webhook -> IF gravedad == alta -> mensaje de WhatsApp.

Uso:
    python n8n_puente.py --una-vez [--dry-run] [--huecos]
    python n8n_puente.py --watch --intervalo 60
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from config import cargar_config, preparar_carpetas
from heartbeat import latir
from incidencias import registrar
from util import escribir_json_atomico, leer_json, timestamp_iso

GRAVEDADES = {"alta", "critica", "critico", "error"}
TIPOS_MCP_ESCRITURA = {
    "mcp.anotar_memoria",
    "mcp.editar_nota",
    "mcp.mover_nota",
    "mcp.eliminar_nota",
}
MAX_EVENTOS_POR_ENVIO = 50
MAX_HUECOS = 5


def es_relevante(evento: dict[str, Any]) -> bool:
    tipo = str(evento.get("tipo", ""))
    gravedad = str(evento.get("gravedad", "info")).lower()

    return (
        gravedad in GRAVEDADES
        or tipo.endswith(".error")
        or tipo in TIPOS_MCP_ESCRITURA
    )


def _resumir(evento: dict[str, Any]) -> dict[str, Any]:
    payload = evento.get("payload", {}) or {}
    seguro = {
        k: v
        for k, v in payload.items()
        if k in {"ok", "ruta", "mensaje", "error", "incidencia", "destino", "origen"}
    }

    return {
        "id": evento.get("id"),
        "ts": evento.get("ts"),
        "tipo": evento.get("tipo"),
        "actor": evento.get("actor"),
        "gravedad": evento.get("gravedad", "info"),
        "payload": seguro,
    }


def leer_nuevos(config, offset: int) -> tuple[list[tuple[dict[str, Any], int]], int]:
    """
    Devuelve ([(evento_relevante, offset_tras_su_linea), ...], offset_final).
    Solo consume líneas completas, para no leer un evento a medio escribir.
    """
    path = config.eventos_path

    if not path.exists():
        return [], 0

    if offset > path.stat().st_size:  # archivo rotado o recreado
        offset = 0

    with path.open("rb") as f:
        f.seek(offset)
        datos = f.read()

    ultimo_salto = datos.rfind(b"\n")

    if ultimo_salto == -1:
        return [], offset

    eventos: list[tuple[dict[str, Any], int]] = []
    posicion = offset

    for linea in datos[: ultimo_salto + 1].splitlines(keepends=True):
        posicion += len(linea)

        try:
            evento = json.loads(linea.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue

        if isinstance(evento, dict) and es_relevante(evento):
            eventos.append((_resumir(evento), posicion))

    return eventos, posicion


def huecos_relevantes() -> list[dict[str, Any]]:
    from analisis import analizar

    return [
        {k: v for k, v in h.items() if k != "texto"}
        for h in analizar().huecos[:MAX_HUECOS]
    ]


def enviar(url: str, cuerpo: dict[str, Any], *, timeout: float = 10.0) -> None:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("N8N_WEBHOOK_URL debe empezar por http:// o https://")

    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("N8N_WEBHOOK_TOKEN")

    if token:
        cabeceras["X-Memoria-Token"] = token

    peticion = urllib.request.Request(
        url,
        data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
        headers=cabeceras,
        method="POST",
    )

    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:  # noqa: S310
        if respuesta.status >= 300:
            raise urllib.error.HTTPError(url, respuesta.status, "respuesta no exitosa", {}, None)  # type: ignore[arg-type]


def ciclo(*, dry_run: bool = False, con_huecos: bool = False) -> dict[str, Any]:
    config = cargar_config()
    preparar_carpetas(config)
    estado_path = config.memoria_dir / "n8n_estado.json"
    estado = leer_json(estado_path, {}) or {}
    offset = int(estado.get("offset", 0))

    pares, offset_final = leer_nuevos(config, offset)
    lote_pares = pares[:MAX_EVENTOS_POR_ENVIO]
    lote = [evento for evento, _ in lote_pares]
    parcial = len(pares) > MAX_EVENTOS_POR_ENVIO
    nuevo_offset = lote_pares[-1][1] if parcial else offset_final

    cuerpo: dict[str, Any] = {
        "fuente": "memoria_vectorial",
        "enviado": timestamp_iso(),
        "eventos": lote,
    }

    if con_huecos:
        cuerpo["huecos"] = huecos_relevantes()

    resultado = {
        "eventos": len(lote),
        "huecos": len(cuerpo.get("huecos", [])),
        "dry_run": dry_run,
        "enviado": False,
        "offset": offset,
    }

    if not lote and not cuerpo.get("huecos"):
        if not dry_run:
            escribir_json_atomico(estado_path, {"offset": nuevo_offset})
        resultado["offset"] = nuevo_offset
        return resultado

    if dry_run:
        resultado["cuerpo"] = cuerpo
        return resultado

    url = os.environ.get("N8N_WEBHOOK_URL", "").strip()

    if not url:
        raise ValueError("Falta N8N_WEBHOOK_URL")

    enviar(url, cuerpo)

    escribir_json_atomico(estado_path, {"offset": nuevo_offset})
    resultado["offset"] = nuevo_offset
    resultado["parcial"] = parcial

    resultado["enviado"] = True
    return resultado


def vigilar(intervalo: float, *, con_huecos: bool, max_ciclos: int | None = None) -> int:
    config = cargar_config()
    stop = config.memoria_dir / "STOP"
    ciclos = 0

    while not stop.exists():
        latir("n8n_puente")

        try:
            ciclo(con_huecos=con_huecos and ciclos == 0)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            registrar("n8n_puente", f"Envío a n8n fallido: {exc}", gravedad="media")

        ciclos += 1

        if max_ciclos is not None and ciclos >= max_ciclos:
            break

        time.sleep(intervalo)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Puente de eventos hacia n8n.")
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--una-vez", action="store_true")
    modo.add_argument("--watch", action="store_true")
    parser.add_argument("--intervalo", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--huecos", action="store_true")
    args = parser.parse_args()

    if args.watch:
        return vigilar(args.intervalo, con_huecos=args.huecos)

    try:
        resultado = ciclo(dry_run=args.dry_run, con_huecos=args.huecos)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        registrar("n8n_puente", f"Envío a n8n fallido: {exc}", gravedad="media")
        print(f"Error: {exc}")
        return 2

    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
