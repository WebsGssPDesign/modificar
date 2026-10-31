"""
ingesta_web.py: del buzón de n8n a notas en LLM-Memoria/Web.
Sin LM Studio ni red. Se usan los JSON reales de Perfil/ y la lista blanca real de reglas.json.
"""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

import config
import ingesta_web
from conftest import leer_jsonl

RAIZ = Path(__file__).resolve().parents[1]
HOY = date(2026, 10, 30)


@pytest.fixture
def web(boveda):
    shutil.copytree(RAIZ / "Perfil", boveda / "Perfil")
    shutil.copy(RAIZ / "Sistema" / "reglas.json", boveda / "Sistema" / "reglas.json")
    cfg = config.cargar_config()
    buzon = cfg.memoria_dir / "entrada_web"
    buzon.mkdir(parents=True, exist_ok=True)
    return boveda, buzon


def paquete(**cambios):
    base = {
        "version": 1,
        "url": "https://github.com/ejemplo/agent-memory-demo",
        "disparador": {"tipo": "dominio_vigilado", "detalle": "agent memory"},
        "titulo_original": "agent-memory-demo",
        "titulo_es": "Memoria de largo plazo para agentes (demo)",
        "idioma_original": "en",
        "fecha_publicacion": "2026-10-20",
        "resumen_es": "Biblioteca de ejemplo que guarda memoria de largo plazo para agentes con SQLite.",
        "hechos_es": ["Usa SQLite", "Licencia MIT"],
        "tags": ["n8n", "Agentes", "memoria"],
        "entidades": ["SQLite", "[[Mal|formada]]"],
        "objetivos": ["OBJ-002", "OBJ-999"],
        "componentes": {"relevancia": 80, "utilidad": 70, "confiabilidad": 100, "novedad": 0},
        "puntaje_final": 99,
        "nivel_memoria": "larga",
    }
    base.update(cambios)
    return base


def dejar(buzon, nombre, datos):
    ruta = buzon / f"{nombre}.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def nota_de(boveda):
    return sorted((boveda / "LLM-Memoria" / "Web").glob("*.md"))


# ------------------------------------------------------------- cálculo puro


def test_puntaje_y_niveles_del_ejemplo_del_readme():
    reglas = ingesta_web.Reglas()

    p = ingesta_web.puntaje_final({"relevancia": 80, "utilidad": 70, "confiabilidad": 90, "novedad": 60}, reglas)

    assert p == 77.0
    assert ingesta_web.nivel_para(77, reglas) == "media"
    assert [ingesta_web.nivel_para(x, reglas) for x in (85, 84.9, 70, 69.9, 50, 49.9)] == [
        "larga", "media", "media", "corta", "corta", "descartar",
    ]


def test_las_fechas_de_vigencia_coinciden_con_el_readme():
    r = ingesta_web.Reglas()

    assert ingesta_web.fecha_vigencia(HOY, "corta", r) == "2026-11-06"
    assert ingesta_web.fecha_vigencia(HOY, "media", r) == "2027-01-28"
    assert ingesta_web.fecha_vigencia(HOY, "larga", r) == "2036-10-27"


def test_confiabilidad_y_novedad_las_calcula_el_codigo(web):
    r = ingesta_web.cargar_reglas(config.cargar_config())

    assert ingesta_web.calcular_confiabilidad("https://api.github.com/x", r) == 90
    assert ingesta_web.calcular_confiabilidad("https://www.reddit.com/r/LocalLLaMA/", r) == 60
    assert ingesta_web.calcular_confiabilidad("https://blog-raro.example/x", r) == 30

    assert ingesta_web.calcular_novedad("2026-10-20", HOY, r) == 100
    assert ingesta_web.calcular_novedad("2026-08-01", HOY, r) == 80
    assert ingesta_web.calcular_novedad("2026-02-01", HOY, r) == 40
    assert ingesta_web.calcular_novedad("", HOY, r) == 50
    assert ingesta_web.calcular_novedad("2020-01-01", HOY, r) == 0


