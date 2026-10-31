"""
embeddings.py — Cliente de embeddings para LM Studio.

Endpoint esperado:
    http://127.0.0.1:1234/v1/embeddings
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np
import urllib.request
import urllib.error

from config import cargar_config

DEFAULT_TIMEOUT = 60.0


class ErrorEmbeddings(RuntimeError):
    pass


def _url() -> str:
    base = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234/v1")
    return base.rstrip("/") + "/embeddings"


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}

    api_key = os.environ.get("LMSTUDIO_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return headers


def _post(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        _url(),
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")

    return json.loads(body)


def _normalizar(texto: str) -> str:
    return " ".join(texto.split()).strip()


def embed_texts(
    textos: list[str],
    *,
    modelo: str | None = None,
    reintentos: int = 3,
    timeout: float = DEFAULT_TIMEOUT,
) -> np.ndarray:
    """
    Devuelve una matriz float32 de forma (n, dimension).
    """
    if not textos:
        return np.zeros((0, 0), dtype=np.float32)

    config = cargar_config()
    modelo = modelo or os.environ.get(
        "EMBEDDING_MODEL",
        "text-embedding-qwen3-embedding-0.6b",
    )

    limpios = [_normalizar(t) for t in textos]

    if any(not t for t in limpios):
        raise ValueError("No se pueden calcular embeddings de texto vacío")

    payload = {
        "model": modelo,
        "input": limpios,
    }

    ultimo_error: Exception | None = None

    for intento in range(1, reintentos + 1):
        try:
            respuesta = _post(payload, timeout)

            if "data" not in respuesta:
                raise ErrorEmbeddings(f"Respuesta sin 'data': {respuesta}")

            items = sorted(respuesta["data"], key=lambda x: x.get("index", 0))
            vectores = [item["embedding"] for item in items]

            matriz = np.asarray(vectores, dtype=np.float32)

            if matriz.shape[0] != len(limpios):
                raise ErrorEmbeddings(
                    f"Se esperaban {len(limpios)} embeddings y llegaron {matriz.shape[0]}"
                )

            normas = np.linalg.norm(matriz, axis=1, keepdims=True)
            normas[normas == 0.0] = 1.0

            return matriz / normas

        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            KeyError,
            ValueError,
            json.JSONDecodeError,
            ErrorEmbeddings,
        ) as exc:
            ultimo_error = exc

            if intento == reintentos:
                break

            time.sleep(min(2 ** intento, 10))

    raise ErrorEmbeddings(
        f"No se pudieron calcular embeddings tras {reintentos} intentos: {ultimo_error}"
    )


def modelo_actual() -> str:
    """Nombre del modelo de embeddings en uso (EMBEDDING_MODEL o el valor por defecto)."""
    return os.environ.get("EMBEDDING_MODEL", "text-embedding-qwen3-embedding-0.6b")


def embed_one(texto: str, **kwargs: Any) -> np.ndarray:
    return embed_texts([texto], **kwargs)[0]


import json  # noqa: E402
