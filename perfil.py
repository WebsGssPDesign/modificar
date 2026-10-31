"""
perfil.py — Perfil persistente del usuario (intereses y objetivos).

Archivos (en la bóveda, carpeta Perfil/):
    perfil_usuario.json   datos generales (nombre, rol, stack, reglas libres)
    intereses.json        formato viejo: [{"nombre", "peso" 1-5}]
                          formato nuevo: {"principales", "secundarios", "pesos" 0.1-2.0, ...}
    objetivos.json        formato viejo: [{"id": "o1", "texto", "prioridad", "estado", "creado"}]
                          formato nuevo: {"objetivos": [{"id": "OBJ-001", "nombre",
                                          "prioridad" 0-10, "estado", "progreso"}], ...}
                          Se respeta el formato del archivo al guardar y se conservan
                          los campos que el CLI no gestiona (progreso, criterios_exito...).
    perfil-usuario.md    vista legible para Obsidian (se regenera sola)

Quién lo lee:
    analisis.py     intereses.json  -> huecos de conocimiento
    aprender.py     perfil_usuario.json -> contexto del LLM
    mcp_server.py   herramienta `perfil`

Principio: el perfil lo decide el humano. Ningún LLM modifica estos archivos;
todo cambio pasa por este CLI y por escritor.py (con auditoría).

Uso:
    python perfil.py --init --nombre "Ana" --rol "Estudiante" --stack python,sql
    python perfil.py --mostrar
    python perfil.py --set rol="Backend junior"
    python perfil.py --interes-add "Machine Learning" --peso 5
    python perfil.py --interes-del "Machine Learning"
    python perfil.py --objetivo-add "Aprobar SQL avanzado" --prioridad alta
    python perfil.py --objetivo-estado o1 hecho
    python perfil.py --objetivo-del o1
    python perfil.py --regenerar
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from config import cargar_config, preparar_carpetas
from escritor import crear_nota, escribir_json_auditado
from util import leer_json, timestamp_iso

PRIORIDADES = ("alta", "media", "baja")
ESTADOS = ("activo", "pausado", "hecho")
ACTOR = "perfil"

# Prioridad numérica (formato nuevo de objetivos.json) <-> etiqueta (CLI).
PRIORIDAD_NUM = {"alta": 10, "media": 5, "baja": 2}

PESO_DEFECTO_PRINCIPALES = 0.8
PESO_DEFECTO_SECUNDARIOS = 0.5
PESO_MIN_DEFECTO = 0.1
PESO_MAX_DEFECTO = 2.0


# ---------------------------------------------------------------- formatos
#
# Se admiten dos formatos de intereses.json y de objetivos.json:
#
#   viejo   intereses: [{"nombre", "peso" 1-5}]      objetivos: [{"id": "o1", "texto", ...}]
#   nuevo   intereses: {"principales", "secundarios", "pesos" 0.1-2.0, "aprendizaje", ...}
#           objetivos: {"objetivos": [{"id": "OBJ-001", "nombre", "prioridad": 10, "progreso"}], ...}
#
# El CLI trabaja siempre con una vista normalizada y, al guardar, respeta el formato
# del archivo (y conserva los campos que no gestiona, como `progreso` o `criterios_exito`).


def _intereses_formato_nuevo(raw: Any) -> bool:
    return isinstance(raw, dict) and any(k in raw for k in ("principales", "secundarios", "pesos"))


def _objetivos_formato_nuevo(raw: Any) -> bool:
    return isinstance(raw, dict) and isinstance(raw.get("objetivos"), list)


def _etiqueta_prioridad(valor: Any) -> str:
    if isinstance(valor, str):
        return valor if valor in PRIORIDADES else "media"

    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return "media"

    if numero >= 9:
        return "alta"

    return "media" if numero >= 5 else "baja"


def _parametros_peso(raw: Any) -> tuple[float, float, float, float]:
    """(defecto principales, defecto secundarios, mínimo, máximo) del formato nuevo."""
    aprendizaje = raw.get("aprendizaje", {}) if isinstance(raw, dict) else {}

    def _f(clave: str, defecto: float) -> float:
        try:
            return float(aprendizaje.get(clave, defecto))
        except (TypeError, ValueError):
            return defecto

    return (
        _f("peso_defecto_principales", PESO_DEFECTO_PRINCIPALES),
        _f("peso_defecto_secundarios", PESO_DEFECTO_SECUNDARIOS),
        _f("peso_minimo", PESO_MIN_DEFECTO),
        _f("peso_maximo", PESO_MAX_DEFECTO),
    )


def _normalizar_intereses(raw: Any) -> list[dict[str, Any]]:
    normalizados: list[dict[str, Any]] = []

    if _intereses_formato_nuevo(raw):
        defecto_p, defecto_s, _, _ = _parametros_peso(raw)
        pesos = {str(k).strip().lower(): v for k, v in (raw.get("pesos") or {}).items()}
        vistos: set[str] = set()

        for lista, defecto in ((raw.get("principales"), defecto_p), (raw.get("secundarios"), defecto_s)):
            for nombre in lista or []:
                nombre = str(nombre).strip()

                if not nombre or nombre.lower() in vistos:
                    continue

                vistos.add(nombre.lower())

                try:
                    peso = float(pesos.get(nombre.lower(), defecto))
                except (TypeError, ValueError):
                    peso = defecto

                normalizados.append({"nombre": nombre, "peso": peso})

        return normalizados

    lista = raw.get("intereses", []) if isinstance(raw, dict) else raw

    for item in lista or []:
        if isinstance(item, str) and item.strip():
            normalizados.append({"nombre": item.strip(), "peso": 3})
        elif isinstance(item, dict) and str(item.get("nombre", "")).strip():
            normalizados.append(
                {"nombre": str(item["nombre"]).strip(), "peso": int(item.get("peso", 3))}
            )

    return normalizados


def _normalizar_objetivos(raw: Any) -> list[dict[str, Any]]:
    if _objetivos_formato_nuevo(raw):
        salida = []

        for o in raw["objetivos"]:
            if not isinstance(o, dict):
                continue

            copia = dict(o)
            copia["texto"] = str(o.get("texto") or o.get("nombre") or "").strip()
            copia["prioridad"] = _etiqueta_prioridad(o.get("prioridad", "media"))
            salida.append(copia)

        return salida

    lista = raw.get("objetivos", []) if isinstance(raw, dict) else raw
    return [o for o in (lista or []) if isinstance(o, dict)]


def _serializar_intereses(raw: Any, normalizados: list[dict[str, Any]]) -> Any:
    if not _intereses_formato_nuevo(raw):
        return normalizados

    defecto_p, defecto_s, _, _ = _parametros_peso(raw)
    salida = dict(raw)
    vigentes = {i["nombre"].lower(): i for i in normalizados}

    principales = [n for n in raw.get("principales", []) if str(n).strip().lower() in vigentes]
    secundarios = [n for n in raw.get("secundarios", []) if str(n).strip().lower() in vigentes]
    conocidos = {str(n).strip().lower() for n in principales + secundarios}

    for i in normalizados:
        if i["nombre"].lower() not in conocidos:
            principales.append(i["nombre"])
            conocidos.add(i["nombre"].lower())

    pesos = dict(raw.get("pesos") or {})
    claves = {str(k).strip().lower(): k for k in pesos}
    en_secundarios = {str(n).strip().lower() for n in secundarios}

    for baja in [k for k in claves if k not in vigentes and k in {
        str(n).strip().lower() for n in raw.get("principales", []) + raw.get("secundarios", [])
    }]:
        pesos.pop(claves[baja], None)

    for i in normalizados:
        clave_baja = i["nombre"].lower()
        defecto = defecto_s if clave_baja in en_secundarios else defecto_p
        existente = claves.get(clave_baja)

        if existente is not None:
            pesos[existente] = i["peso"]
        elif abs(float(i["peso"]) - defecto) > 1e-9:
            pesos[i["nombre"]] = i["peso"]

    salida["principales"] = principales
    salida["secundarios"] = secundarios
    salida["pesos"] = pesos
    return salida


def _serializar_objetivos(raw: Any, normalizados: list[dict[str, Any]]) -> Any:
    if not _objetivos_formato_nuevo(raw):
        return normalizados

    previos = {str(o.get("id")): o for o in raw["objetivos"] if isinstance(o, dict)}
    lista = []

    for o in normalizados:
        base = dict(previos.get(str(o.get("id")), {}))
        extra = {k: v for k, v in o.items() if k not in {"texto", "prioridad"}}
        base.update(extra)
        base["nombre"] = o.get("texto") or base.get("nombre", "")

        etiqueta_previa = _etiqueta_prioridad(base.get("prioridad", "media"))
        etiqueta_nueva = _etiqueta_prioridad(o.get("prioridad", "media"))

        if "prioridad" not in base or etiqueta_nueva != etiqueta_previa:
            base["prioridad"] = PRIORIDAD_NUM[etiqueta_nueva]

        base.setdefault("progreso", 0)
        lista.append(base)

    salida = dict(raw)
    salida["objetivos"] = lista
    return salida


# ---------------------------------------------------------------- lectura


def _rel(config, nombre: str) -> str:
    return (config.perfil / nombre).relative_to(config.boveda).as_posix()


def cargar() -> dict[str, Any]:
    config = cargar_config()
    perfil = leer_json(config.perfil / "perfil_usuario.json", {}) or {}
    intereses_raw = leer_json(config.perfil / "intereses.json", []) or []
    objetivos_raw = leer_json(config.perfil / "objetivos.json", []) or []

    return {
        "perfil": perfil if isinstance(perfil, dict) else {},
        "intereses": _normalizar_intereses(intereses_raw),
        "objetivos": _normalizar_objetivos(objetivos_raw),
        # Contenido original de los archivos: sirve para guardar respetando su formato.
        "_intereses_raw": intereses_raw,
        "_objetivos_raw": objetivos_raw,
    }


# -------------------------------------------------------------- escritura


def _guardar(datos: dict[str, Any], motivo: str) -> None:
    config = cargar_config()
    preparar_carpetas(config)
    config.perfil.mkdir(parents=True, exist_ok=True)

    contenidos = (
        ("perfil_usuario.json", datos["perfil"]),
        ("intereses.json", _serializar_intereses(datos.get("_intereses_raw", []), datos["intereses"])),
        ("objetivos.json", _serializar_objetivos(datos.get("_objetivos_raw", []), datos["objetivos"])),
    )

    for nombre, contenido in contenidos:
        escribir_json_auditado(_rel(config, nombre), contenido, actor=ACTOR, motivo=motivo)

    regenerar_markdown(datos)


def render_markdown(datos: dict[str, Any]) -> str:
    perfil = datos["perfil"]
    lineas = ["## Datos generales", ""]

    if perfil:
        for clave, valor in perfil.items():
            if isinstance(valor, list):
                valor = ", ".join(str(v) for v in valor)
            lineas.append(f"- **{clave}**: {valor}")
    else:
        lineas.append("- Sin datos todavía.")

    lineas += ["", "## Intereses", ""]

    if datos["intereses"]:
        for i in sorted(datos["intereses"], key=lambda x: (-x["peso"], x["nombre"].lower())):
            lineas.append(f"- {i['nombre']} (peso {i['peso']})")
    else:
        lineas.append("- Ninguno.")

    lineas += ["", "## Objetivos", ""]

    if datos["objetivos"]:
        for o in datos["objetivos"]:
            marca = "x" if o.get("estado") == "hecho" else " "
            lineas.append(
                f"- [{marca}] `{o.get('id')}` {o.get('texto')} "
                f"(prioridad {o.get('prioridad', 'media')}, {o.get('estado', 'activo')})"
            )
    else:
        lineas.append("- Ninguno.")

    lineas += ["", f"_Generado por perfil.py el {timestamp_iso()}. No editar a mano: usa el CLI._"]
    return "\n".join(lineas) + "\n"


def regenerar_markdown(datos: dict[str, Any] | None = None) -> str:
    datos = datos or cargar()
    config = cargar_config()
    carpeta = config.perfil.relative_to(config.boveda).as_posix()

    resultado = crear_nota(
        "Perfil usuario",
        render_markdown(datos),
        carpeta=carpeta,
        tags=["perfil"],
        fuente="perfil",
        confianza=1.0,
        actor=ACTOR,
        motivo="vista_perfil",
        sobrescribir=True,
    )

    if not resultado.ok:
        raise RuntimeError(resultado.mensaje)

    return str(resultado.ruta)


# ------------------------------------------------------------- operaciones


def inicializar(
    *, nombre: str | None = None, rol: str | None = None, stack: list[str] | None = None
) -> dict[str, Any]:
    datos = cargar()

    if nombre:
        datos["perfil"]["nombre"] = nombre
    if rol:
        datos["perfil"]["rol"] = rol
    if stack:
        datos["perfil"]["stack"] = stack

    datos["perfil"].setdefault("creado", timestamp_iso())
    _guardar(datos, "init")
    return datos


def fijar(clave: str, valor: str) -> dict[str, Any]:
    clave = clave.strip()

    if not clave:
        raise ValueError("La clave no puede estar vacía")

    datos = cargar()
    datos["perfil"][clave] = [v.strip() for v in valor.split(",")] if "," in valor else valor
    _guardar(datos, "set")
    return datos


def agregar_interes(nombre: str, peso: float | None = None) -> dict[str, Any]:
    nombre = nombre.strip()

    if not nombre:
        raise ValueError("El interés no puede estar vacío")

    datos = cargar()

    if _intereses_formato_nuevo(datos["_intereses_raw"]):
        defecto_p, _, minimo, maximo = _parametros_peso(datos["_intereses_raw"])
        peso = defecto_p if peso is None else float(peso)

        if not minimo <= peso <= maximo:
            raise ValueError(f"El peso debe estar entre {minimo} y {maximo}")
    else:
        peso = 3 if peso is None else peso

        if not 1 <= peso <= 5:
            raise ValueError("El peso debe estar entre 1 y 5")

        peso = int(peso)

    for i in datos["intereses"]:
        if i["nombre"].lower() == nombre.lower():
            i["peso"] = peso
            break
    else:
        datos["intereses"].append({"nombre": nombre, "peso": peso})

    _guardar(datos, "interes_add")
    return datos


def quitar_interes(nombre: str) -> dict[str, Any]:
    datos = cargar()
    antes = len(datos["intereses"])
    datos["intereses"] = [
        i for i in datos["intereses"] if i["nombre"].lower() != nombre.strip().lower()
    ]

    if len(datos["intereses"]) == antes:
        raise KeyError(f"No existe el interés: {nombre}")

    _guardar(datos, "interes_del")
    return datos


def _siguiente_id(objetivos: list[dict[str, Any]], *, formato_nuevo: bool = False) -> str:
    if formato_nuevo:
        numeros_nuevo = [
            int(str(o["id"])[4:])
            for o in objetivos
            if str(o.get("id", "")).upper().startswith("OBJ-") and str(o["id"])[4:].isdigit()
        ]
        return f"OBJ-{max(numeros_nuevo, default=0) + 1:03d}"

    numeros = [
        int(o["id"][1:])
        for o in objetivos
        if str(o.get("id", "")).startswith("o") and str(o["id"])[1:].isdigit()
    ]
    return f"o{max(numeros, default=0) + 1}"


def agregar_objetivo(texto: str, prioridad: str = "media") -> dict[str, Any]:
    texto = texto.strip()

    if not texto:
        raise ValueError("El objetivo no puede estar vacío")

    if prioridad not in PRIORIDADES:
        raise ValueError(f"Prioridad inválida; usa {PRIORIDADES}")

    datos = cargar()
    nuevo = _objetivos_formato_nuevo(datos["_objetivos_raw"])
    datos["objetivos"].append(
        {
            "id": _siguiente_id(datos["objetivos"], formato_nuevo=nuevo),
            "texto": texto,
            "prioridad": prioridad,
            "estado": "activo",
            "creado": timestamp_iso(),
        }
    )
    _guardar(datos, "objetivo_add")
    return datos


def cambiar_estado_objetivo(objetivo_id: str, estado: str) -> dict[str, Any]:
    if estado not in ESTADOS:
        raise ValueError(f"Estado inválido; usa {ESTADOS}")

    datos = cargar()

    for o in datos["objetivos"]:
        if o.get("id") == objetivo_id:
            o["estado"] = estado
            o["actualizado"] = timestamp_iso()
            break
    else:
        raise KeyError(f"No existe el objetivo: {objetivo_id}")

    _guardar(datos, "objetivo_estado")
    return datos


def quitar_objetivo(objetivo_id: str) -> dict[str, Any]:
    datos = cargar()
    antes = len(datos["objetivos"])
    datos["objetivos"] = [o for o in datos["objetivos"] if o.get("id") != objetivo_id]

    if len(datos["objetivos"]) == antes:
        raise KeyError(f"No existe el objetivo: {objetivo_id}")

    _guardar(datos, "objetivo_del")
    return datos


# --------------------------------------------------------------------- CLI


def main() -> int:
    parser = argparse.ArgumentParser(description="Perfil persistente del usuario.")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--nombre")
    parser.add_argument("--rol")
    parser.add_argument("--stack", help="Lista separada por comas.")
    parser.add_argument("--mostrar", action="store_true")
    parser.add_argument("--set", metavar="CLAVE=VALOR")
    parser.add_argument("--interes-add", metavar="NOMBRE")
    parser.add_argument("--peso", type=float, default=None, help="1-5 (formato viejo) o 0.1-2.0 (formato nuevo).")
    parser.add_argument("--interes-del", metavar="NOMBRE")
    parser.add_argument("--objetivo-add", metavar="TEXTO")
    parser.add_argument("--prioridad", default="media", choices=PRIORIDADES)
    parser.add_argument("--objetivo-estado", nargs=2, metavar=("ID", "ESTADO"))
    parser.add_argument("--objetivo-del", metavar="ID")
    parser.add_argument("--regenerar", action="store_true")
    args = parser.parse_args()

    try:
        if args.init:
            stack = [s.strip() for s in args.stack.split(",")] if args.stack else None
            inicializar(nombre=args.nombre, rol=args.rol, stack=stack)
            print("Perfil inicializado.")
        elif args.set:
            clave, _, valor = args.set.partition("=")
            fijar(clave, valor)
            print(f"{clave.strip()} actualizado.")
        elif args.interes_add:
            agregar_interes(args.interes_add, args.peso)
            print("Interés guardado.")
        elif args.interes_del:
            quitar_interes(args.interes_del)
            print("Interés eliminado.")
        elif args.objetivo_add:
            datos = agregar_objetivo(args.objetivo_add, args.prioridad)
            print(f"Objetivo creado: {datos['objetivos'][-1]['id']}")
        elif args.objetivo_estado:
            cambiar_estado_objetivo(*args.objetivo_estado)
            print("Estado actualizado.")
        elif args.objetivo_del:
            quitar_objetivo(args.objetivo_del)
            print("Objetivo eliminado.")
        elif args.regenerar:
            print(f"Vista regenerada: {regenerar_markdown()}")
        elif args.mostrar:
            print(json.dumps({k: v for k, v in cargar().items() if not k.startswith("_")}, ensure_ascii=False, indent=2))
        else:
            parser.print_help()
            return 1
    except (ValueError, KeyError) as exc:
        print(f"Error: {exc}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