def test_normalizar_url():
    n = ingesta_web.normalizar_url

    assert n("HTTPS://www.GitHub.com/a/b/?utm_source=x#frag") == n("https://github.com/a/b")
    assert n("https://github.com/a/b?q=1") != n("https://github.com/a/b")


def test_reglas_reales_son_validas(web):
    assert ingesta_web.validar_reglas(ingesta_web.cargar_reglas(config.cargar_config())) == []


def test_reglas_invalidas_se_detectan():
    r = ingesta_web.Reglas(pesos={"relevancia": 50, "utilidad": 30, "confiabilidad": 20, "novedad": 10})
    assert any("100" in e for e in ingesta_web.validar_reglas(r))

    r = ingesta_web.Reglas(umbral_media=90)
    assert any("umbrales" in e for e in ingesta_web.validar_reglas(r))


# ---------------------------------------------------------------- ingesta


def test_publica_una_nota_valida(web):
    boveda, buzon = web
    dejar(buzon, "001", paquete())

    resumen = ingesta_web.ingerir(hoy=HOY)

    assert [p["nivel"] for p in resumen["publicados"]] == ["media"]  # n8n dijo "larga": el código recalcula
    assert resumen["publicados"][0]["puntaje"] == 81.0  # 32 + 21 + 18 + 10

    notas = nota_de(boveda)
    assert len(notas) == 1
    texto = notas[0].read_text(encoding="utf-8")

    for esperado in (
        "origen: web",
        "url_origen: https://github.com/ejemplo/agent-memory-demo",
        "fecha_consulta: 2026-10-30",
        "nivel_memoria: media",
        "puntaje: 81.0",
        "vigente_hasta: 2027-01-28",
        'objetivos: ["OBJ-002"]',  # OBJ-999 no existe: se descarta
        'titulo_original: "agent-memory-demo"',
        "confianza: 0.9",
        "[[SQLite]]",
        "[[Malformada]]",
        "## Advertencia",
    ):
        assert esperado in texto, esperado

    assert not (buzon / "001.json").exists()
    assert (buzon / "procesados" / "001.json").exists()
    assert not (boveda / "memoria_vectorial" / ".memoria" / "indice.sqlite").exists()  # n8n/ingesta no tocan SQLite


def test_la_escritura_queda_auditada_y_emite_evento(web):
    boveda, buzon = web
    dejar(buzon, "001", paquete())

    ingesta_web.ingerir(hoy=HOY)

    actores = {r["actor"] for r in leer_jsonl(boveda / "Sistema" / "auditoria.jsonl")}
    tipos = {e["tipo"] for e in leer_jsonl(boveda / "Sistema" / "eventos.jsonl")}

    assert actores == {"ingesta_web"}
    assert "ingesta_web.publicado" in tipos


def test_la_nota_se_encuentra_con_recuperacion_y_vence(web):
    """vigente_hasta es el campo que ya respeta recuperacion.py."""
    import recuperacion

    boveda, buzon = web
    dejar(buzon, "001", paquete())
    ingesta_web.ingerir(hoy=HOY)
    ruta = nota_de(boveda)[0].relative_to(boveda).as_posix()

    assert recuperacion._vigente_hasta(boveda, ruta, {}) == date(2027, 1, 28)


@pytest.mark.parametrize(
    "cambios, motivo",
    [
        ({"disparador": {"tipo": "capricho", "detalle": "x"}}, "sin_disparador_valido"),
        ({"disparador": None}, "sin_disparador_valido"),
        ({"url": "https://sitio-raro.example/post"}, "dominio_no_permitido"),
        ({"url": "ftp://github.com/x"}, "url_invalida"),
        ({"url": "https://user:pw@github.com/x"}, "url_invalida"),
        ({"resumen_es": "corto"}, "sin_resumen"),
        ({"componentes": {"relevancia": "mucha", "utilidad": 50}}, "componentes_invalidos"),
        ({"fecha_publicacion": "2020-01-01"}, "demasiado_antiguo"),
        ({"titulo_original": "", "titulo_es": ""}, "sin_titulo"),
    ],
)
def test_rechaza_paquetes_invalidos_sin_borrarlos(web, cambios, motivo):
    boveda, buzon = web
    dejar(buzon, "001", paquete(**cambios))

    resumen = ingesta_web.ingerir(hoy=HOY)

    assert resumen["publicados"] == []
    assert resumen["rechazados"][0]["motivo"] == motivo
    assert (buzon / "rechazados" / "001.json").exists()
    assert (buzon / "rechazados" / "001.json.motivo.txt").read_text(encoding="utf-8").strip() == motivo
    assert nota_de(boveda) == []


