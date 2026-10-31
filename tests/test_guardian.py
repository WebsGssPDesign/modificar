import time

import config
import guardian
import util


def test_modo_observacion_por_defecto(boveda):
    informe = guardian.vigilar()

    assert informe.modo == "observacion"
    assert (boveda / "Sistema" / "propuestas.md").exists()


def test_detecta_heartbeat_silencioso(boveda):
    cfg = config.cargar_config()
    util.escribir_json_atomico(
        cfg.heartbeat_path, {"ts": time.time() - 5000, "iso": "x", "paso": "aprender"}
    )

    informe = guardian.vigilar()

    assert "heartbeat_silencioso" in {h.codigo for h in informe.hallazgos}


def test_detecta_heartbeat_ausente(boveda):
    informe = guardian.vigilar()

    assert "heartbeat_ausente" in {h.codigo for h in informe.hallazgos}


def test_no_modifica_notas_en_observacion(boveda, escribir_nota):
    ruta = escribir_nota(boveda, "Notas/a.md", "# a\n")
    antes = ruta.read_text(encoding="utf-8")

    guardian.vigilar()

    assert ruta.read_text(encoding="utf-8") == antes
