import json

import config
import eventos
import n8n_puente


def test_filtra_solo_lo_relevante():
    assert n8n_puente.es_relevante({"tipo": "x.error", "gravedad": "info"})
    assert n8n_puente.es_relevante({"tipo": "y", "gravedad": "alta"})
    assert n8n_puente.es_relevante({"tipo": "mcp.eliminar_nota", "gravedad": "info"})
    assert not n8n_puente.es_relevante({"tipo": "indexer.index.ok", "gravedad": "info"})


def test_dry_run_no_avanza_el_offset(boveda):
    eventos.emitir_evento("a.error", gravedad="alta", payload={"error": "boom", "secreto": "no"})

    r = n8n_puente.ciclo(dry_run=True)

    assert r["eventos"] == 1 and r["enviado"] is False
    assert "secreto" not in json.dumps(r["cuerpo"])  # solo metadatos permitidos
    assert not (config.cargar_config().memoria_dir / "n8n_estado.json").exists()


def test_envia_y_avanza_offset(boveda, monkeypatch):
    enviados = []
    monkeypatch.setenv("N8N_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/x")
    monkeypatch.setattr(n8n_puente, "enviar", lambda url, cuerpo, **kw: enviados.append(cuerpo))
    eventos.emitir_evento("a.error", gravedad="alta")

    primero = n8n_puente.ciclo()
    segundo = n8n_puente.ciclo()

    assert primero["enviado"] is True and len(enviados) == 1
    assert segundo["eventos"] == 0 and len(enviados) == 1


def test_si_falla_el_envio_no_avanza_y_reintenta(boveda, monkeypatch):
    import pytest

    monkeypatch.setenv("N8N_WEBHOOK_URL", "http://127.0.0.1:1/x")

    def caido(url, cuerpo, **kw):
        raise OSError("n8n caído")

    monkeypatch.setattr(n8n_puente, "enviar", caido)
    eventos.emitir_evento("a.error", gravedad="alta")

    with pytest.raises(OSError):
        n8n_puente.ciclo()

    enviados = []
    monkeypatch.setattr(n8n_puente, "enviar", lambda url, cuerpo, **kw: enviados.append(cuerpo))
    n8n_puente.ciclo()

    assert len(enviados) == 1  # el evento no se perdió


def test_lote_parcial_avanza_solo_lo_enviado(boveda, monkeypatch):
    enviados = []
    monkeypatch.setenv("N8N_WEBHOOK_URL", "http://127.0.0.1:5678/x")
    monkeypatch.setattr(n8n_puente, "enviar", lambda url, cuerpo, **kw: enviados.append(cuerpo))
    monkeypatch.setattr(n8n_puente, "MAX_EVENTOS_POR_ENVIO", 2)

    for i in range(5):
        eventos.emitir_evento("a.error", gravedad="alta", payload={"error": str(i)})

    n8n_puente.ciclo()
    n8n_puente.ciclo()
    n8n_puente.ciclo()

    errores = [e["payload"]["error"] for lote in enviados for e in lote["eventos"]]
    assert errores == ["0", "1", "2", "3", "4"]


def test_no_lee_lineas_incompletas(boveda):
    cfg = config.cargar_config()
    cfg.sistema.mkdir(exist_ok=True)
    cfg.eventos_path.write_text('{"tipo": "a.error", "gravedad": "alta"', encoding="utf-8")  # sin \n

    pares, offset = n8n_puente.leer_nuevos(cfg, 0)

    assert pares == [] and offset == 0