def test_json_roto_va_a_rechazados(web):
    _, buzon = web
    (buzon / "roto.json").write_text("{no es json", encoding="utf-8")

    resumen = ingesta_web.ingerir(hoy=HOY)

    assert resumen["rechazados"][0]["motivo"] == "json_invalido"
    assert (buzon / "rechazados" / "roto.json").exists()


def test_puntaje_bajo_se_descarta_y_resta_peso(web):
    boveda, buzon = web
    # sin fecha para no chocar con "demasiado_antiguo"; n8n dice confiabilidad 100 pero el código manda (github = 90)
    datos = paquete(componentes={"relevancia": 20, "utilidad": 20, "confiabilidad": 100, "novedad": 100}, fecha_publicacion="")
    dejar(buzon, "001", datos)

    resumen = ingesta_web.ingerir(hoy=HOY)

    assert resumen["publicados"] == []
    assert resumen["descartados"][0]["puntaje"] == 37.0  # 8 + 6 + 18 + 5 (novedad sin fecha = 50)
    assert nota_de(boveda) == []
    assert (buzon / "rechazados" / "001.json").exists()
    assert resumen["pesos_ajustados"]["n8n"] == -0.02

    tipos = {e["tipo"] for e in leer_jsonl(boveda / "Sistema" / "eventos.jsonl")}
    assert "ingesta_web.investigacion_no_util" in tipos


def test_duplicado_no_crea_otra_nota(web):
    boveda, buzon = web
    dejar(buzon, "001", paquete())
    ingesta_web.ingerir(hoy=HOY)

    dejar(buzon, "002", paquete(url="https://www.github.com/ejemplo/agent-memory-demo/?utm_source=x"))
    resumen = ingesta_web.ingerir(hoy=date(2026, 10, 31))

    assert resumen["publicados"] == [] and resumen["duplicados"][0]["archivo"] == "002.json"
    assert len(nota_de(boveda)) == 1


def test_el_mismo_ciclo_tampoco_duplica(web):
    boveda, buzon = web
    dejar(buzon, "001", paquete())
    dejar(buzon, "002", paquete())

    resumen = ingesta_web.ingerir(hoy=HOY)

    assert len(resumen["publicados"]) == 1 and len(resumen["duplicados"]) == 1
    assert len(nota_de(boveda)) == 1


def test_tope_por_ciclo_publica_los_mejores(web):
    boveda, buzon = web
    dejar(buzon, "a", paquete(url="https://github.com/x/a", titulo_es="Nota A", componentes={"relevancia": 60, "utilidad": 60, "confiabilidad": 0, "novedad": 0}))
    dejar(buzon, "b", paquete(url="https://github.com/x/b", titulo_es="Nota B", componentes={"relevancia": 95, "utilidad": 95, "confiabilidad": 0, "novedad": 0}))

    resumen = ingesta_web.ingerir(hoy=HOY, max_guardados=1)

    assert [p["titulo"] for p in resumen["publicados"]] == ["Nota B"]
    assert resumen["rechazados"][0]["motivo"] == "tope_por_ciclo"
    assert (buzon / "rechazados" / "a.json").exists()


def test_titulos_iguales_con_urls_distintas_no_se_pisan(web):
    boveda, buzon = web
    dejar(buzon, "a", paquete(url="https://github.com/x/a"))
    dejar(buzon, "b", paquete(url="https://github.com/x/b"))

    ingesta_web.ingerir(hoy=HOY)

    assert len(nota_de(boveda)) == 2


