# Aprendizaje web automático — flujo, herramientas y cómo usarlo

Estado (30/10/2026): plan aprobado. Fases 0 y 1 hechas y probadas (129 tests). Faltan las partes 1 a 3 del workflow de n8n. Lo hecho está en §11 y se usa como indica §11.1. Este documento se llama README_aprendizaje_web.md (y no README.md) para que no pise el README.md de memoria_vectorial. Guardalo en F:\automatizaciones\homeLab\memoria_vectorial\docs\ o donde prefieras.

Marcas: ✅ comprobado leyendo tus archivos · 🆕 propuesta mía · ⚠️ riesgo o problema encontrado. "Leído" significa que lo vi en el código; no ejecuté nada de tu proyecto (ni LM Studio, ni n8n).

## 1. En 60 segundos

**Objetivo**: que cada noche el sistema busque en internet cosas útiles para tus objetivos, las evalúe con modelos locales, guarde las buenas como notas en tu bóveda y aprenda qué temas le sirven.

**Reparto de trabajo**:
- **n8n** = la cinta transportadora. Programa, busca, filtra, llama a los modelos y entrega. No decide nada "de criterio".
- **LM Studio** (modelos locales) = juicio acotado: proponer consultas, puntuar relevancia y utilidad, resumir en español.
- **memoria_vectorial** (Python) = el único que escribe en la bóveda, audita, indexa y vigila.

**Lo que ya existe y se reutiliza**: escritor.py, navegador.py, indexer.py, analisis.py, recuperacion.py, n8n_puente.py, estado.py, guardian.py, los 5 JSON de lineamientos.

**Hecho**: ingesta_web.py, los JSON corregidos, la lista blanca y los ajustes a perfil.py y analisis.py (§11).

**Falta**: el workflow de n8n, en 3 partes.

Los 4 problemas de §3.1 ya están corregidos en los archivos que te entrego. Mientras no copies los archivos nuevos, **no ejecutes perfil.py con escritura**: vaciaría tus JSON de perfil.

## 2. Qué ya tenés y qué papel juega

| Pieza | Qué hace hoy | Papel en el flujo nuevo | Veredicto |
|---|---|---|---|
| n8n (local) | Corre tu flujo "Organizador F:" cada noche (01:12) | Orquesta el flujo nuevo | ✅ usar, workflow separado |
| LM Studio | Sirve qwen3.5-4b, qwen3.5-9b y text-embedding-qwen3-embedding-0.6b en 127.0.0.1:1234 | Planificador, Investigador y Evaluador (4B); embeddings solo al final | ✅ usar |
| *Organizador F:* (workflow) | Clasifica archivos, crea hard links y .met con embedding | Ninguno | ✅ no se toca |
| escritor.py | Única puerta de escritura a la bóveda, con auditoría y .bak | Escribe las notas web y su metadato | ✅ obligatorio |
| navegador.py | Descarga HTML con lista blanca, robots.txt, ETag y límites | Páginas HTML permitidas | ⚠️ solo HTML (ver H5) |
| aprender_web.py | 1 URL → 1 nota en LLM-Memoria/Web | Fuente de ideas (prompt anti-inyección, validación) | ⚠️ no sirve tal cual (ver H4, H6) |
| indexer.py / memoria.py | Indexa notas en SQLite con embeddings | El paso final: genera los embeddings | ✅ usar sin cambios |
| analisis.py | Detecta huecos de conocimiento según tus intereses | Alimenta al Planificador | ⚠️ requiere ajuste (H2) |
| perfil.py | CLI para editar intereses y objetivos | — | ⚠️ no usar hasta ajustarlo (H2) |
| recuperacion.py | Búsqueda que respeta vigente_hasta | Expiración sin borrar | ✅ usar (no está conectada al MCP) |
| n8n_puente.py | Envía eventos de la bóveda a un webhook de n8n | Avisos y resumen diario | ✅ usar |
| estado.py, tablero.py, guardian.py, backup.py | Diagnóstico, tableros, vigilancia, copias | Verificar que todo marcha | ✅ usar |
| mcp_server.py, mcp_server_escritura.py | Exponen la memoria a tu agente | Sin cambios | ✅ |
| iniciar.ps1 | Pipeline manual (indexar, aprender, skills, tablero, backup…) | No incluye fase web ni n8n | ✅ por ahora no se toca |
| 5 JSON de lineamientos | Perfil, intereses, objetivos, criterios, sistema de aprendizaje | Constitución del sistema | ⚠️ corregir (H1, H3) |

## 3. Hallazgos de la revisión

### 3.1 A resolver antes de escribir código

✅ **Resueltos en la fase 0** (H1, H2, H3 y H5). Se dejan descritos para que sepas qué había y por qué cambió. H5: la lista blanca ya cubre todas tus fuentes; que navegador.py solo lee HTML sigue siendo cierto y por eso n8n consulta las APIs y feeds por su cuenta.

**H1** ⚠️ `perfil_usuario.json` tiene mal anidado. Es JSON válido, pero falta una `}` después de `criterios_aprendizaje.evitar`. Resultado: negocios, criterios_busqueda, memoria, evaluacion, aprendizaje y estadisticas quedaron dentro de `criterios_aprendizaje` (comprobado cargando el archivo). Si un flujo lee `perfil.evaluacion` o `perfil.memoria`, no lo encuentra.

**H2** ⚠️ `perfil.py` y `analisis.py` no entienden tus `intereses.json` y `objetivos.json` nuevos (leído y comprobado con la estructura real):

