import json

import analisis
import perfil


def test_flujo_completo(boveda):
    perfil.inicializar(nombre="Ana", rol="Dev", stack=["python", "sql"])
    perfil.agregar_interes("Machine Learning", 5)
    perfil.agregar_objetivo("Aprender SQL", "alta")
    perfil.cambiar_estado_objetivo("o1", "hecho")

    datos = perfil.cargar()

    assert datos["perfil"]["stack"] == ["python", "sql"]
    assert datos["intereses"] == [{"nombre": "Machine Learning", "peso": 5}]
    assert datos["objetivos"][0]["estado"] == "hecho"
    md = (boveda / "Perfil" / "perfil-usuario.md").read_text(encoding="utf-8")
    assert "- [x] `o1`" in md


def test_interes_repetido_actualiza_peso(boveda):
    perfil.agregar_interes("SQL", 2)
    perfil.agregar_interes("sql", 4)

    assert perfil.cargar()["intereses"] == [{"nombre": "SQL", "peso": 4}]


def test_ids_de_objetivo_no_se_reutilizan(boveda):
    perfil.agregar_objetivo("a")
    perfil.agregar_objetivo("b")
    perfil.quitar_objetivo("o1")

    perfil.agregar_objetivo("c")

    assert [o["id"] for o in perfil.cargar()["objetivos"]] == ["o2", "o3"]


def test_validaciones(boveda):
    import pytest

    with pytest.raises(ValueError):
        perfil.agregar_interes("x", 9)
    with pytest.raises(ValueError):
        perfil.agregar_objetivo("x", "urgente")
    with pytest.raises(KeyError):
        perfil.quitar_objetivo("o99")


def test_analisis_lee_los_intereses(boveda):
    perfil.agregar_interes("Machine Learning", 5)

    assert "Machine Learning" in analisis._perfil_intereses(__import__("config").cargar_config())


def test_los_cambios_quedan_auditados(boveda):
    perfil.agregar_interes("SQL")

    lineas = (boveda / "Sistema" / "auditoria.jsonl").read_text(encoding="utf-8").splitlines()
    actores = {json.loads(l)["actor"] for l in lineas}

    assert actores == {"perfil"}