def test_dry_run_no_escribe_nada(web):
    boveda, buzon = web
    dejar(buzon, "001", paquete())

    resumen = ingesta_web.ingerir(hoy=HOY, dry_run=True)

    assert len(resumen["publicados"]) == 1
    assert (buzon / "001.json").exists()
    assert nota_de(boveda) == []
    assert not (boveda / "memoria_vectorial" / ".memoria" / "aprendizaje_web.json").exists()


# ------------------------------------------------------- pesos y propuestas


def test_pesos_efectivos_suben_con_hallazgos_utiles(web):
    cfg = config.cargar_config()
    dejar(web[1], "001", paquete())  # tags incluyen "n8n"

    resumen = ingesta_web.ingerir(hoy=HOY)

    assert resumen["pesos_ajustados"]["n8n"] == 0.05
    assert ingesta_web.pesos_efectivos(cfg)["n8n"] == 1.05
    assert ingesta_web.pesos_efectivos(cfg)["MCP"] == 0.95  # sin hallazgos, sin cambio

    # y Perfil/ no se toca
    base = json.loads((web[0] / "Perfil" / "intereses.json").read_text(encoding="utf-8"))
    assert base["pesos"]["n8n"] == 1.0


def test_pesos_respetan_los_limites(web):
    cfg = config.cargar_config()
    estado = ingesta_web.leer_estado(cfg)
    estado["deltas_pesos"] = {"n8n": 5.0, "seo": -9.0}

    pesos = ingesta_web.pesos_efectivos(cfg, estado)

    assert pesos["n8n"] == 2.0 and pesos["SEO"] == 0.1


def test_progreso_de_objetivos_se_guarda_aparte(web):
    cfg = config.cargar_config()
    dejar(web[1], "001", paquete())

    ingesta_web.ingerir(hoy=HOY)

    assert ingesta_web.leer_estado(cfg)["progreso_auto"] == {"OBJ-002": 1.0}
    base = json.loads((web[0] / "Perfil" / "objetivos.json").read_text(encoding="utf-8"))
    assert base["objetivos"][1]["progreso"] == 0


def test_propuesta_de_interes_nuevo_requiere_dos_evidencias(web):
    boveda, buzon = web
    dejar(buzon, "a", paquete(url="https://github.com/x/a", temas_nuevos=["Qdrant", "Ollama", "contenido spam"]))

    ingesta_web.ingerir(hoy=HOY)
    nota = boveda / "LLM-Memoria" / "Revision" / "propuestas-web.md"
    assert "Sin propuestas pendientes" in nota.read_text(encoding="utf-8")

    dejar(buzon, "b", paquete(url="https://github.com/x/b", temas_nuevos=["Qdrant"]))
    ingesta_web.ingerir(hoy=HOY)
    texto = nota.read_text(encoding="utf-8")

    assert "**Qdrant** — 2 hallazgos" in texto
    assert "Ollama" not in texto and "spam" not in texto  # ya es interés / está en "evitar"


def test_rechazar_propuesta(web):
    boveda, buzon = web
    for n in "ab":
        dejar(buzon, n, paquete(url=f"https://github.com/x/{n}", temas_nuevos=["Qdrant"]))

    ingesta_web.ingerir(hoy=HOY)

    assert ingesta_web.rechazar_propuesta("qdrant") is True
    assert ingesta_web.rechazar_propuesta("no existe") is False

    dejar(buzon, "c", paquete(url="https://github.com/x/c", temas_nuevos=["Qdrant"]))
    ingesta_web.ingerir(hoy=HOY)

    assert "Qdrant" not in (boveda / "LLM-Memoria" / "Revision" / "propuestas-web.md").read_text(encoding="utf-8")


# ------------------------------------------------------------ mantenimiento