| Archivo | Lo que esperan | Lo que tenés | Consecuencia |
|---|---|---|---|
| intereses.json | lista de `{nombre, peso 1-5}` o un dict con la clave `intereses` | dict con `principales`, `secundarios`, pesos (0.1–2.0) | analisis.py ve 0 intereses → no genera huecos |
| objetivos.json | lista de `{id, texto, prioridad, estado}` | dict con `objetivos`, `criterios_exito`, `autoevaluacion` | perfil.py ve 0 objetivos |

Además, cualquier comando de `perfil.py` que escribe (`--init`, `--set`, `--interes-add`, `--objetivo-add`…) reescribe los tres JSON con la versión normalizada: `intereses.json` y `objetivos.json` quedarían como `[]`. Queda un `.bak` con sello de hora y registro en `auditoria.jsonl`, así que se recupera, pero el sistema funcionaría como si no tuvieras intereses. `iniciar.ps1` no llama a `perfil.py`, así que hoy no se dispara solo. **No ejecutes perfil.py con escritura hasta que lo ajustemos.**

Hay un segundo problema en `analisis.py`: solo lee notas de `LLM-Memoria/Hechos`. Las notas de `LLM-Memoria/Web` no cuentan para la cobertura, así que un hueco nunca se cerraría aunque la web ya lo cubra.

**H3** ⚠️ Los JSON se contradicen entre sí.

| Dato | Dónde aparece | Valores |
|---|---|---|
| Pesos de evaluación | perfil_usuario.json | relevancia 40, utilidad 30, novedad 20, confiabilidad 10 |
| — | lo que decidiste | relevancia 40, utilidad 30, confiabilidad 20, novedad 10 |
| Umbrales | perfil_usuario.json | guardar 70, memoria larga 85, descartar 40 |
| — | sistema_aprendizaje.json | larga 85, media 70, corta 50, descartar 49 |
| Criterios de búsqueda | perfil_usuario.json y criterios_busqueda.json | duplicados, con listas distintas |
| Fuentes | criterios_busqueda.fuentes_prioritarias y sistema_aprendizaje.fuentes_confiables | casi iguales, no idénticas |

🆕 Propuesta: **una sola fuente por dato**. Umbrales y ciclo en `sistema_aprendizaje.json`; pesos de evaluación y retención en `perfil_usuario.json`; fuentes y keywords en `criterios_busqueda.json`. El resto se borra de los otros archivos.

**H5** ⚠️ `navegador.py` solo sirve para HTML y tu lista blanca está incompleta.
- Envía `Accept: text/html` y extrae texto de HTML. Una respuesta JSON (API de GitHub o Hugging Face) saldría como basura.
- `web.dominios_permitidos` en `reglas.json` no incluye `ollama.com`, `openwebui.com` ni `readthedocs.io`, que están en tus JSON de lineamientos. Tampoco `raw.githubusercontent.com` (el README en texto plano de un repo).

🆕 Regla: **n8n consulta solo APIs y feeds** (GitHub, Hugging Face, RSS) con sus propios nodos HTTP, y aplica la misma lista blanca leyendo `reglas.json` (no se duplica la lista). Para páginas HTML se sigue usando `navegador.py`.

### 3.2 Observaciones (no bloquean, pero conviene saberlas)

**H4** — Código y configuración de dos generaciones distintas.
- `aprender_web.py` actual procesa una URL y no está en ninguna fase de `iniciar.ps1` (nadie lo llama solo).
- `reglas.json` trae claves de una versión anterior multi-fuente (`fuentes_api`, `fuentes_html`, `min_prioridad`, `enfriamiento_min`, `fallos_para_aislar`…) que el código actual no usa. `prompts/web_temas.md` y `web_resumen.md` tampoco se usan.
- La carpeta `PARCHES/` es de esa generación anterior: **no la apliques**. Sus parches llaman a funciones que no existen en tu código actual (`config.get`, `eventos.emitir`, `incidencias.aislar`, `incidencias.fallos_de`, `navegador.descartar`, `navegador.presupuesto_ok`, `memoria.embed`). Comprobado buscándolas una por una.

**H6** — `aprender_web.py` usa embeddings antes de decidir y a un costo alto. Hace 2 llamadas de embedding por URL (relevancia contra el perfil) y, para detectar duplicados, carga y normaliza todos los vectores del índice en cada URL. Tu índice pesaba ~223 MB en el informe del guardian del 22/10, así que son cientos de MB en RAM por cada página. Además contradice tu decisión de dejar los embeddings al final.

**H7** — `llm.py`: la expresión regular que limpia el razonamiento está incompleta. `THINKING_RE` empieza con `|` (una alternativa vacía) y solo elimina `<thinking>…</thinking>`, no `<think>…</think>`. Si el modelo razona, `chat_json` depende del "rescate" (del primer `{` al último `}`) y puede agarrar llaves del razonamiento. (Leído, no ejecutado.)

**H8** — `Context.md` no es un archivo limpio. Las líneas 1–6 y 633–638 son texto de chat y está envuelto en un bloque de código. Además describe el diseño CORE ↔ BRAIN (fases 0–8, "implementación no iniciada") y fija reglas que este flujo debe respetar, sobre todo la invariante 11: la investigación web nunca es aleatoria; necesita un disparador válido (un hueco, una propuesta aceptada, un dominio vigilado, una contradicción, una petición tuya). Ver §4.3.

**H9** — Informe del guardian del 22/10 con 2 errores (`indice: tuple indices must be integers`; `heartbeat: OverflowError`). El código del zip es posterior y no pude reproducirlos. Ejecutá `python guardian.py --una-vez` y confirmá que ya no aparecen.

