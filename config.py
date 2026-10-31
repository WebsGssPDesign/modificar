"""
config.py — Configuración única de memoria_vectorial.

Precedencia:
    default < Sistema/reglas.json < variable de entorno

Uso:
    python config.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BOVEDA = r"F:\automatizaciones\homeLab"
DEFAULT_NOTAS = "LLM-Memoria"
DEFAULT_MIN_SIM = 0.35
DEFAULT_POOL = 30
DEFAULT_MAX_SYNC_SEGUNDOS = 5.0
DEFAULT_WEB_MAX_POR_HORA = 30
DEFAULT_WEB_MAX_POR_DIA = 200
DEFAULT_GUARDIAN_MODO = "observacion"
DEFAULT_APRENDER_EXCLUIR = [
    "Diario",
    "Sistema",
    "LLM-Memoria",
    "Perfil",
    "skills",
    "memoria_vectorial/.memoria",
    ".obsidian",
    ".trash",
]
DEFAULT_INDICE_EXCLUIR = [
    "Sistema",
    "Diario",
    "memoria_vectorial/.memoria",
    ".obsidian",
    ".trash",
]
DEFAULT_INDICE_IGNORAR_ARCHIVOS = [
    "tablero.md",
    "huecos.md",
    "conocimiento.md",
    "aprendidohoy.md",
    "estado.md",
    "cola.md",
]


@dataclass(frozen=True)
class ValorConfig:
    valor: Any
    origen: str  # "default" | "reglas.json" | "env"


@dataclass
class Config:
    boveda: Path
    notas: Path
    sistema: Path
    perfil: Path
    memoria_dir: Path
    min_sim: ValorConfig
    pool: ValorConfig
    max_sync_segundos: ValorConfig
    aprender_excluir: list[str]
    indice_excluir: list[str]
    indice_ignorar_archivos: list[str]
    web_dominios: list[str]
    web_max_por_hora: ValorConfig
    web_max_por_dia: ValorConfig
    guardian_modo: ValorConfig
    guardian_reparaciones: list[str]
    repaso_dias: list[int]
    confianza_por_fuente: dict[str, float]
    _origenes: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def db_path(self) -> Path:
        return self.memoria_dir / "indice.sqlite"

    @property
    def reglas_path(self) -> Path:
        return self.sistema / "reglas.json"

    @property
    def auditoria_path(self) -> Path:
        return self.sistema / "auditoria.jsonl"

    @property
    def eventos_path(self) -> Path:
        return self.sistema / "eventos.jsonl"

    @property
    def metricas_path(self) -> Path:
        return self.sistema / "metricas.jsonl"

    @property
    def incidencias_path(self) -> Path:
        return self.sistema / "incidencias.json"

    @property
    def heartbeat_path(self) -> Path:
        return self.sistema / "heartbeat.json"

    @property
    def papelera_path(self) -> Path:
        return self.sistema / "papelera"

    @property
    def backups_path(self) -> Path:
        return self.sistema / "backups"

    def origen(self, clave: str) -> str:
        return self._origenes.get(clave, "default")


def _leer_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _resolver(
    clave: str,
    default: Any,
    reglas: dict[str, Any],
    env_name: str | None = None,
    cast: type | None = None,
) -> ValorConfig:
    valor = default
    origen = "default"

    if env_name and env_name in os.environ:
        raw = os.environ[env_name]
        try:
            valor = cast(raw) if cast else raw
            origen = "env"
        except (TypeError, ValueError):
            valor = default
            origen = "default"
    else:
        nodo: Any = reglas
        encontrado = True
        for parte in clave.split("."):
            if isinstance(nodo, dict) and parte in nodo:
                nodo = nodo[parte]
            else:
                encontrado = False
                break

        if encontrado:
            valor = nodo
            origen = "reglas.json"

    return ValorConfig(valor=valor, origen=origen)


def cargar_config() -> Config:
    boveda_valor = _resolver(
        "memoria.boveda",
        DEFAULT_BOVEDA,
        {},
        "MEMORIA_BOVEDA",
    )

    boveda = Path(str(boveda_valor.valor)).expanduser().resolve()
    sistema = boveda / "Sistema"
    reglas = _leer_json(sistema / "reglas.json")

    notas_valor = _resolver(
        "memoria.notas",
        DEFAULT_NOTAS,
        reglas,
        "MEMORIA_NOTAS",
    )

    min_sim = _resolver(
        "memoria.min_sim",
        DEFAULT_MIN_SIM,
        reglas,
        "MEMORIA_MIN_SIM",
        float,
    )

    pool = _resolver(
        "memoria.pool",
        DEFAULT_POOL,
        reglas,
        "MEMORIA_POOL",
        int,
    )

    max_sync = _resolver(
        "memoria.max_sync_segundos",
        DEFAULT_MAX_SYNC_SEGUNDOS,
        reglas,
        "MEMORIA_MAX_SYNC_SEGUNDOS",
        float,
    )

    web_hora = _resolver(
        "web.limites.max_por_hora",
        DEFAULT_WEB_MAX_POR_HORA,
        reglas,
        "WEB_LIMITES_MAX_POR_HORA",
        int,
    )

    guardian_modo = _resolver(
        "guardian.modo",
        DEFAULT_GUARDIAN_MODO,
        reglas,
        "MEMORIA_GUARDIAN_MODO",
    )

    config = Config(
        boveda=boveda,
        notas=boveda / str(notas_valor.valor),
        sistema=sistema,
        perfil=boveda / "Perfil",
        memoria_dir=boveda / "memoria_vectorial" / ".memoria",
        min_sim=min_sim,
        pool=pool,
        max_sync_segundos=max_sync,
        aprender_excluir=list(
            reglas.get("aprender", {}).get("excluir", DEFAULT_APRENDER_EXCLUIR)
        ),
        indice_excluir=list(
            reglas.get("indice", {}).get("excluir", DEFAULT_INDICE_EXCLUIR)
        ),
        indice_ignorar_archivos=list(
            reglas.get("indice", {}).get(
                "ignorar_archivos", DEFAULT_INDICE_IGNORAR_ARCHIVOS
            )
        ),
        web_dominios=list(reglas.get("web", {}).get("dominios_permitidos", [])),
        web_max_por_hora=web_hora,
        web_max_por_dia=_resolver(
            "web.limites.max_por_dia",
            DEFAULT_WEB_MAX_POR_DIA,
            reglas,
            "WEB_LIMITES_MAX_POR_DIA",
            int,
        ),
        guardian_modo=guardian_modo,
        guardian_reparaciones=list(
            reglas.get("guardian", {}).get("reparaciones_permitidas", [])
        ),
        repaso_dias=list(
            reglas.get("tablero", {}).get("repaso_dias", [1, 3, 7, 21, 60])
        ),
        confianza_por_fuente=dict(
            reglas.get("confianza", {}).get("por_fuente", {})
        ),
    )

    config._origenes = {
        "memoria.boveda": boveda_valor.origen,
        "memoria.notas": notas_valor.origen,
        "memoria.min_sim": min_sim.origen,
        "memoria.pool": pool.origen,
        "memoria.max_sync_segundos": max_sync.origen,
        "web.limites.max_por_hora": web_hora.origen,
        "guardian.modo": guardian_modo.origen,
    }

    return config


def validar_config(config: Config) -> list[str]:
    errores: list[str] = []

    if not config.boveda.exists():
        errores.append(f"La bóveda no existe: {config.boveda}")

    if config.min_sim.valor < 0 or config.min_sim.valor > 1:
        errores.append("memoria.min_sim debe estar entre 0 y 1")

    if config.guardian_modo.valor not in {"observacion", "reparar"}:
        errores.append("guardian.modo debe ser 'observacion' o 'reparar'")

    if config.web_max_por_hora.valor < 1:
        errores.append("web.limites.max_por_hora debe ser al menos 1")

    return errores


def preparar_carpetas(config: Config) -> None:
    carpetas = [
        config.boveda,
        config.sistema,
        config.notas,
        config.perfil,
        config.memoria_dir,
        config.papelera_path,
        config.backups_path,
    ]

    for carpeta in carpetas:
        carpeta.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida la configuración base.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Muestra la configuración efectiva, su origen y valida rutas.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Crea las carpetas base si no existen.",
    )
    args = parser.parse_args()

    config = cargar_config()

    if args.init:
        preparar_carpetas(config)
        print(f"Carpetas base preparadas en: {config.boveda}")

    print("Configuración efectiva:")
    print(f"  bóveda              = {config.boveda} [{config.origen('memoria.boveda')}]")
    print(f"  notas generadas     = {config.notas} [{config.origen('memoria.notas')}]")
    print(f"  min_sim             = {config.min_sim.valor} [{config.min_sim.origen}]")
    print(f"  pool                = {config.pool.valor} [{config.pool.origen}]")
    print(f"  max_sync_segundos   = {config.max_sync_segundos.valor} [{config.max_sync_segundos.origen}]")
    print(f"  web max/hora        = {config.web_max_por_hora.valor} [{config.web_max_por_hora.origen}]")
    print(f"  guardian.modo       = {config.guardian_modo.valor} [{config.guardian_modo.origen}]")
    print(f"  SQLite              = {config.db_path}")

    errores = validar_config(config)

    if errores:
        print("\nErrores:")
        for error in errores:
            print(f"  - {error}")
        return 2

    print("\nConfiguración válida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
