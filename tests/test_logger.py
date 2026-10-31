import json

import logger


def test_escribe_json_estructurado(boveda):
    log = logger.get_logger("prueba")

    log.info("hola", extra={"datos": {"n": 1}})
    logger.cerrar()

    linea = (boveda / "Sistema/logs/memoria.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    registro = json.loads(linea)

    assert registro["modulo"] == "prueba"
    assert registro["nivel"] == "INFO"
    assert registro["datos"] == {"n": 1}


def test_respeta_el_nivel_de_entorno(boveda, monkeypatch):
    monkeypatch.setenv("MEMORIA_LOG_NIVEL", "ERROR")
    log = logger.get_logger("nivel")

    log.info("no debe aparecer")
    log.error("sí debe aparecer")
    logger.cerrar()

    registros = logger.leer_log(10)

    assert [r["mensaje"] for r in registros] == ["sí debe aparecer"]


def test_leer_log_filtra_por_nivel_y_modulo(boveda):
    logger.get_logger("a").warning("w")
    logger.get_logger("b").error("e")
    logger.cerrar()

    assert [r["mensaje"] for r in logger.leer_log(10, nivel_minimo="ERROR")] == ["e"]
    assert [r["mensaje"] for r in logger.leer_log(10, modulo="a")] == ["w"]