**H10** — Observaciones del flujo "Organizador F:" (leídas en el JSON):
- El disparador se llama "Ejecutar prueba 01:12" y está activo como producción.
- Ningún nodo tiene manejo de errores: si falla un archivo, se detiene toda la corrida nocturna.
- Reprocesa todos los archivos de `archivos.txt` cada noche (sin comparar fecha o hash).
- Las rutas se insertan entre comillas simples dentro del comando de PowerShell: un archivo con `'` en el nombre lo rompe.
- n8n usa por defecto la zona horaria `America/New_York` si no configurás `GENERIC_TIMEZONE`. Si no lo hiciste, "01:12" es hora de Nueva York (ver §8.3).

Nada de H10 es parte de este trabajo. Lo dejo anotado por si querés optimizar después ("primero que funcione, luego optimiza").

## 4. Arquitectura propuesta

### 4.1 Principios (heredados de tu proyecto)
1. **El código manda.** El LLM solo puntúa, resume y propone. No elige rutas, no escribe archivos.
2. **Un solo escritor.** Todo lo que entra a la bóveda pasa por `escritor.py`.
3. **n8n nunca escribe en SQLite ni en la bóveda.** Entrega un "paquete" y Python lo publica.
4. **Nada se borra.** Expirar = marcar `vigente_hasta`. Descartar = mover a `rechazados`.
5. **Embeddings al final de todo.** n8n no llama al modelo de embeddings; lo hace el indexador cuando la nota ya existe.
6. **El contenido web es dato, no instrucción.** Jamás se inserta en una línea de comandos (ver §10).

### 4.2 Diagrama

```text
 n8n  (cinta transportadora, determinista)
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │ 1 Disparo 03:00 / manual                                                         │
 │ 2 Cargar lineamientos (5 JSON) + huecos (analisis.py --json) + URLs ya vistas     │
 │ 3 PLANIFICADOR (4B)  → ≤ 8 consultas, cada una con su "disparador"               │
 │ 4 Fuentes: GitHub API · releases Atom · Hugging Face API · RSS    (lista blanca)  │
 │ 5 Deduplicar por hash de URL + filtrar antigüedad ≤ 12 meses y descartes          │
 │ 6 INVESTIGADOR (4B)  → pre-puntaje sobre título + snippet:  20 → 10              │
 │ 7 Extraer texto limpio de los 10                                                  │
 │ 8 EVALUADOR (4B)     → relevancia, utilidad, resumen en español:  10 → 5 mejores  │
 │ 9 Código: confiabilidad + novedad + puntaje final + nivel de memoria              │
 └───────────────────────────────┬────────────────────────────────────────────────┘
                                 │  buzón de archivos JSON (.memoria\entrada_web\)
                                 ▼
 Python (memoria_vectorial) — único escritor
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │ 10 ingesta_web.py 🆕  valida · recalcula el puntaje · crea la nota con escritor   │
 │    (LLM-Memoria/Web) · actualiza pesos · propone intereses nuevos · mantenimiento │
 │ 11 indexer.py --index  → EMBEDDINGS (último paso)                                 │
 │ 12 estado.py / n8n_puente.py → resumen diario y avisos                            │
 └────────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Cómo cumple la regla "nunca aleatorio" de Context.md

Cada consulta que genera el Planificador lleva un **disparador**, y ese dato viaja hasta la nota:

| Disparador | De dónde sale | Ejemplo |
|---|---|---|
| `hueco` | `analisis.py --json` → huecos | "Interés Open WebUI sin notas" |
| `dominio_vigilado` | `criterios_busqueda.json` → keywords (tu watchlist) | "agent memory" |
| `peticion` | un archivo que vos dejás en el buzón (futuro) | "investigá ChromaDB vs SQLite-vec" |

Una nota con puntaje < 50 se descarta y se registra como `investigacion_no_util`. Eso cumple la "restricción crítica" (aprende porque algo reduce incertidumbre, no porque sea nuevo) y no almacena artículos completos: solo resumen, hechos y URL.

### 4.4 Relación con el video (según el resumen que pegaste)

No pude ver el video; uso tu resumen.

| AI Factory | Aquí |
|---|---|
| Brain (memoria persistente) | memoria_vectorial |
| Orquestador determinista | n8n |
| Spec Writer / Builder | Planificador / Investigador |
| Revisores en paralelo | Evaluador + reglas de código (confiabilidad, novedad) |
| Approver y clasificador de criticidad | Umbrales de puntaje + aprobación tuya para cambios al perfil |

### 4.5 Tus 4 agentes

| Agente | Modelo | Qué hace | ¿Usa LLM? |
|---|---|---|---|
| Planificador | 4B | Convierte objetivos, pesos y huecos en ≤ 8 consultas | Sí |
| Investigador | 4B | Pre-puntúa título y snippet (20 → 10) | Sí |
| Evaluador | 4B (parámetro; 9B si hace falta) | Relevancia, utilidad y resumen en español | Sí |
| Memoria | — | Decide el nivel con una tabla de umbrales y escribe la nota | No (es código) |

Dar "Memoria" a un LLM solo añadiría errores: es una tabla de umbrales.

## 5. El flujo paso a paso

| # | Etapa | Entrada → salida | Quién | Límite |
|---|---|---|---|---|
| 1 | Disparo | Cron 03:00 o ejecución manual | n8n | — |
| 2 | Cargar contexto | 5 JSON + `python analisis.py --json` + `.memoria\aprendizaje_web.json` → contexto | n8n (solo lectura) | — |
| 3 | Planificar | contexto → consultas con disparador | LLM 4B | ≤ 8 consultas |
| 4 | Buscar | consultas → candidatos (título, URL, fecha, snippet, fuente) | n8n HTTP | solo dominios permitidos |
| 5 | Filtrar | candidatos → nuevos | n8n Code | URL ya vista = descarta; > 12 meses = descarta; lista descartar |
| 6 | Pre-puntuar | candidatos → mejores | LLM 4B | 20 → 10 |
| 7 | Extraer | URL → texto limpio | n8n HTTP + Code | recorte a ~6 000 caracteres |
| 8 | Evaluar | texto → relevancia, utilidad, resumen_es, hechos, tags, entidades | LLM 4B | 10 → 5 mejores |
| 9 | Puntuar | componentes → puntaje y nivel | n8n Code | fórmula de §7.3 |
| 10 | Entregar | paquete JSON → `.memoria\entrada_web\` | n8n | 1 archivo por hallazgo |
| 11 | Publicar | buzón → notas en LLM-Memoria\Web | ingesta_web.py 🆕 | recalcula el puntaje y valida |
| 12 | Ajustar | resultados → pesos, estadísticas, propuestas | ingesta_web.py 🆕 | ver §7.4 |
| 13 | Indexar | notas nuevas → SQLite + embeddings | indexer.py --index | último paso |
| 14 | Informar | resumen del día | estado.py + n8n_puente.py | — |

Sobre "20 → 10 → 5 → 1-3 promovidos": 20, 10 y 5 son topes por noche. Lo de "1-3 promovidos" es lo que esperás obtener: la promoción a memoria larga depende de superar 85, no de un cupo.

## 6. Herramientas: qué usar y cómo

### 6.1 LM Studio
- **Para qué**: servir los modelos locales. Debe estar con el servidor activo en `http://127.0.0.1:1234/v1`.
- **Modelos**: `qwen3.5-4b` (planificar, pre-filtrar, evaluar), `text-embedding-qwen3-embedding-0.6b` (solo el indexador). `qwen3.5-9b` es el modelo por defecto de los scripts Python (`LLM_MODEL`); poné `LLM_MODEL` según lo que tengas cargado.
- ⚠️ Confirmá que los modelos que usás caben a la vez en 12 GB de VRAM. No lo medí.
- **Comprobar**:

