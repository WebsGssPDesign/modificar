import time

import config
import estado
import incidencias
import util


def test_bobeda_vacia_es_atencion_no_critico(boveda):
    datos = estado.recolectar()

    assert datos["veredicto"] == "atencion"
    assert datos["indice"]["existe"] is False
    assert datos["heartbeat"]["estado"] == "sin_latidos"


def test_heartbeat_viejo_es_critico(boveda):
    cfg = config.cargar_config()
    util.escribir_json_atomico(cfg.heartbeat_path, {"ts": time.time() - 5000, "paso": "x"})

    assert estado.recolectar()["veredicto"] == "critico"


def test_cuenta_incidencias_y_errores(boveda):
    import eventos

    incidencias.registrar("mod", "algo falló", gravedad="alta")
    eventos.emitir_evento("x.error", gravedad="alta", payload={"error": "boom"})

    datos = estado.recolectar()

    assert datos["incidencias"]["abiertas"] == 1
    assert datos["incidencias"]["por_gravedad"] == {"alta": 1}
    assert datos["errores"]["eventos"][0]["tipo"] == "x.error"


def test_registra_ultimo_aprendizaje(boveda):
    import eventos

    eventos.emitir_evento("aprender.ciclo.ok", payload={"publicados": 2})

    assert estado.recolectar()["ultimo_aprendizaje"]["payload"] == {"publicados": 2}


def test_publicar_tablero_crea_nota(boveda):
    ruta = estado.publicar_tablero(estado.recolectar())

    assert ruta.name == "estado.md"
    assert "Estado del sistema" in ruta.read_text(encoding="utf-8")


def test_render_texto_y_markdown(boveda):
    datos = estado.recolectar()

    assert "Estado general" in estado.render_texto(datos)
    assert "| Componente | Estado |" in estado.render_markdown(datos)
