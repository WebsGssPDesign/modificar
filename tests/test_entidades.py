import entidades


def _hecho(boveda, escribir_nota, nombre, ents):
    escribir_nota(
        boveda,
        f"LLM-Memoria/Hechos/{nombre}.md",
        f'---\ntitulo: "{nombre}"\n---\n## Resumen\n\nx\n\n## Entidades\n\n{ents}\n\n## Fuente\n\n- x\n',
    )


def test_umbral_de_menciones_evita_ruido(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "n1", "[[Python]], [[SQLite]], [[Solo Una]]")
    _hecho(boveda, escribir_nota, "n2", "[[python]], [[SQLite]]")

    r = entidades.generar(min_menciones=2)

    nombres = {p.name for p in (boveda / "LLM-Memoria/Entidades").glob("*.md")}
    assert nombres == {"python.md", "sqlite.md"}
    assert r["entidades"] == 2


def test_acepta_formato_antiguo_sin_wikilinks_y_descarta_relleno(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "n1", "Python, 123, N/A, -")
    _hecho(boveda, escribir_nota, "n2", "Python")

    r = entidades.generar(min_menciones=2)

    assert r["entidades"] == 1


def test_backlinks_y_relaciones(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "n1", "[[Python]], [[SQLite]]")
    _hecho(boveda, escribir_nota, "n2", "[[Python]], [[SQLite]]")

    entidades.generar()
    texto = (boveda / "LLM-Memoria/Entidades/sqlite.md").read_text(encoding="utf-8")

    assert "[[n1|n1]]" in texto and "[[n2|n2]]" in texto
    assert "[[python|Python]] (2 notas en común)" in texto
    assert 'aliases: ["SQLite"]' in texto


def test_es_idempotente(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "n1", "[[Python]]")
    _hecho(boveda, escribir_nota, "n2", "[[Python]]")
    entidades.generar()

    segunda = entidades.generar()

    assert segunda["sin_cambios"] == 1
    assert segunda["creadas"] == [] and segunda["actualizadas"] == []


def test_obsoletas_se_reportan_y_solo_limpiar_las_mueve(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "n1", "[[Python]]")
    _hecho(boveda, escribir_nota, "n2", "[[Python]]")
    entidades.generar()
    (boveda / "LLM-Memoria/Hechos/n2.md").unlink()

    sin_limpiar = entidades.generar()
    assert sin_limpiar["obsoletas"] == ["python.md"]
    assert (boveda / "LLM-Memoria/Entidades/python.md").exists()

    entidades.generar(limpiar=True)
    assert not (boveda / "LLM-Memoria/Entidades/python.md").exists()


def test_colision_de_slug_conserva_la_mas_mencionada(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "n1", "[[C++]], [[C#]]")
    _hecho(boveda, escribir_nota, "n2", "[[C++]], [[C#]]")
    _hecho(boveda, escribir_nota, "n3", "[[C++]]")

    r = entidades.generar()

    assert r["entidades"] == 1
    assert r["colisiones"]