```powershell
Invoke-RestMethod http://127.0.0.1:1234/v1/models | Select-Object -ExpandProperty data | Select-Object id
```

### 6.2 n8n
- **Para qué**: programar y encadenar los pasos 1–10 y lanzar los comandos Python de 11–14.
- **Cómo corre**: local, con PowerShell (ver §8). El workflow nuevo es independiente del Organizador.
- **Nodos que se usarán**: Schedule Trigger, Execute Command, HTTP Request, Code, Split In Batches, IF, Merge.

### 6.3 Fuentes de búsqueda (sin Docker, sin SearXNG)

| Fuente | Qué aporta | Detalles |
|---|---|---|
| GitHub API | Repos por keyword y actividad reciente | `GET https://api.github.com/search/repositories?q=...`. Token gratis recomendado (sin token el límite es bajo). Se guarda como credencial de n8n |
| Releases (Atom) | Novedades de n8n, Ollama, Open WebUI, ChromaDB, LM Studio | `https://github.com/<dueño>/<repo>/releases.atom` |
| Hugging Face API | Modelos y papers | `https://huggingface.co/api/models?search=...` (parámetros exactos: se verifican al construir la parte 1) |
| RSS técnicos | Blogs y docs con feed | Lista a completar por vos (no inventé URLs) |
| Hacker News, r/LocalLLaMA | Casos reales de IA local | Opcional, desactivado. Requiere agregar el dominio a la lista blanca |

### 6.4 analisis.py — de dónde salen los huecos

```powershell
cd F:\automatizaciones\homeLab\memoria_vectorial
.\.venv\Scripts\Activate.ps1
python analisis.py --json
```

Devuelve `huecos: [{"interes": "...", "motivo": "..."}]`. Hoy devolvería una lista vacía (H2).

### 6.5 escritor.py — cómo se escribirá cada nota

`ingesta_web.py` usará dos funciones que ya existen:
- `crear_nota(titulo, cuerpo, carpeta="LLM-Memoria/Web", tags=[...], fuente=<URL>, confianza=<0-1>, actor="ingesta_web")`
- `actualizar_frontmatter(ruta, {...campos extra...}, backup=False)` para `nivel_memoria`, `puntaje`, `vigente_hasta`, etc.

No hace falta modificar `escritor.py`. Los textos libres (título original, resumen) se escribirán entre comillas JSON para que el frontmatter no se rompa con `:`.

### 6.6 indexer.py — los embeddings

```powershell
python indexer.py --index          # indexa lo nuevo y calcula embeddings
python indexer.py --status
python indexer.py --search "memoria para agentes" --k 5
```

Si el vigilante (`indexer.py --watch`, lo arranca `iniciar.ps1`) está activo, indexa solo (revisa cada 30 s por defecto). Si no, n8n ejecuta `--index` al final. Ambos a la vez no rompen nada (hay lock).

### 6.7 recuperacion.py — expiración sin borrar

```powershell
python recuperacion.py "memoria para agentes" --ambito LLM-Memoria/Web --k 5
python recuperacion.py "memoria para agentes" --ambito LLM-Memoria/Web --incluir-vencidos
```

Oculta las notas con `vigente_hasta` vencido; con `--incluir-vencidos` las muestra. ⚠️ El MCP (`buscar_memoria`) todavía no usa este filtro: tu agente seguiría viendo notas vencidas. Está en el pendiente 5 de tu README.

### 6.8 n8n_puente.py — avisos hacia n8n

```powershell
python n8n_puente.py --una-vez --dry-run --huecos     # muestra lo que enviaría, sin enviar
$env:N8N_WEBHOOK_URL = "http://localhost:5678/webhook/memoria"   # ejemplo
python n8n_puente.py --una-vez
```

