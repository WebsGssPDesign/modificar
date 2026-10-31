"""
llm.py — Cliente único de chat para LM Studio.

Reglas:
- El LLM recibe texto y devuelve texto/JSON.
- Nunca elige rutas, ni usa herramientas, ni escribe archivos.
- Todas las respuestas se validan antes de usarse.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from config import cargar_config
from eventos import emitir_evento
from incidencias import registrar
from metricas import medir

DEFAULT_TIMEOUT = 180.0
DEFAULT_MAX_TOKENS = 1200
DEFAULT_TEMPERATURE = 0.2

THINKING_RE = re.compile(
    r"|<thinking>.*?</thinking>",
    re.DOTALL | re.IGNORECASE,
)


class ErrorLLM(RuntimeError):
    pass


def _url() -> str:
    base = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234/v1")
    return base.rstrip("/") + "/chat/completions"


def _headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
    }

    api_key = os.environ.get("LMSTUDIO_API_KEY")

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return headers


def _modelo_default() -> str:
    return os.environ.get("LLM_MODEL", "qwen3.5-9b")


def _post(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        _url(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _limpiar_respuesta(texto: str) -> str:
    texto = THINKING_RE.sub("", texto)
    return texto.strip()


def _extraer_json(texto: str) -> dict[str, Any]:
    texto = _limpiar_respuesta(texto)

    try:
        datos = json.loads(texto)

        if isinstance(datos, dict):
            return datos
    except json.JSONDecodeError:
        pass

    # Rescate: primer bloque JSON balanceado.
    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio >= 0 and fin > inicio:
        try:
            datos = json.loads(texto[inicio : fin + 1])

            if isinstance(datos, dict):
                return datos
        except json.JSONDecodeError:
            pass

    raise ErrorLLM("El modelo no devolvió un objeto JSON válido")


def chat(
    prompt_sistema: str,
    prompt_usuario: str,
    *,
    modelo: str | None = None,
    temperatura: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    json_mode: bool = False,
    reintentos: int = 3,
    timeout: float = DEFAULT_TIMEOUT,
    entrada_metrica: str = "chat",
) -> str:
    """
    Ejecuta una conversación simple y devuelve el texto limpio.
    """
    config = cargar_config()
    modelo = modelo or _modelo_default()

    payload: dict[str, Any] = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario},
        ],
        "temperature": temperatura,
        "max_tokens": max_tokens,
        "stream": False,
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    ultimo_error: Exception | None = None

    with medir("llm.chat", entrada_metrica) as registro:
        for intento in range(1, reintentos + 1):
            try:
                respuesta = _post(payload, timeout)

                contenido = respuesta["choices"][0]["message"]["content"]
                contenido = _limpiar_respuesta(contenido)

                if not contenido:
                    raise ErrorLLM("Respuesta vacía del modelo")

                registro["salida"] = {
                    "modelo": modelo,
                    "intentos": intento,
                    "caracteres": len(contenido),
                }

                return contenido

            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
                KeyError,
                IndexError,
                json.JSONDecodeError,
                ErrorLLM,
            ) as exc:
                ultimo_error = exc
                registro["resultado"] = "error"
                registro["error"] = str(exc)

                if intento < reintentos:
                    time.sleep(min(2 ** intento, 15))

    incidencia_id = registrar(
        "llm.chat",
        f"Chat fallido tras {reintentos} intentos: {ultimo_error}",
        gravedad="alta",
        detalle={"modelo": modelo},
    )

    emitir_evento(
        "llm.chat.error",
        gravedad="alta",
        payload={"incidencia": incidencia_id, "modelo": modelo},
    )

    raise ErrorLLM(f"Chat fallido tras {reintentos} intentos: {ultimo_error}")


def chat_json(
    prompt_sistema: str,
    prompt_usuario: str,
    *,
    modelo: str | None = None,
    temperatura: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    reintentos: int = 3,
    timeout: float = DEFAULT_TIMEOUT,
    entrada_metrica: str = "chat_json",
) -> dict[str, Any]:
    """
    Ejecuta chat en modo JSON y devuelve un diccionario validado.
    """
    texto = chat(
        prompt_sistema,
        prompt_usuario,
        modelo=modelo,
        temperatura=temperatura,
        max_tokens=max_tokens,
        json_mode=True,
        reintentos=reintentos,
        timeout=timeout,
        entrada_metrica=entrada_metrica,
    )

    return _extraer_json(texto)