def test_promueve_corta_a_media_tras_dos_noches_buenas(web):
    boveda, buzon = web
    flojo = {"relevancia": 50, "utilidad": 50, "confiabilidad": 0, "novedad": 0}
    bueno = {"relevancia": 90, "utilidad": 90, "confiabilidad": 0, "novedad": 0}
    url = "https://www.reddit.com/r/LocalLLaMA/comments/abc"

    dejar(buzon, "n1", paquete(url=url, componentes=flojo))
    r1 = ingesta_web.ingerir(hoy=date(2026, 10, 30))
    assert r1["publicados"][0]["nivel"] == "corta"
    ruta = r1["publicados"][0]["nota"]

    dejar(buzon, "n2", paquete(url=url, componentes=bueno))
    ingesta_web.ingerir(hoy=date(2026, 10, 31))
    assert ingesta_web.mantenimiento(hoy=date(2026, 10, 31))["promovidas"] == []  # solo 1 noche buena

    dejar(buzon, "n3", paquete(url=url, componentes=bueno))
    ingesta_web.ingerir(hoy=date(2026, 11, 1))
    seco = ingesta_web.mantenimiento(hoy=date(2026, 11, 1), dry_run=True)
    assert seco["promovidas"] == [{"nota": ruta, "de": "corta", "a": "media"}]
    assert "nivel_memoria: corta" in (boveda / ruta).read_text(encoding="utf-8")

    real = ingesta_web.mantenimiento(hoy=date(2026, 11, 1))
    texto = (boveda / ruta).read_text(encoding="utf-8")

    assert len(real["promovidas"]) == 1
    assert "nivel_memoria: media" in texto and "vigente_hasta: 2027-01-30" in texto
    assert texto.count("nivel_memoria:") == 1  # se reemplaza, no se duplica
    assert ingesta_web.mantenimiento(hoy=date(2026, 11, 2))["promovidas"] == []  # no se repite


def test_cuenta_notas_vencidas_sin_tocarlas(web):
    boveda, buzon = web
    dejar(buzon, "001", paquete(componentes={"relevancia": 50, "utilidad": 50, "confiabilidad": 0, "novedad": 0}))
    ingesta_web.ingerir(hoy=HOY)
    antes = nota_de(boveda)[0].read_text(encoding="utf-8")

    res = ingesta_web.mantenimiento(hoy=date(2027, 1, 1))

    assert res["vencidas"] == 1
    assert nota_de(boveda)[0].read_text(encoding="utf-8") == antes


# -------------------------------------------------------------------- CLI


def test_contexto_para_el_planificador(web):
    dejar(web[1], "001", paquete())
    ingesta_web.ingerir(hoy=HOY)

    ctx = ingesta_web.contexto()

    assert ctx["pesos_efectivos"]["n8n"] == 1.05
    assert [o["id"] for o in ctx["objetivos_activos"]] == [f"OBJ-00{n}" for n in range(1, 6)]
    assert "mcp" in ctx["keywords"] and "github.com" in ctx["dominios_permitidos"]
    assert ctx["urls_vistas"] == ["https://github.com/ejemplo/agent-memory-demo"]
    assert ctx["max_antiguedad_dias"] == 365
    json.dumps(ctx)  # serializable


def test_cli_check_y_salida_ascii(web, capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["ingesta_web.py", "--check"])
    assert ingesta_web.main() == 0
    salida = json.loads(capsys.readouterr().out)

    assert salida["umbrales"] == {"larga": 85.0, "media": 70.0, "corta": 50.0}
    assert salida["pesos"] == {"relevancia": 40.0, "utilidad": 30.0, "confiabilidad": 20.0, "novedad": 10.0}
    assert salida["errores"] == [] and salida["pendientes"] == 0

    dejar(web[1], "001", paquete(titulo_es="Guía de configuración para agentes"))
    monkeypatch.setattr("sys.argv", ["ingesta_web.py", "--ingerir"])
    assert ingesta_web.main() == 0
    bruto = capsys.readouterr().out

    assert bruto.isascii() and "\\u00ed" in bruto  # "í" viaja escapada: seguro para la consola de Windows
    assert json.loads(bruto)["publicados"][0]["titulo"] == "Guía de configuración para agentes"