Solo envía metadatos (nunca el texto de las notas). En n8n hay que crear un workflow con un nodo Webhook que reciba eso.

### 6.9 Control de calidad

```powershell
python config.py --check
python estado.py --tablero         # diagnóstico en Obsidian
python guardian.py --una-vez
python backup.py --crear           # antes de la primera corrida real
```

## 7. Contratos de datos (🆕 propuestos)

### 7.1 El buzón: un JSON por hallazgo

Carpeta: `F:\automatizaciones\homeLab\memoria_vectorial\.memoria\entrada_web\` (con `procesados\` y `rechazados\` al lado). n8n solo crea archivos aquí; Python los lee y los mueve (no los borra).

```json
{
  "version": 1,
  "url": "https://github.com/ejemplo/agent-memory-demo",
  "fuente": "github.com",
  "tipo_fuente": "github_api",
  "disparador": { "tipo": "dominio_vigilado", "detalle": "agent memory" },
  "titulo_original": "agent-memory-demo",
  "titulo_es": "Memoria de largo plazo para agentes (demo)",
  "idioma_original": "en",
  "fecha_publicacion": "2026-09-14",
  "resumen_es": "Biblioteca de ejemplo que guarda memoria de largo plazo para agentes usando SQLite.",
  "hechos_es": ["Usa SQLite con búsqueda de texto", "Licencia MIT"],
  "tags": ["ia-local", "agentes", "memoria"],
  "entidades": ["SQLite"],
  "objetivos": ["OBJ-002", "OBJ-004"],
  "temas_nuevos": ["SQLite-vec"],
  "componentes": { "relevancia": 80, "utilidad": 70, "confiabilidad": 90, "novedad": 60 },
  "puntaje_final": 77,
  "nivel_memoria": "media",
  "modelo_evaluador": "qwen3.5-4b",
  "capturado": "2026-10-30T03:12:00-03:00"
}
```

(El repositorio del ejemplo es ficticio.)

**Campos obligatorios**: `url`, `disparador` (`tipo` ∈ `hueco` | `dominio_vigilado` | `peticion`), `titulo_original` o `titulo_es`, `resumen_es` (≥ 10 caracteres) y `componentes.relevancia` y `componentes.utilidad` (0–100). Todo lo demás es opcional.

**Lo que Python no te cree**: `confiabilidad`, `novedad`, `puntaje_final` y `nivel_memoria` que mande n8n se ignoran; Python los recalcula con la URL, la fecha de publicación y `sistema_aprendizaje.json`. `temas_nuevos` alimenta las propuestas de §7.4.

### 7.2 La nota resultante (`LLM-Memoria/Web/<slug>.md`)

```markdown
---
titulo: "Memoria de largo plazo para agentes con SQLite (demo)"
creado: <lo pone escritor.py>
actualizado: <lo pone escritor.py>
fuente: https://github.com/ejemplo/agent-memory-demo
confianza: 0.9
tags: ["ia-local", "agentes", "memoria"]
estado: borrador
origen: web
url_origen: https://github.com/ejemplo/agent-memory-demo
fecha_consulta: 2026-10-30
idioma_original: en
titulo_original: "agent-memory-demo"
disparador: "dominio_vigilado: agent memory"
objetivos: ["OBJ-002", "OBJ-004"]
nivel_memoria: media
puntaje: 77
vigente_hasta: 2027-01-28
---
## Resumen
Biblioteca de ejemplo que guarda memoria de largo plazo para agentes usando SQLite.

## Hechos
- Usa SQLite con búsqueda de texto
- Licencia MIT

## Entidades
[[SQLite]]

## Fuente
- URL: <https://github.com/ejemplo/agent-memory-demo>

