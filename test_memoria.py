import os
import time

import memoria
from util import proceso_vivo


def test_chunk_text_no_pierde_nada():
    texto = "palabra " * 900
    trozos = memoria.chunk_text(texto, markdown=True)
    assert "".join(t.strip() for t in trozos).count("palabra") == 900


def test_chunk_text_respeta_bloques_de_codigo():
    texto = "# titulo\n\n```python\nx = 1  # no es encabezado\n```\n\nmas texto"
    trozos = memoria.chunk_text(texto, markdown=True)
    assert any("no es encabezado" in t for t in trozos)


def test_formatear_trunca():
    largos = [{"ruta": f"n{i}.md", "texto": "x" * 3000, "score": 0.9} for i in range(6)]
    salida = memoria.formatear(largos)
    assert len(salida) <= memoria.MAX_CARACTERES_TOTAL + 400
    assert "[...]" in salida


def test_lock_propio_y_ajeno():
    assert memoria._acquire_lock() is True
    assert memoria._lock_es_nuestro() is True
    assert memoria._acquire_lock() is False
    memoria._release_lock()
    assert not memoria.LOCK_PATH.exists()


def test_lock_no_se_libera_si_es_de_otro():
    memoria.LOCK_PATH.write_text("999999 1.0", encoding="ascii")
    memoria._release_lock()
    assert memoria.LOCK_PATH.exists()
    memoria.LOCK_PATH.unlink()


def test_lock_viejo_de_proceso_muerto_se_roba():
    memoria.LOCK_PATH.write_text("999999 1.0", encoding="ascii")
    viejo = time.time() - memoria.LOCK_STALE_SECONDS - 10
    os.utime(memoria.LOCK_PATH, (viejo, viejo))
    assert memoria._acquire_lock() is True
    memoria._release_lock()


def test_lock_viejo_con_duenno_vivo_no_se_roba():
    memoria.LOCK_PATH.write_text(f"{os.getpid()} 1.0", encoding="ascii")
    viejo = time.time() - memoria.LOCK_STALE_SECONDS - 10
    os.utime(memoria.LOCK_PATH, (viejo, viejo))
    assert proceso_vivo(os.getpid())
    assert memoria._acquire_lock() is False
    memoria.LOCK_PATH.unlink()


def test_contadores_son_por_ventana():
    memoria.contador_sumar("prueba.hora", 3)
    assert memoria.contador_leer("prueba.hora") == 3
