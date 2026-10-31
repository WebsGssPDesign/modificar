import tablero


def test_dry_run_no_crea_archivos(boveda, embeddings_falsos):
    resultado = tablero.generar_tableros(dry_run=True)

    assert resultado["dry_run"] is True
    assert set(resultado["documentos"]) == {"Tablero", "Huecos", "Conocimiento", "AprendidoHoy"}
    assert not (boveda / "LLM-Memoria").exists() or not list((boveda / "LLM-Memoria").glob("*.md"))


def test_genera_los_cuatro_documentos(boveda, embeddings_falsos):
    tablero.generar_tableros()

    nombres = {p.name for p in (boveda / "LLM-Memoria").glob("*.md")}

    assert {"tablero.md", "huecos.md", "conocimiento.md", "aprendidohoy.md"} <= nombres


def test_funciona_sin_incidencias_ni_indice(boveda):
    """Regresión: abiertas() fallaba si incidencias.json no existía."""
    import incidencias

    assert incidencias.abiertas() == []
    assert tablero.generar_tablero()