## Advertencia
- Contenido obtenido de la web. Revisar antes de considerarlo conocimiento consolidado.
```

- Las claves `origen`, `url_origen`, `fecha_consulta` y `fuente` dejan la nota lista para importarse a las futuras tablas `knowledge_nodes` de Context.md (§4.5, §4.14.5) sin reprocesar.
- `vigente_hasta` ya lo entiende `recuperacion.py` (no inventé un campo nuevo para la expiración).
- `confianza` = confiabilidad de la fuente (0–1), igual que el resto de tu sistema; el puntaje final va aparte.

### 7.3 Puntaje y niveles

**Fórmula** (tu decisión): `0.40·relevancia + 0.30·utilidad + 0.20·confiabilidad + 0.10·novedad`

| Componente | Quién lo calcula | 🆕 Cómo |
|---|---|---|
| Relevancia | LLM 4B | 0–100 según objetivos, intereses y pesos |
| Utilidad | LLM 4B | 0–100: ¿se puede aplicar? ¿es gratis/open source/local? |
| Confiabilidad | Código | Dominio en `fuentes_confiables` = alta; desconocido = baja; en `descartar` = descarta |
| Novedad | Código | Antigüedad de la fecha de publicación y que la URL no se haya visto |

Dejar confiabilidad y novedad al código sigue tu regla "el código manda" y evita que un modelo pequeño opine sobre fuentes.

| Puntaje | Nivel | Retención (`perfil_usuario.memoria`) | `vigente_hasta` si hoy es 2026-10-30 |
|---|---|---|---|
| ≥ 85 | larga | 3650 días | 2036-10-27 |
| ≥ 70 | media | 90 días | 2027-01-28 |
| ≥ 50 | corta | 7 días | 2026-11-06 |
| < 50 | descartar | — | — (se registra `investigacion_no_util`) |

Ejemplo: relevancia 80, utilidad 70, confiabilidad 90, novedad 60 → 32 + 21 + 18 + 6 = 77 → nivel media.

**Promoción y degradación** (solo metadatos):
- `corta` → `media`: la misma URL o tema reaparece en 2 noches distintas con ≥ 70.
- `vencida`: pasó `vigente_hasta`; la nota sigue existiendo, solo se oculta en `recuperacion.py`.

Lo hace `ingesta_web.py --mantenimiento` con `actualizar_frontmatter(..., backup=False)`, porque tu README ya anota que los `.bak` se acumulan sin rotación.

### 7.4 Autoajuste: dónde viven los pesos

Tu regla de proyecto dice que ningún LLM modifica `Perfil/`. Para cumplir tu decisión (pesos y estadísticas automáticos) sin romper esa regla:

- 🆕 Los cambios automáticos se guardan en `.memoria\aprendizaje_web.json` (estado interno, escrito solo por Python). `intereses.json` y `objetivos.json` quedan como base que solo tocás vos.
- `peso_efectivo = clamp(peso_base + delta, peso_minimo, peso_maximo)` con tus parámetros (+0.05 por hallazgo útil, −0.02 por irrelevante, límites 0.1–2.0).
- Los pesos solo reparten el presupuesto de consultas del Planificador (más peso → más consultas).
- El archivo también guarda las URLs vistas (para no reevaluarlas cada noche), contadores y el progreso sugerido de objetivos.
- **Interés u objetivo nuevo = propuesta, no cambio.** Se anota en `LLM-Memoria/Revision/propuestas-web.md` con su evidencia (URLs) y vos decidís. Ejemplo: "Criptomonedas" → pedir aprobación; "Ollama" → ya cubierto.

## 8. Levantar todo con PowerShell

### 8.1 Requisitos

| Requisito | Cómo comprobarlo |
|---|---|
| Node.js 20.19 – 24.x | `node --version` |
| n8n instalado | `n8n --version` |
| LM Studio con el servidor activo | ver §6.1 |
| Entorno de Python del proyecto | `.\.venv\Scripts\python.exe --version` |

### 8.2 Orden de arranque
1. LM Studio (servidor activo y modelos cargados).
2. Comprobar memoria_vectorial.
3. n8n.

```powershell
cd F:\automatizaciones\homeLab\memoria_vectorial
.\.venv\Scripts\Activate.ps1
python config.py --check
python aprender_web.py --check        # muestra la lista blanca y los límites
```

### 8.3 Arrancar n8n

Si ya lo tenés instalado (tu Organizador ya corre), no lo reinstales. Si no:

```powershell
npm install n8n -g
```

La documentación de n8n indica que las instalaciones con npm quedan obsoletas desde n8n 3.0. Si en el futuro actualizás de versión mayor, revisá cómo migrar (Docker u otra vía).

En una ventana de PowerShell dedicada, cada vez que lo levantes:

```powershell
# 1) Habilita el nodo Execute Command (en n8n 2.x viene desactivado por defecto)
$env:NODES_EXCLUDE = "[]"

# 2) Windows no maneja los permisos 0600 que n8n exige sobre su archivo de configuración
$env:N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS = "false"

# 3) Zona horaria: sin esto n8n usa America/New_York y los cron no corren a tu hora
$env:GENERIC_TIMEZONE = "America/Montevideo"

# 4) Arrancar
n8n start
```

Luego abrí `http://localhost:5678`.

| Variable | Para qué |
|---|---|
| `NODES_EXCLUDE="[]"` | Reactivar Execute Command (lo usa tu Organizador y lo usará el flujo nuevo). Si tu flujo actual ya ejecuta, ya lo tenés resuelto |
| `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=false` | Evita el error de permisos en Windows |
| `GENERIC_TIMEZONE` | Hora de los disparadores Schedule/Cron |

Si querés que queden fijas para siempre (sin escribirlas cada vez), una sola vez:

```powershell
[Environment]::SetEnvironmentVariable("NODES_EXCLUDE", "[]", "User")
[Environment]::SetEnvironmentVariable("N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS", "false", "User")
[Environment]::SetEnvironmentVariable("GENERIC_TIMEZONE", "America/Montevideo", "User")
```

(Abrí una ventana nueva de PowerShell para que tomen efecto.)

### 8.4 Mantenerlo vivo de noche
- Los disparadores solo funcionan si n8n está corriendo y la PC está despierta. Dejá la ventana de PowerShell abierta (o minimizada).
- Para que la PC no se suspenda enchufada: `powercfg /change standby-timeout-ac 0`.
- 🆕 Después de aprobar, te preparo `iniciar_n8n.ps1` que comprueba Node, fija las variables y arranca n8n con un doble clic.

### 8.5 Importar y activar el workflow
1. En n8n: Workflows → Import from file y elegí el JSON (te lo entrego por partes en las fases 3–5).
2. Creá las credenciales que pida (token de GitHub).
3. Probá con **Execute workflow** (manual) antes de activar el cron.
4. Activá con el interruptor **Active**.

### 8.6 Prueba de humo (en orden)

```powershell
# a) LM Studio responde
Invoke-RestMethod http://127.0.0.1:1234/v1/models | Select-Object -ExpandProperty data | Select-Object id
# b) El proyecto está sano
cd F:\automatizaciones\homeLab\memoria_vectorial
python config.py --check ; python guardian.py --una-vez
# c) n8n responde: abrir http://localhost:5678 en el navegador
```

### 8.7 Detener

`Ctrl + C` en la ventana de n8n. Al vigilante de índices: `.\iniciar.ps1 -Detener`.

## 9. Operación diaria

| Hora | Qué corre | Dónde |
|---|---|---|
| 01:12 | Organizador F:\ (el actual) | n8n |
| 03:00 🆕 | Aprendizaje web | n8n → Python |
| Mañana | Revisás el resumen | Obsidian |

