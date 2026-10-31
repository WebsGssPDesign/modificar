"""Conftest de compatibilidad: deja la raíz en sys.path.

Las fixtures reales (boveda, embeddings_falsos, llm_falso, leer_jsonl) viven en
tests/conftest.py, que es donde pytest las recoge cuando se ejecuta con
`testpaths = ["tests"]` desde la raíz del proyecto.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
