import pytest

import incidencias


@pytest.fixture(autouse=True)
def _incidencias_en_boveda_temporal(tmp_path, monkeypatch):
    """Aísla el registro: sin esto los tests escriben en Sistema/incidencias.json
    compartido y `reintentos` se acumula entre corridas (el fallo que vimos)."""
    monkeypatch.setenv("MEMORIA_BOVEDA", str(tmp_path))
    (tmp_path / "Sistema").mkdir(exist_ok=True)
    return tmp_path


def test_agrupa_por_componente_y_error():
    incidencias.registrar("web", "timeout", "baja", "react.dev")
    incidencias.registrar("web", "timeout", "baja", "react.dev")
    abiertas = incidencias.abiertas("web")
    assert len(abiertas) == 1 and abiertas[0]["reintentos"] == 2


def test_primer_registro_cuenta_una_ocurrencia():
    """El contador es de ocurrencias totales: el primer registro marca 1."""
    incidencias.registrar("web", "timeout", "baja")
    abiertas = incidencias.abiertas("web")
    assert len(abiertas) == 1 and abiertas[0]["reintentos"] == 1


def test_detalle_str_se_guarda_como_fuente():
    incidencias.registrar("web", "timeout", "baja", "react.dev")
    abiertas = incidencias.abiertas("web")
    assert abiertas[0]["detalle"] == {"fuente": "react.dev"}


def test_dedupe_no_toca_otros_modulos():
    incidencias.registrar("web", "timeout", "baja")
    incidencias.registrar("web", "timeout", "alta")     # mismo modulo/mensaje -> agrupa
    incidencias.registrar("indice", "timeout", "baja")  # otro modulo -> nueva
    assert len(incidencias.abiertas()) == 2


def test_cerrar_mueve_a_cerradas():
    incidencias.registrar("indice", "database is locked", "alta")
    assert incidencias.cerrar("indice", "database is locked") is True
    assert incidencias.abiertas("indice") == []


def test_abiertas_sin_argumento_devuelve_todo():
    """Compatibilidad con tablero.py y estado.py, que llaman abiertas() sin filtro."""
    incidencias.registrar("web", "timeout", "baja")
    incidencias.registrar("indice", "database is locked", "alta")
    assert len(incidencias.abiertas()) == 2