**Qué mirar**: `LLM-Memoria/estado.md` (o `python estado.py`), `LLM-Memoria/Web/` (notas nuevas), `LLM-Memoria/Revision/propuestas-web.md` (lo que espera tu aprobación).

**Cómo aprobar una propuesta**: hasta que ajustemos `perfil.py` (H2), editás a mano `Perfil\intereses.json` o `Perfil\objetivos.json` y guardás.

**Si algo sale mal**: el estado del buzón (`rechazados\`), `Sistema\incidencias.json` y `python guardian.py --una-vez`. Para volver atrás: `python backup.py --listar` y `--restaurar` (restaura en una carpeta aparte, nunca pisa la bóveda).

⚠️ **Solapamiento**: si el Organizador tarda más de 1 h 48 min, el aprendizaje web arrancaría mientras sigue usando LM Studio. Opciones en §12 (decisión 7).

## 10. Reglas de seguridad
- Contenido web = dato. El prompt lo delimita (`CONTENIDO_NO_CONFIABLE`) y se ignora cualquier orden que traiga.
- **Jamás** se interpola texto web dentro de un comando de PowerShell. El Organizador hace bien en pasar el JSON en base64; el flujo nuevo escribe los paquetes con un nodo que no pasa por el intérprete de comandos y solo recibe rutas que construye el propio flujo (hash de la URL, nunca el título).
- Lista blanca única (`reglas.json` → `web.dominios_permitidos`) para n8n y para `navegador.py`.
- Límites: 20 hallazgos/noche; `navegador.py` conserva sus tope por hora y por día.
- Los modelos no tocan `Perfil/`. Proponen; vos aprobás.
- Todo queda en `Sistema/auditoria.jsonl` (lo hace `escritor.py`).
- El token de GitHub es una credencial de n8n, no una variable de entorno: en n8n 2.x el nodo Code no puede leer variables de entorno por defecto.

## 11. Plan de entrega por fases

| Fase | Entregable | Archivos | Criterio de aceptación |
|---|---|---|---|
| 0 ✅ | Arreglar los 4 puntos de §3.1 | perfil_usuario.json, intereses.json, sistema_aprendizaje.json, reglas.json (lista blanca), perfil.py, analisis.py (+ sus tests en tests/) | `perfil.cargar()` ve tus intereses y objetivos; `analisis.py --json` devuelve huecos; `python -m pytest` pasa |
| 1 ✅ | ingesta_web.py y formato del buzón | 🆕 ingesta_web.py | Un JSON de prueba en el buzón produce una nota válida, auditada y se mueve a `procesados\` |
| 2 | Workflow n8n, parte 1: planificar, buscar y filtrar | 🆕 JSON de n8n | 2–3 consultas reales devuelven candidatos nuevos y sin repetir |
| 3 | Parte 2: pre-filtro, extracción, evaluación y puntaje | 🆕 JSON de n8n | Una corrida manual deja ≤ 5 paquetes en el buzón con puntaje coherente |
| 4 | Parte 3: ingesta, indexado, ajuste de pesos, propuestas y resumen | 🆕 JSON de n8n | Corrida completa: notas en LLM-Memoria/Web, indexadas, resumen en Obsidian |
| 5 | Operación | 🆕 iniciar_n8n.ps1 (opcional) | 3 noches seguidas sin intervención |

`iniciar.ps1`, `escritor.py`, `navegador.py`, `indexer.py` y el Organizador **no se modifican**.

Fuera de alcance: SearXNG o cualquier Docker, reescribir `aprender_web.py`, tocar el Organizador, las fases CORE ↔ BRAIN de Context.md y la tabla `knowledge_nodes`.

### 11.1 Qué se hizo en las fases 0 y 1 y cómo usarlo

**Archivos** (copialos sobre los tuyos; antes, `python backup.py --crear`):

| Archivo | Dónde va | Cambio |
|---|---|---|
| Perfil\perfil_usuario.json | F:\automatizaciones\homeLab\Perfil\ | Anidado corregido; pesos 40/30/20/10; sin umbrales ni búsqueda duplicados |
| Perfil\intereses.json | ídem | + MCP, SQLite-vec, memoria para agentes, Modelos open source, React, HTML; Python pasa a principal; pesos por defecto |
| Perfil\objetivos.json | ídem | + `escala_progreso` (0–100) |
| Perfil\criterios_busqueda.json | ídem | + tus RSS, releases Atom, documentación, keywords y límites por ciclo |
| Perfil\sistema_aprendizaje.json | ídem | + tabla de confiabilidad por dominio y tramos de novedad |
| Sistema\reglas.json | ...\homeLab\Sistema\ | Lista blanca ampliada; w3schools.com fuera de prohibidos |
| perfil.py, analisis.py | ...\memoria_vectorial\ | Entienden el formato nuevo (y siguen entendiendo el viejo); analisis.py cuenta LLM-Memoria/Web y ya no deja comillas en los tags |
| ingesta_web.py 🆕 | ídem | El módulo del buzón |
| tests\test_perfil_formato_nuevo.py, tests\test_ingesta_web.py 🆕 | ...\memoria_vectorial\tests\ | 43 tests nuevos |

**Orden para aplicarlo**:

```powershell
cd F:\automatizaciones\homeLab\memoria_vectorial
.\.venv\Scripts\Activate.ps1
python backup.py --crear                      # 1) copia de seguridad
# 2) copiá los archivos de la tabla
python config.py --check                      # 3) la configuración sigue válida
python ingesta_web.py --check                 # 4) pesos suman 100, umbrales en orden, buzón creado
pip install pytest ; python -m pytest         # 5) esperado: 129 tests en verde
python analisis.py --json                     # 6) ahora `huecos` ya no viene vacío
```

**Comandos de ingesta_web.py** (toda la salida JSON va en ASCII para que la consola de Windows no la rompa):

| Comando | Para qué |
|---|---|
| `python ingesta_web.py --check` | Valida reglas y muestra el buzón (código 2 si hay errores) |
| `python ingesta_web.py --ingerir --dry-run` | Muestra qué publicaría, sin escribir ni mover nada |
| `python ingesta_web.py --ingerir [--max 5]` | Publica el buzón. Tope por defecto: `limites_por_ciclo.max_guardados` |
| `python ingesta_web.py --mantenimiento [--dry-run]` | Promueve corta → media (2 noches con ≥ 70) y cuenta las vencidas |
| `python ingesta_web.py --contexto` | JSON para el Planificador: pesos efectivos, objetivos activos, keywords, huecos, dominios, URLs vistas |
| `python ingesta_web.py --resumen` | Resumen de la última ingesta (para el aviso diario) |
| `python ingesta_web.py --rechazar-propuesta "tema"` | Descarta una propuesta de interés nuevo |

**Prueba de punta a punta sin n8n** (sirve para ver el contrato con tus propios ojos): guardá esto como `F:\automatizaciones\homeLab\memoria_vectorial\.memoria\entrada_web\prueba.json`:

```json
{"url":"https://github.com/ejemplo/demo","disparador":{"tipo":"hueco","detalle":"Open WebUI"},
 "titulo_original":"demo","resumen_es":"Ejemplo de resumen para probar la ingesta.",
 "componentes":{"relevancia":85,"utilidad":80},"tags":["open webui"]}
```

y ejecutá `python ingesta_web.py --ingerir`. Resultado esperado: puntaje 81, nivel media, una nota en `LLM-Memoria\Web\demo.md` y el JSON movido a `entrada_web\procesados\`. Después borrá la nota de prueba (muévela a la papelera de Obsidian) y limpiá su entrada en `.memoria\aprendizaje_web.json`, o te quedará como "URL ya vista".

**Qué se comprobó** (todo con simuladores, sin LM Studio ni red): los 86 tests originales siguen en verde; 43 tests nuevos cubren el cálculo del puntaje con el ejemplo de §7.3, las fechas de vigencia, el recálculo de confiabilidad y novedad, 9 motivos de rechazo, duplicados (incluso dentro del mismo ciclo), tope por ciclo, pesos y límites, propuestas, promoción, dry-run y la salida ASCII. Lo que **no** se probó: n8n, LM Studio, tu bóveda real ni Windows. La primera corrida real conviene hacerla con `--dry-run`.

Una cosa a tener en cuenta: `--contexto` consulta el índice para calcular los huecos; si todavía no existe, lo crea vacío.

## 12. Decisiones tomadas (30/10/2026)

Aprobaste todas las recomendadas y completaste las pendientes:

| # | Decisión | Resultado |
|---|---|---|
| 1 | Quién escribe la nota | Python (ingesta_web.py) desde el buzón |
| 2 | Embeddings | Solo indexer.py, al final |
| 3 | Pesos automáticos | En `.memoria\aprendizaje_web.json`, no en `Perfil/` |
| 4 | Esquema de intereses y objetivos | perfil.py y analisis.py adaptados (hecho) |
| 5 | Pesos de evaluación | 40/30/20/10, una sola fuente por dato (hecho) |
| 6 | Confiabilidad y novedad | Las calcula el código (hecho) |
| 7 | Horario | 03:00, y el flujo comprueba que el Organizador terminó antes de empezar (se construye en la parte 1) |
| 8 | Lista blanca | Ampliada (hecho) |
| 9 | Hacker News y r/LocalLLaMA | Activados (pediste incluirlos) |
| 10 | Token de GitHub | Lo creás vos (PAT gratuito, solo lectura) y lo cargás como credencial en n8n |
| 11 | Peso de intereses sin peso | principales 0.8, secundarios 0.5 (hecho) |
| 12 | Escala de progreso | 0–100 (hecho) |
| 13 | RSS y temas | Cargados en criterios_busqueda.json e intereses.json (hecho) |

Cosas que conviene que sepas de tus elecciones:
- `w3schools.com` estaba en `dominios_prohibidos` de `reglas.json`. Lo saqué de ahí para poder usarlo. Su confiabilidad queda en "media" (60) y no en "alta".
- Hacker News, r/LocalLLaMA y Phoronix están marcados `ruido: alto`: el Investigador los filtrará más duro. Reddit suele rechazar a los clientes sin User-Agent; el nodo HTTP de n8n deberá mandar uno.
- No pude comprobar que las URLs de los feeds respondan (mi entorno no sale a esos sitios). Si alguna da error, la parte 1 la saltea y la anota; no detiene la corrida.

## 13. Fuentes consultadas
- n8n — Instalación con npm (Node 20.19–24.x, `npm install n8n -g`, `n8n start`, puerto 5678, obsoleto desde 3.0)
- n8n — Cambios incompatibles de la 2.0 (Execute Command desactivado, acceso a variables de entorno en Code, permisos del archivo de configuración)
- n8n — Bloquear o habilitar nodos (`NODES_EXCLUDE`)
- n8n — Zona horaria (`GENERIC_TIMEZONE`, por defecto `America/New_York`)
- Tu proyecto: README.md, Context.md, config.py, escritor.py, navegador.py, aprender_web.py, perfil.py, analisis.py, llm.py, n8n_puente.py, iniciar.ps1, Sistema/reglas.json, Sistema/guardian.json, PARCHES/ y los 5 JSON de Perfil/.
