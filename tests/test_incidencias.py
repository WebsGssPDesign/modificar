import incidencias


def test_agrupa_por_componente_y_error():
    incidencias.registrar("web", "timeout", "baja", "react.dev")
    incidencias.registrar("web", "timeout", "baja", "react.dev")
    abiertas = incidencias.abiertas("web")
    assert len(abiertas) == 1 and abiertas[0]["reintentos"] == 2


def test_cerrar_mueve_a_cerradas():
    incidencias.registrar("indice", "database is locked", "alta")
    assert incidencias.cerrar("indice", "database is locked") is True
    assert incidencias.abiertas("indice") == []
