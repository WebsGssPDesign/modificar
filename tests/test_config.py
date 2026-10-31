import config


def test_defaults_protegen_contra_aprender_de_si_mismo(boveda):
    cfg = config.cargar_config()

    for carpeta in ("LLM-Memoria", "Sistema", "Diario", "Perfil", "skills"):
        assert carpeta in cfg.aprender_excluir


def test_el_indice_si_incluye_lo_generado_pero_no_sistema(boveda):
    cfg = config.cargar_config()

    assert "LLM-Memoria" not in cfg.indice_excluir
    assert "Sistema" in cfg.indice_excluir


def test_reglas_json_sobrescribe_defaults(boveda):
    (boveda / "Sistema" / "reglas.json").write_text(
        '{"indice": {"excluir": ["Privado"]}}', encoding="utf-8"
    )

    assert config.cargar_config().indice_excluir == ["Privado"]


def test_variable_de_entorno_gana_a_reglas(boveda, monkeypatch):
    (boveda / "Sistema" / "reglas.json").write_text('{"memoria": {"pool": 10}}', encoding="utf-8")
    monkeypatch.setenv("MEMORIA_POOL", "77")

    cfg = config.cargar_config()

    assert cfg.pool.valor == 77 and cfg.pool.origen == "env"
