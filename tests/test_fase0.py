import json
from pathlib import Path

import config
import escritor
import util


def test_config_basica(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORIA_BOVEDA", str(tmp_path))

    cfg = config.cargar_config()

    assert cfg.boveda == tmp_path.resolve()
    assert cfg.sistema == tmp_path / "Sistema"
    assert cfg.db_path == tmp_path / "memoria_vectorial" / ".memoria" / "indice.sqlite"


def test_escritura_atomica(tmp_path):
    destino = tmp_path / "nota.md"
    util.escribir_texto_atomico(destino, "v1")

    util.escribir_texto_atomico(destino, "v2")

    assert destino.read_text(encoding="utf-8") == "v2"


def test_ruta_fuera_de_boveda(tmp_path):
    base = tmp_path / "boveda"
    base.mkdir()

    try:
        util.ruta_relativa_segura("../fuera.md", base)
        assert False, "Debía rechazar la ruta"
    except ValueError:
        pass


def test_crear_editar_eliminar(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORIA_BOVEDA", str(tmp_path))
    config.preparar_carpetas(config.cargar_config())

    resultado = escritor.crear_nota(
        "Prueba de memoria",
        "Contenido inicial",
        carpeta="LLM-Memoria/Hechos",
        tags=["test"],
    )

    assert resultado.ok

    ruta = resultado.ruta
    assert ruta.exists()

    edicion = escritor.editar_nota(
        ruta.relative_to(tmp_path),
        "Contenido inicial",
        "Contenido actualizado",
    )

    assert edicion.ok
    assert "Contenido actualizado" in ruta.read_text(encoding="utf-8")
    assert edicion.backup is not None

    eliminacion = escritor.eliminar_nota(ruta.relative_to(tmp_path))

    assert eliminacion.ok
    assert not ruta.exists()
    assert (tmp_path / "Sistema" / "papelera").exists()


def test_eventos_y_metricas(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORIA_BOVEDA", str(tmp_path))
    config.preparar_carpetas(config.cargar_config())

    import eventos
    import metricas

    evento = eventos.emitir_evento("prueba", payload={"ok": True})
    assert evento["tipo"] == "prueba"

    with metricas.medir("test", "entrada") as registro:
        registro["salida"] = "ok"

    assert (tmp_path / "Sistema" / "eventos.jsonl").exists()
    assert (tmp_path / "Sistema" / "metricas.jsonl").exists()
