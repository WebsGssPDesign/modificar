import json

import escritor

from conftest import leer_jsonl


def test_crear_editar_eliminar_deja_auditoria(boveda):
    import config

    r = escritor.crear_nota("Mi nota", "contenido original", carpeta="Notas")
    assert r.ok and r.ruta.exists()

    e = escritor.editar_nota("Notas/mi-nota.md", "original", "editado")
    assert e.ok and "editado" in r.ruta.read_text(encoding="utf-8")
    assert e.backup is not None and e.backup.exists()  # editar crea .bak

    d = escritor.eliminar_nota("Notas/mi-nota.md")
    assert d.ok and not r.ruta.exists()
    assert any(p.name.startswith("mi-nota") for p in config.cargar_config().papelera_path.rglob("*"))

    operaciones = [x["operacion"] for x in leer_jsonl(config.cargar_config().auditoria_path)]
    assert operaciones == ["crear", "editar", "eliminar"]


def test_no_sobrescribe_por_defecto(boveda):
    escritor.crear_nota("Nota", "uno", carpeta="Notas")

    segunda = escritor.crear_nota("Nota", "dos", carpeta="Notas")

    assert not segunda.ok


def test_rechaza_rutas_fuera_de_la_boveda(boveda):
    import pytest

    with pytest.raises(Exception):
        escritor.editar_nota("../fuera.md", "a", "b")


def test_actualizar_frontmatter_conserva_cuerpo(boveda):
    r = escritor.crear_nota("Nota", "cuerpo intacto", carpeta="Notas")

    a = escritor.actualizar_frontmatter(
        "Notas/nota.md", {"repasar": "2026-01-01", "aliases": ["Alias"]}, backup=False
    )
    texto = r.ruta.read_text(encoding="utf-8")

    assert a.ok
    assert "repasar: 2026-01-01" in texto
    assert 'aliases: ["Alias"]' in texto
    assert texto.rstrip().endswith("cuerpo intacto")


def test_actualizar_frontmatter_reemplaza_clave_existente(boveda):
    escritor.crear_nota("Nota", "x", carpeta="Notas")
    escritor.actualizar_frontmatter("Notas/nota.md", {"estado": "revisada"}, backup=False)

    texto = (boveda / "Notas/nota.md").read_text(encoding="utf-8")

    assert texto.count("estado:") == 1
    assert "estado: revisada" in texto


def test_actualizar_frontmatter_en_nota_sin_frontmatter(boveda, escribir_nota):
    escribir_nota(boveda, "Notas/plana.md", "solo texto\n")

    escritor.actualizar_frontmatter("Notas/plana.md", {"repasar": "2026-01-01"}, backup=False)

    assert (boveda / "Notas/plana.md").read_text(encoding="utf-8").startswith("---\nrepasar:")


def test_escribir_json_auditado(boveda):
    r = escritor.escribir_json_auditado("Perfil/x.json", {"a": 1}, actor="test")

    assert json.loads(r.ruta.read_text(encoding="utf-8")) == {"a": 1}
    again = escritor.escribir_json_auditado("Perfil/x.json", {"a": 1}, actor="test")
    assert again.mensaje == "Sin cambios"


def test_escribir_json_solo_acepta_json(boveda):
    import pytest

    with pytest.raises(ValueError):
        escritor.escribir_json_auditado("Perfil/x.md", {"a": 1})
