"""
migrar_perfil.py

Migra los archivos del perfil a la estructura v3.

Migra:
    perfil_usuario.json
    intereses.json
    objetivos.json

Realiza backup automático antes de modificar.

Uso:
    python migrar_perfil.py
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from config import cargar_config
from escritor import escribir_json_auditado
from util import leer_json

ACTOR = "migrador_perfil"


def timestamp():
    return datetime.now().isoformat(timespec="seconds")


def backup_archivo(ruta: Path) -> None:
    if not ruta.exists():
        return

    destino = ruta.with_suffix(
        ruta.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    shutil.copy2(ruta, destino)
    print(f"[BACKUP] {destino.name}")


def migrar_perfil_usuario(datos: dict) -> dict:
    resultado = {
        "version": 3,
        "nombre": datos.get(
            "nombre",
            "Usuario"
        ),
        "idioma": datos.get("idioma", "es"),
        "ubicacion": datos.get("ubicacion", "Montevideo, Uruguay"),
        "presupuesto": datos.get("presupuesto", "muy limitado"),

        "filosofia": datos.get(
            "filosofia",
            [
                "simplicidad",
                "control manual",
                "minimo numero de dependencias",
                "primero funciona, luego optimiza"
            ]
        ),

        "preferencias": {
            **datos.get("preferencias", {}),
            "aprendizaje_continuo": True
        },

        "hardware": datos.get("hardware", {}),

        "herramientas": datos.get("herramientas", []),

        "areas_negocio": datos.get(
            "areas_negocio",
            []
        ),

        "criterios_busqueda": {
            "idiomas": ["es", "en"],
            "priorizar": [
                "github",
                "documentacion_oficial",
                "opensource",
                "casos_reales",
                "local_ai"
            ],
            "descartar": [
                "publicidad",
                "spam",
                "clickbait",
                "contenido_desactualizado"
            ]
        },

        "memoria": {
            "habilitada": True,

            "corto_plazo": {
                "max_items": 50,
                "retencion_dias": 7
            },

            "medio_plazo": {
                "max_items": 500,
                "retencion_dias": 90
            },

            "largo_plazo": {
                "max_items": 5000,
                "retencion_dias": 3650
            },

            "resumen_automatico": True,
            "consolidacion_nocturna": True,
            "promocion_memoria": True,
            "degradacion_memoria": True
        },

        "evaluacion": {
            "habilitada": True,

            "criterios": {
                "relevancia": 40,
                "utilidad": 30,
                "confiabilidad": 20,
                "novedad": 10
            },

            "umbral_memoria_larga": 85,
            "umbral_guardado": 70,
            "umbral_memoria_corta": 50,
            "umbral_descartar": 40
        },

        "aprendizaje": {
            "nivel_actual": 0,
            "experiencia": 0,

            "recompensas": {
                "hallazgo_relevante": 5,
                "objetivo_completado": 20,
                "fuente_confiable": 3
            },

            "penalizaciones": {
                "informacion_irrelevante": -2,
                "duplicado": -1,
                "fuente_poco_confiable": -3
            }
        },

        "evaluacion_continua": {
            "habilitada": True,
            "revisar_cada_dias": 30,
            "eliminar_obsoleto": False
        },

        "estadisticas": datos.get(
            "estadisticas",
            {
                "conocimientos_guardados": 0,
                "conocimientos_descartados": 0,
                "objetivos_cumplidos": 0,
                "consultas_realizadas": 0,
                "ultima_revision": None
            }
        ),

        "actualizado": timestamp()
    }

    return resultado


def migrar_intereses(datos):
    if isinstance(datos, dict):
        return datos

    principales = []
    pesos = {}

    for item in datos:

        if isinstance(item, str):
            principales.append(item)
            pesos[item] = 1.0

        elif isinstance(item, dict):

            nombre = item.get("nombre")

            if not nombre:
                continue

            principales.append(nombre)

            peso_antiguo = int(item.get("peso", 3))

            pesos[nombre] = round(
                max(0.1, min(2.0, peso_antiguo / 3)),
                2
            )

    resultado = {
        "version": 3,

        "principales": principales,

        "secundarios": [],

        "evitar": [],

        "pesos": pesos,

        "aprendizaje": {
            "actualizacion_automatica": True,
            "incremento_por_hallazgo_util": 0.05,
            "decremento_por_hallazgo_irrelevante": 0.02,
            "peso_maximo": 2.0,
            "peso_minimo": 0.1
        },

        "estadisticas": {
            "busquedas_realizadas": 0,
            "hallazgos_relevantes": 0,
            "hallazgos_descartados": 0,
            "ultima_actualizacion": None
        }
    }

    return resultado


def migrar_objetivos(datos):

    if isinstance(datos, dict):
        return datos

    objetivos = []

    for item in datos:

        if not isinstance(item, dict):
            continue

        objetivos.append({
            "id": item.get("id", ""),
            "nombre": item.get(
                "texto",
                item.get("nombre", "")
            ),
            "estado": item.get(
                "estado",
                "activo"
            ),
            "prioridad": item.get(
                "prioridad",
                5
            ),
            "progreso": 0
        })

    resultado = {
        "version": 3,
        "objetivos": objetivos,

        "criterios_exito": {},

        "autoevaluacion": {
            "habilitada": True,
            "frecuencia": "diaria",

            "metricas": {
                "conocimiento_nuevo": 0,
                "objetivos_avanzados": 0,
                "errores_detectados": 0,
                "exitos_detectados": 0
            },

            "reglas": {
                "sumar_progreso_por_hallazgo": 1,
                "sumar_progreso_por_accion_exitosa": 2,
                "restar_progreso_por_error": 1
            }
        },

        "historial": []
    }

    return resultado


def main():

    config = cargar_config()

    perfil_path = config.perfil / "perfil_usuario.json"
    intereses_path = config.perfil / "intereses.json"
    objetivos_path = config.perfil / "objetivos.json"

    for archivo in (
        perfil_path,
        intereses_path,
        objetivos_path,
    ):
        backup_archivo(archivo)

    perfil = leer_json(perfil_path, {})
    intereses = leer_json(intereses_path, [])
    objetivos = leer_json(objetivos_path, [])

    perfil_v3 = migrar_perfil_usuario(perfil)
    intereses_v3 = migrar_intereses(intereses)
    objetivos_v3 = migrar_objetivos(objetivos)

    escribir_json_auditado(
        perfil_path.relative_to(config.boveda).as_posix(),
        perfil_v3,
        actor=ACTOR,
        motivo="migracion_v3"
    )

    escribir_json_auditado(
        intereses_path.relative_to(config.boveda).as_posix(),
        intereses_v3,
        actor=ACTOR,
        motivo="migracion_v3"
    )

    escribir_json_auditado(
        objetivos_path.relative_to(config.boveda).as_posix(),
        objetivos_v3,
        actor=ACTOR,
        motivo="migracion_v3"
    )

    print()
    print("Migracion completada.")
    print("Perfil v3 generado.")
    print("Intereses v3 generados.")
    print("Objetivos v3 generados.")


if __name__ == "__main__":
    main()