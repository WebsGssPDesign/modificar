"""
Fixtures compartidas. Ningún test necesita LM Studio ni red:
los embeddings y el LLM se sustituyen por versiones deterministas.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

VARIABLES_A_LIMPIAR = (
    "MEMORIA_NOTAS",
    "MEMORIA_MIN_SIM",
    "MEMORIA_POOL",
    "MEMORIA_MAX_SYNC_SEGUNDOS",
    "MEMORIA_GUARDIAN_MODO",
    "WEB_LIMITES_MAX_POR_HORA",
    "WEB_LIMITES_MAX_POR_DIA",
    "N8N_WEBHOOK_URL",
    "N8N_WEBHOOK_TOKEN",
    "MEMORIA_LOG_NIVEL",
    "MEMORIA_LOG_CONSOLA",
)


def embedding_falso(textos, **kwargs):
    """Bolsa de palabras hasheada a 64 dimensiones, normalizada."""
    filas = []

    for texto in textos:
        v = np.zeros(64, dtype=np.float32)

        for palabra in str(texto).lower().split():
            v[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % 64] += 1.0

        norma = np.linalg.norm(v) or 1.0
        filas.append(v / norma)

    return np.vstack(filas)


@pytest.fixture
def boveda(tmp_path, monkeypatch):
    """Bóveda temporal vacía, aislada del entorno real."""
    monkeypatch.setenv("MEMORIA_BOVEDA", str(tmp_path))

    for variable in VARIABLES_A_LIMPIAR:
        monkeypatch.delenv(variable, raising=False)

    (tmp_path / "Sistema").mkdir()
    (tmp_path / "Notas").mkdir()
    return tmp_path


@pytest.fixture
def escribir_nota():
    def _escribir(boveda: Path, relativa: str, texto: str) -> Path:
        ruta = boveda / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    return _escribir


@pytest.fixture
def embeddings_falsos(monkeypatch):
    import embeddings
    import memoria

    uno = lambda texto, **kw: embedding_falso([texto])[0]  # noqa: E731

    monkeypatch.setattr(embeddings, "embed_texts", embedding_falso)
    monkeypatch.setattr(memoria, "embed_texts", embedding_falso)
    monkeypatch.setattr(memoria, "embed_one", uno)

    for nombre in ("aprender", "aprender_web", "crear_skills"):
        modulo = importlib.import_module(nombre)

        if hasattr(modulo, "embed_one"):
            monkeypatch.setattr(modulo, "embed_one", uno)

    return embedding_falso


@pytest.fixture
def llm_falso(monkeypatch):
    """Sustituye chat_json por una respuesta fija de 'aprendizaje'."""
    import aprender
    import llm

    respuesta = {
        "util": True,
        "titulo": "Listas y diccionarios en Python",
        "resumen": "Las listas usan corchetes y los diccionarios guardan pares clave valor.",
        "hechos": ["Las listas permiten append", "Los diccionarios guardan pares"],
        "tags": ["python"],
        "entidades": ["Python", "Diccionario"],
        "confianza": 0.9,
        "motivo_descarte": "",
    }
    llamadas: list[str] = []

    def falso(prompt_sistema, prompt_usuario, **kwargs):
        llamadas.append(prompt_usuario)
        return dict(respuesta)

    monkeypatch.setattr(llm, "chat_json", falso)
    monkeypatch.setattr(aprender, "chat_json", falso)

    return {"respuesta": respuesta, "llamadas": llamadas}


def leer_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []

    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
