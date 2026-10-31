import aprender
import config


def _preparar(boveda, escribir_nota):
    escribir_nota(boveda, "Notas/python.md", "# Python\nLas listas usan corchetes.\n")


def test_aprende_y_publica_nota(boveda, escribir_nota, embeddings_falsos, llm_falso):
    _preparar(boveda, escribir_nota)

    resumen = aprender.aprender_boveda()

    assert resumen["publicados"] == 1
    nota = boveda / "LLM-Memoria/Hechos/listas-y-diccionarios-en-python.md"
    texto = nota.read_text(encoding="utf-8")
    assert "## Hechos" in texto
    assert "[[Python]]" in texto  # entidades como wikilinks (grafo de Obsidian)
    assert "fuente: Notas/python.md" in texto


def test_no_reprocesa_archivos_ya_vistos(boveda, escribir_nota, embeddings_falsos, llm_falso):
    _preparar(boveda, escribir_nota)
    aprender.aprender_boveda()

    segunda = aprender.aprender_boveda()

    assert segunda["procesados"] == 0
    assert segunda["omitidos"] == 1
    assert len(llm_falso["llamadas"]) == 1


def test_descarta_lo_no_util(boveda, escribir_nota, embeddings_falsos, llm_falso):
    _preparar(boveda, escribir_nota)
    llm_falso["respuesta"].update({"util": False, "motivo_descarte": "trivial"})

    resumen = aprender.aprender_boveda()

    assert resumen["descartados"] == 1
    assert resumen["publicados"] == 0


def test_dry_run_no_escribe(boveda, escribir_nota, embeddings_falsos, llm_falso):
    _preparar(boveda, escribir_nota)

    aprender.aprender_boveda(dry_run=True)

    assert not list((boveda / "LLM-Memoria").rglob("*.md"))


def test_nunca_aprende_de_sus_propias_salidas(boveda, escribir_nota):
    escribir_nota(boveda, "LLM-Memoria/Hechos/x.md", "# x\n")
    escribir_nota(boveda, "Sistema/propuestas.md", "# p\n")
    escribir_nota(boveda, "Diario/hoy.md", "# d\n")
    escribir_nota(boveda, "Perfil/perfil-usuario.md", "# p\n")
    escribir_nota(boveda, "Notas/real.md", "# real\n")

    candidatos = aprender._archivos_candidatos(config.cargar_config())

    assert [c.relative_to(boveda).as_posix() for c in candidatos] == ["Notas/real.md"]
