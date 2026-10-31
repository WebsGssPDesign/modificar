from datetime import date

import memoria
import recuperacion
from memoria import Resultado


def _r(ruta, titulo, encabezado, score):
    return Resultado(
        chunk_id=ruta, ruta=ruta, titulo=titulo, encabezado=encabezado,
        contenido="x", score=score, metodo="hibrido", rank_fts=1, rank_vec=1,
    )


def test_filtro_por_ambito(boveda, escribir_nota, embeddings_falsos):
    escribir_nota(boveda, "Notas/a.md", "# A\nredes y protocolos\n")
    escribir_nota(boveda, "LLM-Memoria/Hechos/b.md", "# B\nredes aprendidas\n")
    memoria.indexar_boveda()

    solo = recuperacion.buscar("redes", ambitos=["LLM-Memoria"], k=5)

    assert solo and all(r.ruta.startswith("LLM-Memoria/") for r in solo)


def test_excluye_notas_vencidas(boveda, escribir_nota, embeddings_falsos):
    escribir_nota(boveda, "Notas/vieja.md", "---\nvigente_hasta: 2020-01-01\n---\n# Vieja\nredes\n")
    escribir_nota(boveda, "Notas/nueva.md", "---\nvigente_hasta: 2999-01-01\n---\n# Nueva\nredes\n")
    memoria.indexar_boveda()

    normal = recuperacion.buscar("redes", k=5, hoy=date(2026, 10, 25))
    todo = recuperacion.buscar("redes", k=5, hoy=date(2026, 10, 25), incluir_vencidos=True)

    assert {r.ruta for r in normal} == {"Notas/nueva.md"}
    assert {r.ruta for r in todo} == {"Notas/nueva.md", "Notas/vieja.md"}


def test_rerank_sube_coincidencias_en_titulo():
    a = _r("a", "Cocina", "Recetas", 0.020)
    b = _r("b", "Redes", "Protocolos", 0.018)

    orden = recuperacion.reordenar("protocolos de redes", [a, b])

    assert [r.ruta for r in orden] == ["b", "a"]


def test_ambito_no_confunde_prefijos_parciales():
    assert recuperacion._en_ambito("Notas/a.md", ["Notas"])
    assert not recuperacion._en_ambito("NotasViejas/a.md", ["Notas"])
    assert recuperacion._en_ambito("cualquiera.md", [])
