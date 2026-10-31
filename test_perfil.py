import perfil


def test_asegurar_crea_los_json():
    perfil.asegurar()
    assert (perfil.config.PERFIL / "perfil_usuario.json").exists()
    assert (perfil.config.PERFIL / "intereses.json").exists()
    assert (perfil.config.PERFIL / "objetivos.json").exists()


def test_no_sobrescribe_lo_editado():
    perfil.asegurar()
    ruta = perfil.config.PERFIL / "intereses.json"
    original = ruta.read_text(encoding="utf-8")
    perfil.asegurar()
    assert ruta.read_text(encoding="utf-8") == original


def test_contexto_incluye_stack():
    ctx = perfil.como_contexto()
    assert "HTML5" in ctx and "Reglas de inferencia" in ctx


def test_relevancia_ordena_bien():
    assert perfil.puntuar_relevancia("como hacer una web con react y next") > \
           perfil.puntuar_relevancia("recetas de cocina vegana")
