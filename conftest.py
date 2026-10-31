import json
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

_BOVEDA = Path(tempfile.mkdtemp(prefix="memoria_test_"))
os.environ["MEMORIA_BOVEDA"] = str(_BOVEDA)
os.environ["MEMORIA_MIN_SIM"] = "0.35"

for sub in ("Sistema", "Perfil", "LLM-Memoria/Hechos", "LLM-Memoria/Web",
            "Diario", "skills", "_descartados", ".memoria"):
    (_BOVEDA / sub).mkdir(parents=True, exist_ok=True)

def leer_jsonl(path: Path) -> list[dict]:
    """Lee un archivo JSONL y devuelve una lista de dicts."""
    if not path.exists():
        return []
    resultados = []
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea:
            resultados.append(json.loads(linea))
    return resultados
