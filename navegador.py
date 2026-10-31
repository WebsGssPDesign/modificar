"""
navegador.py — Cliente HTTP educado para aprendizaje web.

Reglas:
- Solo dominios de la lista blanca.
- Respeta robots.txt.
- Usa ETag / If-None-Match cuando esté disponible.
- Limita peticiones por hora y día.
- Extrae texto legible, sin ejecutar JavaScript.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config import cargar_config
from eventos import emitir_evento
from util import leer_json, escribir_json_atomico, timestamp_iso

USER_AGENT = "memoria-vectorial/0.1 (+local personal knowledge base)"
DEFAULT_TIMEOUT = 30.0

ETIQUETAS_IGNORADAS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "iframe",
    "nav",
    "footer",
    "aside",
}


class ExtractorTexto(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.partes: list[str] = []
        self._ignorar = 0
        self._titulo = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ETIQUETAS_IGNORADAS:
            self._ignorar += 1

        if tag == "title" and not self._titulo:
            self._capturar_titulo = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ETIQUETAS_IGNORADAS and self._ignorar:
            self._ignorar -= 1

        if tag == "title":
            self._capturar_titulo = False

    def handle_data(self, data: str) -> None:
        if self._ignorar:
            return

        texto = data.strip()

        if not texto:
            return

        if getattr(self, "_capturar_titulo", False) and not self._titulo:
            self._titulo = texto

        self.partes.append(texto)

    def texto(self) -> str:
        texto = "\n".join(self.partes)
        texto = re.sub(r"\n{3,}", "\n\n", texto)
        return texto.strip()


class Navegador:
    def __init__(self) -> None:
        self.config = cargar_config()
        self.cache_path = self.config.memoria_dir / "web_cache.json"
        self.estado_path = self.config.memoria_dir / "web_estado.json"
        self.cache = leer_json(self.cache_path, {})
        self.estado = leer_json(self.estado_path, {"hora": [], "dia": []})

    def _dominio_permitido(self, url: str) -> bool:
        dominio = urlparse(url).netloc.lower()
        dominio = dominio.removeprefix("www.")

        return any(
            dominio == permitido.lower().removeprefix("www.")
            or dominio.endswith("." + permitido.lower().removeprefix("www."))
            for permitido in self.config.web_dominios
        )

    def _limpiar_ventanas(self) -> None:
        ahora = time.time()
        self.estado["hora"] = [
            ts for ts in self.estado.get("hora", []) if ahora - ts < 3600
        ]
        self.estado["dia"] = [
            ts for ts in self.estado.get("dia", []) if ahora - ts < 86400
        ]

    def _puede_pedir(self) -> tuple[bool, str]:
        self._limpiar_ventanas()

        if len(self.estado["hora"]) >= int(self.config.web_max_por_hora.valor):
            return False, "Límite horario alcanzado"

        if len(self.estado["dia"]) >= int(self.config.web_max_por_dia.valor):
            return False, "Límite diario alcanzado"

        return True, ""

    def _registrar_peticion(self) -> None:
        ahora = time.time()
        self.estado["hora"].append(ahora)
        self.estado["dia"].append(ahora)
        escribir_json_atomico(self.estado_path, self.estado)

    def _robots_permite(self, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        parser = urllib.robotparser.RobotFileParser()

        try:
            parser.set_url(robots_url)
            parser.read()
        except (urllib.error.URLError, OSError):
            # Si no se puede leer robots.txt, ser conservador.
            return False

        return parser.can_fetch(USER_AGENT, url)

    def _extraer_texto(self, html: str) -> tuple[str, str]:
        extractor = ExtractorTexto()
        extractor.feed(html)
        return extractor._titulo, extractor.texto()

    def obtener(self, url: str) -> dict[str, Any]:
        if not self._dominio_permitido(url):
            raise ValueError(f"Dominio no permitido: {url}")

        permitido, motivo = self._puede_pedir()

        if not permitido:
            raise RuntimeError(motivo)

        if not self._robots_permite(url):
            raise RuntimeError(f"robots.txt no permite acceder a: {url}")

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        cache = self.cache.get(url, {})
        etag = cache.get("etag")

        if etag:
            headers["If-None-Match"] = etag

        request = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                if response.status == 304:
                    return {
                        "url": url,
                        "estado": "sin_cambios",
                        "titulo": cache.get("titulo", ""),
                        "texto": cache.get("texto", ""),
                        "etag": etag,
                    }

                html = response.read().decode("utf-8", errors="replace")
                etag_nuevo = response.headers.get("ETag")

        except urllib.error.HTTPError as exc:
            if exc.code == 304 and etag:
                return {
                    "url": url,
                    "estado": "sin_cambios",
                    "titulo": cache.get("titulo", ""),
                    "texto": cache.get("texto", ""),
                    "etag": etag,
                }

            raise

        self._registrar_peticion()

        titulo, texto = self._extraer_texto(html)

        if not titulo:
            titulo = urlparse(url).path.rstrip("/").split("/")[-1] or url

        self.cache[url] = {
            "etag": etag_nuevo,
            "titulo": titulo,
            "texto": texto,
            "actualizado": timestamp_iso(),
        }

        escribir_json_atomico(self.cache_path, self.cache)

        return {
            "url": url,
            "estado": "ok",
            "titulo": titulo,
            "texto": texto,
            "etag": etag_nuevo,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga y extrae texto de una URL permitida.")
    parser.add_argument("url")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--max-chars", type=int, default=2000)

    args = parser.parse_args()

    if args.check:
        config = cargar_config()
        print("Dominios permitidos:")
        for dominio in config.web_dominios:
            print(f"  - {dominio}")
        return 0

    navegador = Navegador()

    try:
        resultado = navegador.obtener(args.url)
    except Exception as exc:
        print(f"Error: {exc}")
        return 2

    print(f"URL: {resultado['url']}")
    print(f"Estado: {resultado['estado']}")
    print(f"Título: {resultado['titulo']}")
    print("\nTexto:")
    print(resultado["texto"][: args.max_chars])

    return 0


if __name__ == "__main__":
    sys.exit(main())
