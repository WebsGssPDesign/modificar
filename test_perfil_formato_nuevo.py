"""
perfil.py y analisis.py con el formato nuevo de intereses.json y objetivos.json
(los reales de la carpeta Perfil/ del proyecto, copiados a una bóveda temporal).
"""

import json
import shutil
from pathlib import Path

import pytest

import analisis
import config
import perfil

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def boveda_nueva(boveda):
    shutil.copytree(RAIZ / "Perfil", boveda / "Perfil")
    return boveda


def _json(boveda, nombre):
    return json.loads((boveda / "Perfil" / nombre).read_text(encoding="utf-8"))


def test_los_json_reales_son_validos_y_coherentes():
    perfil_usuario = json.loads((RAIZ / "Perfil" / "perfil_usuario.json").read_text(encoding="utf-8"))
    sistema = json.loads((RAIZ / "Perfil" / "sistema_aprendizaje.json").read_text(encoding="utf-8"))

    # el anidado roto ya no existe
    assert set(perfil_usuario["criterios_aprendizaje"]) == {"priorizar", "evitar"}
    for clave in ("memoria", "evaluacion", "aprendizaje", "estadisticas"):
        assert clave in perfil_usuario

    pesos = perfil_usuario["evaluacion"]["criterios"]
    assert pesos == {"relevancia": 40, "utilidad": 30, "confiabilidad": 20, "novedad": 10}
    assert sum(pesos.values()) == 100

    # una sola fuente para los umbrales
    assert "umbral_guardado" not in perfil_usuario["evaluacion"]
    assert sistema["puntuacion"]["guardar_memoria_larga"] == 85
    assert sistema["puntuacion"]["guardar_memoria_media"] == 70
    assert sistema["puntuacion"]["guardar_memoria_corta"] == 50


def test_la_lista_blanca_cubre_todas_las_fuentes_configuradas():
    reglas = json.loads((RAIZ / "Sistema" / "reglas.json").read_text(encoding="utf-8"))
    criterios = json.loads((RAIZ / "Perfil" / "criterios_busqueda.json").read_text(encoding="utf-8"))
    permitidos = reglas["web"]["dominios_permitidos"]

    def cubierto(host):
        host = host.removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in permitidos)

    from urllib.parse import urlparse

    urls = [f["url"] for f in criterios["fuentes_rss"] + criterios["releases_atom"]]
    urls += [d["url"] for d in criterios["documentacion_prioritaria"]]
    urls += ["https://api.github.com/search/repositories", "https://huggingface.co/api/models"]

    sin_cubrir = [u for u in urls if not cubierto(urlparse(u).netloc.lower())]
    assert sin_cubrir == []


def test_perfil_ve_los_intereses_y_objetivos_nuevos(boveda_nueva):
    datos = perfil.cargar()
    nombres = {i["nombre"]: i["peso"] for i in datos["intereses"]}

    assert len(datos["intereses"]) == 25
    assert nombres["n8n"] == 1.0
    assert nombres["MCP"] == 0.95
    assert nombres["Machine Learning"] == 0.8  # sin peso propio: defecto de principales
    assert nombres["Linux"] == 0.5  # secundario sin peso: defecto de secundarios

    assert [o["id"] for o in datos["objetivos"]] == [f"OBJ-00{n}" for n in range(1, 6)]
    assert datos["objetivos"][0]["texto"] == "Empresa IA Digital"
    assert datos["objetivos"][0]["prioridad"] == "alta"


def test_analisis_ve_los_intereses_nuevos(boveda_nueva):
    intereses = analisis._perfil_intereses(config.cargar_config())

    assert "SQLite-vec" in intereses and "Linux" in intereses and len(intereses) == 25


def test_escribir_no_vacia_ni_pierde_campos(boveda_nueva):
    perfil.agregar_interes("Qdrant", 0.7)
    perfil.agregar_objetivo("Publicar el flujo", "media")
    perfil.cambiar_estado_objetivo("OBJ-003", "pausado")

    intereses = _json(boveda_nueva, "intereses.json")
    objetivos = _json(boveda_nueva, "objetivos.json")

    assert "Qdrant" in intereses["principales"] and intereses["pesos"]["Qdrant"] == 0.7
    assert intereses["pesos"]["n8n"] == 1.0
    assert "evitar" in intereses and "aprendizaje" in intereses and "estadisticas" in intereses
    assert intereses["aprendizaje"]["peso_defecto_principales"] == 0.8
    assert "Linux" in intereses["secundarios"] and "Linux" not in intereses["pesos"]

    assert len(objetivos["objetivos"]) == 6
    assert "criterios_exito" in objetivos and "autoevaluacion" in objetivos
    assert objetivos["escala_progreso"] == {"min": 0, "max": 100}

    nuevo = objetivos["objetivos"][-1]
    assert nuevo["id"] == "OBJ-006" and nuevo["nombre"] == "Publicar el flujo"
    assert nuevo["prioridad"] == 5 and nuevo["progreso"] == 0 and nuevo["estado"] == "activo"

    pausado = next(o for o in objetivos["objetivos"] if o["id"] == "OBJ-003")
    assert pausado["estado"] == "pausado" and pausado["prioridad"] == 9  # no se pisa el 9 original


def test_quitar_interes_limpia_listas_y_peso(boveda_nueva):
    perfil.quitar_interes("SEO")

    intereses = _json(boveda_nueva, "intereses.json")

    assert "SEO" not in intereses["secundarios"]
    assert "SEO" not in intereses["pesos"]
    assert len(intereses["principales"]) == 20


def test_peso_fuera_de_rango_en_formato_nuevo(boveda_nueva):
    with pytest.raises(ValueError):
        perfil.agregar_interes("X", 5)  # 5 es válido en el formato viejo, no en el nuevo


def test_interes_sin_peso_usa_el_defecto_y_no_lo_guarda(boveda_nueva):
    perfil.agregar_interes("Qdrant")

    intereses = _json(boveda_nueva, "intereses.json")

    assert "Qdrant" in intereses["principales"]
    assert "Qdrant" not in intereses["pesos"]


def test_analisis_cuenta_las_notas_de_web(boveda_nueva, escribir_nota):
    escribir_nota(
        boveda_nueva,
        "LLM-Memoria/Web/memoria-agentes.md",
        '---\ntitulo: "x"\nconfianza: 0.9\ntags: ["mcp"]\n---\n## Entidades\n[[Ollama]]\n',
    )

    notas = analisis._leer_notas_generadas(config.cargar_config())

    assert [n["ruta"] for n in notas] == ["LLM-Memoria/Web/memoria-agentes.md"]
    assert notas[0]["tags"] == ["mcp"] and notas[0]["entidades"] == ["Ollama"]
