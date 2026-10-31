import escritor
import tablero


def test_genera_los_cuatro_archivos():
    escritor.escribir("LLM-Memoria/Hechos/uno.md", "# uno\ncuerpo",
                      {"fecha": "2026-10-21", "etapa": "aprendizaje", "tema": "[React]"},
                      "aprender")
    tablero.actualizar()
    for rel in ("LLM-Memoria/Tablero.md", "LLM-Memoria/AprendidoHoy.md",
                "LLM-Memoria/AprendidoSemana.md", "LLM-Memoria/Revision/Cola.md"):
        assert (tablero.config.VAULT / rel).exists(), rel


def test_tablero_es_idempotente():
    tablero.actualizar()
    a = (tablero.config.VAULT / "LLM-Memoria/Tablero.md").read_text(encoding="utf-8")
    tablero.actualizar()
    b = (tablero.config.VAULT / "LLM-Memoria/Tablero.md").read_text(encoding="utf-8")
    assert a.splitlines()[3:] == b.splitlines()[3:]
