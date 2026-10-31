import json
import zipfile
from datetime import date

import backup
import config
import memoria


def _bóveda_con_datos(boveda, escribir_nota, embeddings_falsos):
    escribir_nota(boveda, "Notas/a.md", "# A\ntexto sobre redes\n")
    escribir_nota(boveda, "LLM-Memoria/Hechos/h.md", "# H\nhecho\n")
    escribir_nota(boveda, "Perfil/intereses.json", "[]")
    memoria.indexar_boveda()


def test_crear_y_verificar(boveda, escribir_nota, embeddings_falsos):
    _bóveda_con_datos(boveda, escribir_nota, embeddings_falsos)

    resultado = backup.crear_backup()
    verif = backup.verificar_backup()

    assert resultado["chunks"] > 0
    assert verif["ok"] is True
    assert verif["integridad_sqlite"] == "ok"
    assert verif["chunks"] == verif["chunks_esperados"]


def test_el_backup_no_incluye_backups_ni_bak(boveda, escribir_nota, embeddings_falsos):
    _bóveda_con_datos(boveda, escribir_nota, embeddings_falsos)
    escribir_nota(boveda, "LLM-Memoria/Hechos/h.md.2026.bak", "viejo")
    backup.crear_backup()

    archivo = backup.listar_backups()[-1]
    nombres = zipfile.ZipFile(archivo).namelist()

    assert not any(n.endswith(".bak") for n in nombres)
    assert not any("/backups/" in n for n in nombres)
    assert "indice/indice.sqlite" in nombres and "manifest.json" in nombres


def test_verificar_detecta_corrupcion(boveda, escribir_nota, embeddings_falsos, tmp_path):
    _bóveda_con_datos(boveda, escribir_nota, embeddings_falsos)
    backup.crear_backup()
    original = backup.listar_backups()[-1]

    adulterado = tmp_path / "adulterado.zip"

    with zipfile.ZipFile(original) as src, zipfile.ZipFile(adulterado, "w") as dst:
        for item in src.infolist():
            datos = src.read(item.filename)

            if item.filename.endswith("h.md"):
                datos = b"CONTENIDO ALTERADO"

            dst.writestr(item.filename, datos)

    verif = backup.verificar_backup(adulterado)

    assert verif["ok"] is False
    assert any(n.endswith("h.md") for n in verif["corruptos"])


def test_restaurar_no_toca_la_boveda(boveda, escribir_nota, embeddings_falsos, tmp_path):
    _bóveda_con_datos(boveda, escribir_nota, embeddings_falsos)
    backup.crear_backup()
    nota = boveda / "Notas/a.md"
    nota.write_text("# CAMBIADA\n", encoding="utf-8")

    destino = tmp_path / "restauracion"
    resultado = backup.restaurar_backup(backup.listar_backups()[-1], destino)

    assert resultado["ok"] is True
    assert (destino / "datos/LLM-Memoria/Hechos/h.md").exists()
    assert (destino / "indice/indice.sqlite").exists()
    assert nota.read_text(encoding="utf-8") == "# CAMBIADA\n"  # la bóveda sigue intacta


def test_restaurar_rechaza_destino_con_contenido(boveda, escribir_nota, embeddings_falsos, tmp_path):
    import pytest

    _bóveda_con_datos(boveda, escribir_nota, embeddings_falsos)
    backup.crear_backup()
    (tmp_path / "ocupado").mkdir()
    (tmp_path / "ocupado" / "x.txt").write_text("x")

    with pytest.raises(backup.ErrorBackup):
        backup.restaurar_backup(backup.listar_backups()[-1], tmp_path / "ocupado")


def test_poda_conserva_diario_semanal_mensual():
    nombres = [
        "backup-20261025-100000.zip",  # hoy
        "backup-20261025-020000.zip",  # hoy, más antiguo -> se elimina
        "backup-20261024-100000.zip",
        "backup-20261015-100000.zip",
        "backup-20260901-100000.zip",
        "backup-20250101-100000.zip",  # muy viejo -> se elimina
    ]
    retencion = {"diarios": 7, "semanales": 4, "mensuales": 6}

    conservar, eliminar = backup.calcular_poda(nombres, retencion, hoy=date(2026, 10, 25))

    assert "backup-20261025-100000.zip" in conservar
    assert "backup-20261025-020000.zip" in eliminar
    assert "backup-20250101-100000.zip" in eliminar
    assert "backup-20260901-100000.zip" in conservar  # mensual


def test_poda_nunca_deja_sin_backups():
    conservar, eliminar = backup.calcular_poda(
        ["backup-20200101-000000.zip"], {"diarios": 1, "semanales": 0, "mensuales": 0}, hoy=date(2026, 10, 25)
    )

    assert conservar == ["backup-20200101-000000.zip"]
    assert eliminar == []


def test_dry_run_no_escribe(boveda, escribir_nota, embeddings_falsos):
    _bóveda_con_datos(boveda, escribir_nota, embeddings_falsos)

    resultado = backup.crear_backup(dry_run=True)

    assert resultado["destino"] is None
    assert backup.listar_backups() == []
