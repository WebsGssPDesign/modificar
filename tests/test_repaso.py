from datetime import date, timedelta

import repaso

HOY = date(2026, 10, 25)


def _hecho(boveda, escribir_nota, nombre):
    return escribir_nota(boveda, f"LLM-Memoria/Hechos/{nombre}.md", f'---\ntitulo: "{nombre}"\n---\ncuerpo\n')


def test_inicializar_agenda_con_el_primer_escalon(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "a")

    nuevas = repaso.inicializar(hoy=HOY)
    texto = (boveda / "LLM-Memoria/Hechos/a.md").read_text(encoding="utf-8")

    assert nuevas == ["LLM-Memoria/Hechos/a.md"]
    assert "repasar: 2026-10-26" in texto
    assert "repaso_estado: sin-revisar" in texto
    assert repaso.inicializar(hoy=HOY) == []  # no repite


def test_vencidas_ordenadas_por_atraso(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "a")
    _hecho(boveda, escribir_nota, "b")
    repaso.inicializar(hoy=HOY - timedelta(days=10))
    repaso.marcar("LLM-Memoria/Hechos/b.md", hoy=HOY - timedelta(days=5))  # reagenda b

    pendientes = repaso.vencidas(hoy=HOY)

    assert [n["stem"] for n in pendientes][0] == "a"
    assert pendientes[0]["atraso"] == 9


def test_escalera_sube_y_olvidar_reinicia(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "a")
    ruta = "LLM-Memoria/Hechos/a.md"
    repaso.inicializar(hoy=HOY)

    r1 = repaso.marcar(ruta, hoy=HOY)
    r2 = repaso.marcar(ruta, hoy=HOY)
    olvidada = repaso.marcar(ruta, olvidada=True, hoy=HOY)

    assert (r1["nivel"], r1["proxima"]) == (1, "2026-10-28")   # +3 días
    assert (r2["nivel"], r2["proxima"]) == (2, "2026-11-01")   # +7 días
    assert (olvidada["nivel"], olvidada["proxima"]) == (0, "2026-10-26")


def test_el_ultimo_escalon_se_repite():
    assert repaso.intervalo_para(99, [1, 3, 7, 21, 60]) == 60
    assert repaso.intervalo_para(-1, [1, 3, 7]) == 1


def test_genera_cola_y_no_la_indexa(boveda, escribir_nota):
    _hecho(boveda, escribir_nota, "a")
    repaso.inicializar(hoy=HOY - timedelta(days=5))

    r = repaso.generar_cola(hoy=HOY)
    cola = boveda / "LLM-Memoria/Revision/cola.md"

    assert r["pendientes"] == 1
    assert "[[a\\|a]]" in cola.read_text(encoding="utf-8")


def test_marcar_nota_inexistente(boveda):
    import pytest

    with pytest.raises(FileNotFoundError):
        repaso.marcar("LLM-Memoria/Hechos/no-existe.md", hoy=HOY)
