import config


def test_defaults_se_aplican():
    assert config.get("memoria.min_sim") == 0.35


def test_env_gana_a_reglas(monkeypatch):
    monkeypatch.setenv("MEMORIA_MIN_SIM", "0.62")
    assert config.get("memoria.min_sim") == 0.62


def test_reglas_gana_a_default():
    ruta = config.SISTEMA / "reglas.json"
    ruta.write_text('{"memoria": {"pool": 7}}', encoding="utf-8")
    config.cargar(recargar=True)
    assert config.get("memoria.pool") == 7
    assert config.get("memoria.min_sim") == 0.35
    ruta.unlink()
    config.cargar(recargar=True)


def test_reglas_corrupto_no_lanza():
    ruta = config.SISTEMA / "reglas.json"
    ruta.write_text("{ roto", encoding="utf-8")
    config.cargar(recargar=True)
    assert config.get("memoria.pool") == 30
    ruta.unlink()
    config.cargar(recargar=True)


def test_lista_desde_env(monkeypatch):
    monkeypatch.setenv("WEB_DOMINIOS_PERMITIDOS", "a.com, b.com")
    assert config.get("web.dominios_permitidos") == ["a.com", "b.com"]


def test_origen(monkeypatch):
    monkeypatch.delenv("MEMORIA_MIN_SIM", raising=False)  # conftest fija esta env global para el suite
    assert config.origen("memoria.min_sim") == "default"
    monkeypatch.setenv("MEMORIA_MIN_SIM", "0.5")
    assert config.origen("memoria.min_sim") == "env"
