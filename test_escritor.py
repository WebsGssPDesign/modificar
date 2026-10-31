import pytest

import config
import escritor


def test_frontmatter_escapa_yaml():
    fm = escritor.frontmatter({"fuente": 'una "url" con: dos puntos',
                               "tags": ["a", "b"], "generado": True, "n": 3})
    assert '\\"' in fm and fm.count("---") == 2
    assert "generado: true" in fm and "n: 3" in fm


def test_rel_valida_no_sale_de_la_boveda():
    assert escritor.rel_valida("LLM-Memoria/x.md").name == "x.md"
    with pytest.raises(ValueError):
        escritor.rel_valida("../fuera.md")


def test_escribir_y_eliminar_va_a_papelera():
    escritor.escribir("LLM-Memoria/Notas/t.md", "hola", {"fecha": "2026-01-01"}, "test")
    ruta = config.VAULT / "LLM-Memoria/Notas/t.md"
    assert ruta.exists()
    copia = escritor.eliminar("LLM-Memoria/Notas/t.md", "test")
    assert copia and copia.exists() and not ruta.exists()


def test_sobrescribir_deja_bak():
    escritor.escribir("LLM-Memoria/Notas/b.md", "v1", None, "test")
    escritor.escribir("LLM-Memoria/Notas/b.md", "v2", None, "test", sobrescribir=True)
    assert (config.VAULT / "LLM-Memoria/Notas/b.md.bak").exists()


def test_wikilink():
    assert escritor.wikilink("LLM-Memoria/Web/x.md") == "[[LLM-Memoria/Web/x|x]]"
