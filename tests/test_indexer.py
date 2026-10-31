import sys

import indexer
import memoria

NOTA = "# Redes\nTexto sobre redes y protocolos.\n"


def test_vigilar_sale_si_existe_stop(boveda):
    import config

    cfg = config.cargar_config()
    config.preparar_carpetas(cfg)
    (cfg.memoria_dir / "STOP").touch()

    assert indexer.vigilar_boveda(intervalo=0.01) == 0


def test_vigilar_indexa_en_el_primer_ciclo(boveda, escribir_nota, embeddings_falsos):
    escribir_nota(boveda, "Notas/redes.md", NOTA)

    codigo = indexer.vigilar_boveda(intervalo=0.01, max_ciclos=1)

    assert codigo == 0
    assert memoria.estado_indice()["chunks"] == 1


def test_vigilar_detecta_archivo_nuevo(boveda, escribir_nota, embeddings_falsos):
    escribir_nota(boveda, "Notas/redes.md", NOTA)
    indexer.vigilar_boveda(intervalo=0.01, max_ciclos=1)

    escribir_nota(boveda, "Notas/bd.md", "# Bases de datos\nTexto sobre SQL.\n")
    indexer.vigilar_boveda(intervalo=0.01, max_ciclos=1)

    assert memoria.estado_indice()["archivos"] == 2


def test_cli_status_devuelve_cero(boveda, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["indexer.py", "--status"])

    assert indexer.main() == 0


def test_cli_sin_argumentos_devuelve_uno(boveda, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["indexer.py"])

    assert indexer.main() == 1
