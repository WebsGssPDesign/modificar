import memoria

NOTA = "---\ntags: [python]\n---\n# Python basico\n## Listas\nLas listas se crean con corchetes.\n## Diccionarios\nLos diccionarios guardan pares clave valor.\n"


def test_rrf_fusiona_dos_rankings():
    fts = [("a", 1.0), ("b", 0.5)]
    vec = [("b", 0.9), ("c", 0.4)]

    fusion = memoria._rrf([fts, vec], limite=3)
    ids = [x[0] for x in fusion]

    assert ids[0] == "b"  # aparece en ambos rankings
    assert set(ids) == {"a", "b", "c"}
    assert fusion[0][2] == {"fts": 2, "vec": 1}


def test_indexa_y_busca(boveda, escribir_nota, embeddings_falsos):
    escribir_nota(boveda, "Notas/python.md", NOTA)

    stats = memoria.indexar_boveda()

    assert stats["errores"] == 0
    assert stats["chunks_nuevos"] >= 2
    estado = memoria.estado_indice()
    assert estado["chunks"] == estado["con_embedding"] > 0

    resultados = memoria.buscar_hibrido("diccionarios clave valor", k=3)
    assert resultados
    assert resultados[0].encabezado == "Diccionarios"
    assert resultados[0].ruta == "Notas/python.md"  # ruta relativa, no absoluta


def test_indexacion_es_incremental(boveda, escribir_nota, embeddings_falsos):
    escribir_nota(boveda, "Notas/python.md", NOTA)
    memoria.indexar_boveda()

    segunda = memoria.indexar_boveda()

    assert segunda["archivos_actualizados"] == 0
    assert segunda["chunks_nuevos"] == 0


def test_forzar_reprocesa_aunque_no_haya_cambios(boveda, escribir_nota, embeddings_falsos):
    escribir_nota(boveda, "Notas/python.md", NOTA)
    memoria.indexar_boveda()

    forzada = memoria.indexar_boveda(forzar=True)

    assert forzada["archivos_actualizados"] == 1


def test_poda_archivos_borrados(boveda, escribir_nota, embeddings_falsos):
    ruta = escribir_nota(boveda, "Notas/python.md", NOTA)
    memoria.indexar_boveda()
    ruta.unlink()

    stats = memoria.indexar_boveda()

    assert stats["archivos_eliminados"] == 1
    assert memoria.estado_indice()["chunks"] == 0


def test_indexa_conocimiento_generado_pero_no_sistema_ni_tablero(
    boveda, escribir_nota, embeddings_falsos
):
    escribir_nota(boveda, "LLM-Memoria/Hechos/hecho.md", "# Hecho\nconocimiento aprendido\n")
    escribir_nota(boveda, "LLM-Memoria/tablero.md", "# Tablero\nignorar esto\n")
    escribir_nota(boveda, "Sistema/propuestas.md", "# Propuestas\nignorar esto\n")

    memoria.indexar_boveda()
    rutas = {r.ruta for r in memoria.buscar_hibrido("conocimiento aprendido", k=10)}

    assert "LLM-Memoria/Hechos/hecho.md" in rutas
    assert not any("tablero" in r or r.startswith("Sistema") for r in rutas)


def test_error_de_embeddings_registra_incidencia(boveda, escribir_nota, monkeypatch):
    import incidencias

    def roto(textos, **kw):
        raise RuntimeError("LM Studio caído")

    monkeypatch.setattr(memoria, "embed_texts", roto)
    escribir_nota(boveda, "Notas/python.md", NOTA)

    stats = memoria.indexar_boveda()

    assert stats["errores"] == 1
    assert any("memoria.indexar" == i["modulo"] for i in incidencias.abiertas())
