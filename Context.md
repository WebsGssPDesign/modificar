# `Context.md` — v4 completo

Listo para guardar en `F:\automatizaciones\homeLab\memoria_vectorial\Context.md`.

---

```markdown
# Context.md — Fuente única de verdad (CORE ↔ BRAIN)

> **Propósito:** que yo o cualquier IA podamos retomar el trabajo sin releer miles
> de líneas de código. Solo se registra aquí lo **estructural, estratégico y de
> estado actual**. Lo detallado vive en el código y en git; lo efímero se descarta.
>
> **Documento derivado:** `docs/integracion_CORE_BRAIN.md` amplía contexto.
> Si hay discrepancia, **gana este archivo**.

Última actualización: sesión de diseño inicial + inversión de fases + modelo de transformación (9 verbos) + vistas derivadas + indicadores de éxito + política de aprendizaje web activo.
Estado global: **Diseño cerrado. Implementación no iniciada. Pendientes 6 confirmaciones.**

---

## 1. Identidad y misión

### 1.1 Tabla de proyectos

| Proyecto | Rol | Pregunta que responde | Ruta |
|---|---|---|---|
| **CORE** (Segundo Cerebro Digital) | **Productor** de información consolidada. Descubre, clasifica, organiza físicamente. | *¿qué tengo, dónde está y qué contiene?* | `F:\_segundo_cerebro` |
| **BRAIN** (Memoria Vectorial) | **Capa de comprensión persistente**. Mantiene continuidad de contexto del usuario. Expone por MCP. | *¿qué significa lo que tengo, qué aprendí, qué me falta y cómo pienso?* | `F:\automatizaciones\homeLab\memoria_vectorial` |

### 1.2 Misión única de BRAIN

> **Mantener la continuidad del contexto del usuario para que ninguna IA tenga
> que re-explicarse lo que ya se sabe.**

Todo lo demás —aprender, perfilar, detectar huecos, proponer, evolucionar,
investigar en web— es **capacidad al servicio de la misión**, no misión en sí.
Si una capacidad no contribuye a reducir el contexto que el usuario debe
re-explicar, **no pertenece a BRAIN** o debe justificarse explícitamente como
soporte indirecto.

### 1.3 Principio operativo rector (invariante conductual)

> **Todo lo que entra en BRAIN debe cambiar el estado del conocimiento existente
> o evidenciar por qué no pudo hacerlo.**
>
> Ninguna ingesta es silenciosa. Si un input no dispara al menos una transformación,
> se registra como `input_no_transformado` y cuenta como deuda explícita.

### 1.4 Capacidades (derivadas de la misión, no fines en sí)

| Capacidad | Contribuye a la misión porque… |
|---|---|
| Recordar (memoria) | evita re-explicar hechos ya conocidos |
| Comprender (dominios/proyectos) | da contexto estructurado, no fragmentos |
| Aprender (transformaciones primarias) | actualiza la comprensión con cada input |
| **Aprender activamente vía web** (§4.14) | cierra huecos detectados sin esperar input pasivo |
| Perfilar | captura preferencias estables que reducen re-explicación |
| Detectar huecos | evidencia lo que el usuario tendría que explicar y BRAIN no sabe |
| Proponer | sugiere qué aprender para reducir futura re-explicación |
| Evolucionar (fusionar/archivar/consolidar) | mantiene la comprensión útil, no acumulativa |

**Regla de oro:** si una capacidad nueva no encaja en esta tabla con una razón
concreta, se rechaza o se pospone.

### 1.5 Cuatro capas (no confundir)

```
CORE   = memoria documental    (qué tengo)
Vault  = memoria humana        (qué decidí yo)
BRAIN  = memoria conceptual    (qué significa / qué aprendí / qué me falta)
LLM    = motor de razonamiento (qué hago con ello)
```

- **Dirección única de integración:** CORE → BRAIN. Nunca bidireccional.
- CORE **no conoce** la existencia de BRAIN.
- Ambos viven y mueren por separado.
- **Aviso de framing:** BRAIN no es satélite de CORE. CORE es **una de tres
  fuentes** (vault, web, disk). La integración CORE → BRAIN es un proyecto
  *dentro* de BRAIN, no la razón de ser de BRAIN.

---

## 2. Invariantes (no negociables)

**Arquitectónicos:**

1. **Cero fusión** de bases de datos, carpetas, configuraciones o ciclos de vida.
2. **Cero escritura cruzada.** `cerebro.db` → read-only desde BRAIN.
   `indice.sqlite` → jamás tocado por CORE.
3. **Cero duplicación de conocimiento** entre ambos.
4. CORE **no** sabe que BRAIN existe. BRAIN **puede** vivir sin CORE (fallback limpio).
5. **Vault Obsidian es soberana.** Si hay duplicado Vault ↔ CORE/disk, **gana Vault**.
6. Prohibido:
   - recalcular embeddings válidos de CORE;
   - copiar `cards/` dentro de la bóveda;
   - reindexar documentos ya consolidados por CORE;
   - que BRAIN escriba en `cerebro.db`;
   - que CORE escriba en `indice.sqlite`.
7. **Un solo `mcp_server.py`.** No se crean servidores MCP paralelos.
8. Cualquier diseño con dependencia mutua, sync bidireccional, escritura cruzada o DB compartida = **fallo arquitectónico** → rechazar.

**Conductual:**

9. **Ninguna ingesta silenciosa.** Todo input debe disparar ≥1 transformación
   de §4.11–§4.12, o registrarse como `input_no_transformado` con el motivo.
10. **Misión única.** Toda capacidad nueva debe justificar su contribución a §1.2.
11. **Investigación web nunca aleatoria.** Toda consulta web requiere un disparador
    válido (§4.14.1). Aprender por aprender está prohibido. La web se usa para
    reducir incertidumbre, no para acumular.

---

## 3. Inventario existente (reutilizar, no reescribir)

### CORE (`F:\_segundo_cerebro`)
- `cerebro.db`
- `inventory`
- embeddings (válidos → se reutilizan tal cual)
- `cards/`
- `folder summaries` + `project summaries` (producidos por `consolidator.py`)

### BRAIN (`F:\automatizaciones\homeLab\memoria_vectorial`)
- Módulos: `memoria.py` (`buscar_hibrido()`), `aprender.py`, **`aprender_web.py`**,
  `entidades.py`, `crear_skills.py`, `perfil.py`, `recuperacion.py`, `mcp_server.py`,
  `config.py`, `estado.py`, `escritor.py`, `llm.py`, `metricas.py`, **`navegador.py`**,
  `util.py`, `guardian.py`, `heartbeat.py`, `incidencias.py`, `eventos.py`,
  `tablero.py`, `analisis.py`.
- Persistencia: `.memoria/indice.sqlite`, `.memoria/aprendido.json`,
  `.memoria/skills.json`, **`.memoria/web.json`**, `.memoria/pipeline.log`.
- Directorios: `Perfil/`, `Sistema/`, vault `LLM-Memoria/`, `memoria_vectorial/`,
  `Diario/`, `Context/`, `assets/`, `docs/`.

**Nota:** snapshot `estructura.txt` es obsoleto. La copia
`F:\automatizaciones\git\59cf75c7-...` fue **eliminada** y no debe considerarse.

**Nota:** `huecos()`, `perfil.py`, `crear_skills.py`, `analisis.py`,
`aprender_web.py` y `navegador.py` ya existen. §4.13, §4.4.2 y §4.14 los
formalizan. A partir de ahora son ciudadanos de primera clase, no afterthought.

---

## 4. Arquitectura de integración (diseño cerrado, sin implementar)

### 4.1 Nueva capa: `fuentes/disco.py` (solo lectura)

- Único punto de contacto con `cerebro.db`. Abre en **modo `ro`** (SQLite URI).
- **Lee únicamente** summaries de carpeta y de proyecto + embeddings asociados.
- **Ignora** archivos individuales, chunks sueltos, redundancias.
- API interna tipada:
  - `listar_dominios() -> list[DominioDisco]`
  - `listar_proyectos() -> list[ProyectoDisco]`
  - `obtener_documento(id) -> DocumentoDisco`
- Cada objeto normalizado contiene: `titulo`, `resumen`, `origen_absoluto`,
  `card_path`, `embedding_vector` (o `None`), `modelo`, `dimension`,
  `conceptos[]`, `metadatos{}`.
- **Nunca** importa el `escritor` de BRAIN. **Nunca** escribe.

### 4.2 Nuevo módulo: `disk_sync.py` (sincronización incremental)

- Estado en `.memoria/disk_sync_state.json`:
  `{ id_elemento: { hash, embedding_hash, last_seen, activo } }`.
- Reglas:
  - `hash` sin cambios → **skip** (idempotencia).
  - `hash` cambió → **update**.
  - desapareció de CORE → `activo=False` (no destruir conocimiento derivado).
- Reversible, incremental, log en `.memoria/pipeline.log`.
- Solo opera sobre **summaries**. Nunca sobre `cards/` individuales salvo
  justificación documentada.
- **Reutiliza embedding de CORE** si `modelo` y `dimension` son compatibles.
  Si no → genera local **registrando el motivo**.
- **Obligación §2.9:** cada lote reporta cuántos inputs dispararon transformación
  y cuántos quedaron `input_no_transformado`.

### 4.3 Nueva fuente: `source='disk'`

- BRAIN tiene 3 procedencias: `vault` (default, soberana), `web`, `disk`.
- `buscar_hibrido(..., ambito='vault'|'web'|'disk'|'all')`.
- **Default: `vault`** hasta validar integración completa.
- La fuente `web` tiene política propia en **§4.14** (no es pasiva; es aprendizaje
  activo con disparadores, validación y trazabilidad).

### 4.4 Capa conceptual — eje de conocimiento + vistas derivadas

**Corrección clave (v3):** `Perfil` y `Skill` **no son hijos** de `Proyecto`.
Son **vistas derivadas** del conocimiento base, materializadas por agregación.

#### 4.4.1 Eje de conocimiento (padre-hijo real)

```
Documento → Chunk → Hecho → Entidad → Dominio → Proyecto
```

Relaciones: `contains` (descendente) y `belongs_to` (ascendente).
Únicos nodos con jerarquía padre-hijo.

- **Dominio** = conocimiento consolidado estable sobre un área temática.
- **Proyecto** = agrupación de dominios relacionados, con ciclo de vida (§4.9).
- **Prioridad de recuperación:** `Proyecto > Dominio > Entidad > Hecho > Chunk`.

#### 4.4.2 Vistas derivadas (no jerarquía)

```
Perfil  = agregación inferida de hechos/entidades/dominios/proyectos
Skill   = agregación inferida de hechos/entidades sobre una práctica concreta
```

- Se materializan como nodos en `knowledge_nodes` con `origen='derived'`.
- Relación con el eje base: **`derived_from`** (no `contains`/`belongs_to`).
- Pueden agregar nodos de **múltiples proyectos**; no tienen padre único.
- **No auto-promoción:** un `fact` no “sube” a `skill`. Una `skill` se **deriva**
  cuando la política de consolidación (§4.12) lo justifica; hasta entonces no existe.
- `Perfil` y `Skill` **no compiten** en la prioridad de recuperación base; se
  sirven por tools específicas (`perfil()`, `skills()`), no por `buscar_hibrido`
  por defecto (aunque pueden aparecer vía `ambito='all'`).

#### 4.4.3 Eje meta (fuera de la jerarquía)

```
gap → propuesta
```

No recuperable por `buscar_hibrido`. Solo vía `huecos()` / `propuestas()`.

#### 4.4.4 Regla de inversión (comprensión como criterio de aceptación)

- Una fase de ingesta que solo produce `document`/`chunk` **ha fallado**, aunque
  los tests técnicos pasen.
- **Fase 1:** cada summary expone material clasificable como dominio o proyecto.
  Si no → `no_clasificable` documentado (nunca se finge).
- **Fase 2:** cada lote produce **≥1 transformación de §4.11** con trazabilidad.
- CORE alimenta primero `Dominio`/`Proyecto`. Sin auto-promoción a `fact`/`skill`.
- **Detección de patrones** es objetivo **aspiracional**; requiere ground truth
  (§4.9) y confianza (§4.8). Sin ambos, `analisis.py` produce ruido elegante y
  **no se expone por MCP**.

### 4.5 Nuevas tablas en `indice.sqlite` (ampliación, no sustitución)

- **`knowledge_nodes`**: `document`, `chunk`, `fact`, `entity`, `domain`,
  `project`, `profile`, `skill`, `gap`, `propuesta`. Campos obligatorios desde
  día uno: `confianza`, `vigente_desde`, `vigente_hasta`, `superseded_by`,
  `origen`, `archivado`, `absorbido_por`, `derived_from` (vistas), y para nodos
  con `origen='web'`: **`url_origen`**, **`fecha_consulta`**, **`fuente`**.
- **`knowledge_relations`**: `contains`, `belongs_to`, `depends_on`,
  `generated_from`, `related_to`, `contradicts`, `confirms`, `amplia`,
  `fusionado_en`, `consolida`, `origina`, `derived_from`.
- Todo importado desde CORE registra `generated_from source='disk'` + origen.
- Todo derivado de web registra `origen='web'` + `url_origen` + `fecha_consulta`
  + `fuente` (§4.14.5). **Ningún nodo web puede perder referencia al origen.**

### 4.6 Anti-duplicados Vault ↔ disk

- Detección por similitud coseno sobre embeddings.
- Colisión → **gana Vault**. Nunca dos hechos equivalentes.
- Objetivo: **consolidar**, no acumular.

### 4.7 MCP transparente

- `mcp_server.py` único.
- `buscar_memoria()`, `conocimiento()`, `huecos()`, `propuestas()`, `perfil()`,
  `skills()`, `estado_memoria()` y futuras tools incorporan `source='disk'` y
  `origen='web'` **internamente**.
- `buscar_memoria` **nunca** devuelve `gap`/`propuesta` (meta, §4.13).
- `perfil()` y `skills()` sirven vistas derivadas (§4.4.2), no el eje base.
- Tools de aprendizaje web (Fase 7): `investigar(tema)`, `marcar_watchlist(dominio)`,
  `estado_investigacion()`.
- El agente **no distingue origen** salvo petición explícita.

### 4.8 Política de contradicción, recencia y confianza

Todo nodo `fact`, `entity`, `domain`, `profile`, `skill` lleva desde su creación:

- `confianza` (0.0–1.0), `vigente_desde`, `vigente_hasta` (`NULL`=vigente),
  `superseded_by`, `origen` (`vault`|`web`|`disk`|`derived`), `archivado` (bool).

**Reglas:**

1. **Nunca se borra por contradicción.** Se marca `vigente_hasta` + relación `contradicts`.
2. **Resolución por confianza y recencia:**
   - `confianza_nuevo ≥ confianza_viejo + umbral` → gana nuevo (`superseded_by`);
   - similares → ambos vigentes, `conflicting=true` para revisión;
   - el viejo **nunca desaparece** (auditoría).
3. **Caducidad:** `preferencia` caduca a los N días sin refuerzo. Pasa a
   `vigente_hasta`; no aparece salvo `ambito='all'`.
4. **Refuerzo** (`confirmar`): sube `confianza`, renueva `vigente_desde`, relación `confirms`.
5. **Recuperación:** `buscar_hibrido` solo devuelve `vigente_hasta IS NULL` y
   `archivado=false`. Recuperación histórica explícita.
6. **Trazabilidad:** todo cambio en `pipeline.log` y `knowledge_relations`.

**Prohibido:** añadir campos de vigencia/confianza/archivado “más adelante”.

### 4.9 Ground truth de ciclo de vida de proyecto

**Cada `project` debe tener:** `estado` (`active`|`paused`|`completed`|`abandoned`|
`absorbed`), `fecha_inicio`, `fecha_ultima_actividad`, `fecha_cierre`, `motivo_cierre`,
`absorbido_por`, `fuente_estado` (`manual`|`inferido`).

**Regla dura:** patrones solo sobre `fuente_estado=manual`. Los `inferido` sirven
para búsqueda/contexto, **nunca** para `analisis.py` ni conclusiones expuestas.

**Decisión de Fase 0:** (a) etiquetar en CORE, (b) etiquetado manual desde BRAIN
vía MCP, (c) aplazar detección. **Recomendación: (b)**.

### 4.10 Modelo de transformación del conocimiento

BRAIN opera **9 transformaciones** en dos grupos. Toda ingesta (vault, disk o
web) debe disparar ≥1 (§2.9). Si no puede → `input_no_transformado` con motivo.

| Grupo | Cuándo | Verbos | Sección |
|---|---|---|---|
| **Primarias** | Diario | `confirmar`, `contradecir`, `ampliar`, `crear`, `detectar_hueco`, `proponer` | §4.11 |
| **Evolutivas** | Maduración | `fusionar`, `archivar`, `consolidar` | §4.12 |

**Regla de maduración:** las evolutivas **no son entregables de Fases 1–7**.
Requieren volumen y confianza estable. Se abordan en **Fase 8** (§5).

### 4.11 Transformaciones primarias (diarias)

| Verbo | Efecto | Registro |
|---|---|---|
| `confirmar` | sube `confianza`, renueva `vigente_desde` | `confirms` + log |
| `contradecir` | aplica §4.8 | `contradicts` + log |
| `ampliar` | añade nodo + `belongs_to`/`amplia` a nodo existente | log |
| `crear` | crea `domain`/`project`/`fact`/`entity` nuevo | log + trazabilidad |
| `detectar_hueco` | crea nodo `gap` (§4.13) | log |
| `proponer` | deriva `propuesta` desde `gap` (§4.13) | `origina` + log |

**Mapeo ingesta → verbo:** cada lote de `disk_sync` o de investigación web
reporta qué verbo(s) disparó cada input. No son mutuamente excluyentes (un input
puede confirmar y detectar hueco).

### 4.12 Transformaciones evolutivas (maduración)

| Verbo | Efecto | Requisito |
|---|---|---|
| `fusionar` | dos `domain`/`entity`/`project` con solapamiento alto colapsan. El secundario recibe `absorbido_por=primario` + `archivado=true`; relaciones repuntadas con `fusionado_en`. | Similitud ≥ umbral + auditoría. Nunca automático. |
| `archivar` | nodo sigue **cierto** (`vigente_hasta IS NULL`) pero no compite por atención activa (`archivado=true`). Distinto de contradecir (sigue válido) y de caducar (sigue vigente indefinidamente). Reversible. | Regla configurable + revisión. |
| `consolidar` | N nodos de menor nivel se condensan en 1 de mayor nivel (ej. 100 `fact` → 1 `skill`). Nodo consolidado guarda `consolida` hacia origen. Los origen **no se borran**: `archivado=true`. **Requiere `derived_from`** (§4.4.2). | Patrón estable + `confianza` agregada ≥ umbral + `analisis.py` maduro. |

**Reglas comunes:**

1. **Nunca automáticas sin auditoría.** Evidencia en `pipeline.log`.
2. **Reversibles.** `fusionar`/`consolidar` deshacibles; `archivar` trivialmente.
3. **No destruyen origen.** Nodos absorbidos/consolidados quedan archivados.
4. **Explícitas en recuperación histórica.** `ambito='all'` los devuelve; default no.

### 4.13 Huecos y propuestas (meta-capa)

**`gap`** (nodo meta, no recuperable por `buscar_hibrido`):
`dominio_ref`, `descripcion`, `tipo` (`falta_hecho`|`falta_entidad`|
`falta_relacion`|`contradiccion_sin_resolver`|`pregunta_sin_respuesta`),
`prioridad`, `vigencia`.

**`propuesta`** (nodo meta): `gap_ref`, `accion_sugerida` (`leer`|`preguntar`|
`investigar_web`|`consolidar`), `justificacion`, `estado` (`pendiente`|`aceptada`|
`rechazada`|`ejecutada`).

**Reglas:**

1. Un `gap` sin `propuesta` es **deuda explícita** (visible en `estado_memoria`).
2. Propuestas se rankean por `impacto × frecuencia × novedad`.
3. Se exponen por MCP (`huecos()`, `propuestas()`) pero **nunca se auto-ejecutan**.
4. Un `gap` se cierra al añadir conocimiento o marcarse `no_aplica`.
5. Son **capa meta**: `buscar_hibrido` los ignora por diseño.
6. Un `gap` de consolidación se resuelve vía `consolidar` (§4.12).
7. Un `gap` de `falta_hecho`/`falta_entidad` puede resolverse vía aprendizaje web
   si el disparador lo justifica (§4.14.1).

### 4.14 Aprendizaje Web Activo

**Propósito.** La web no es fuente pasiva: es **mecanismo de expansión controlada
del conocimiento**. BRAIN puede usar la web para confirmar, resolver
contradicciones, ampliar dominios, crear dominios nuevos, reducir huecos y
actualizar contexto de temas conocidos. **No acumula artículos ni enlaces**;
transforma información externa en comprensión reutilizable alineada con §1.2.

#### 4.14.1 Principio de activación

La investigación web **nunca es aleatoria**. Debe existir ≥1 disparador válido:

1. `gap` detectado (§4.13).
2. `propuesta` aceptada con `accion_sugerida='investigar_web'`.
3. `dominio` marcado como incompleto (`watchlist=true` + revisión vencida).
4. `contradicción` pendiente (`conflicting=true` sin resolver).
5. **Petición explícita del usuario** vía MCP (`investigar(tema)`).
6. Actualización periódica de un **dominio vigilado**.

Sin disparador válido → **no se inicia aprendizaje web** (invariante §2.11).

#### 4.14.2 Dominios vigilados (watchlist)

- Campo `watchlist` (bool) en nodos `domain` (o config global si el dominio aún
  no existe).
- Candidatos: `IA local`, `LLM`, `Qwen`, `LM Studio`, `Agentes IA`, `Embeddings`,
  `Automatización`… (lista configurable en `config.py`).
- La frecuencia de revisión periódica se define en `config.py` por dominio.

#### 4.14.3 Flujo de aprendizaje web

```
Gap / Propuesta / Watchlist / Contradicción / Petición
        ↓
Investigación web (navegador.py + aprender_web.py)
        ↓
Extracción
        ↓
Validación
        ↓
Transformación (§4.11)
        ↓
Persistencia (knowledge_nodes, origen='web')
```

Toda información obtenida **debe** terminar en ≥1 transformación de §4.11
(`confirmar`/`contradecir`/`ampliar`/`crear`/`detectar_hueco`/`proponer`).
Si no → `input_no_transformado` en `pipeline.log`.

#### 4.14.4 Reglas de validación

1. **Conservar referencia a la fuente original.** Sin URL no hay conocimiento.
2. **Nunca almacenar el artículo completo** si no es necesario. Se guardan:
   hechos derivados, entidades, relaciones, resumen consolidado, `url_origen`,
   `fecha_consulta`.
3. **Múltiples fuentes coinciden** → sube `confianza` (`confirms`).
4. **Múltiples fuentes discrepan** → aplica §4.8 (`contradicts`, `conflicting=true`
   si no hay resolución clara).
5. **Una sola fuente** → `confianza` baja por defecto; candidata a refuerzo.

#### 4.14.5 Procedencia (trazabilidad web)

Todo nodo derivado de web registra obligatoriamente:

- `origen='web'`
- `url_origen` (no nulo)
- `fecha_consulta`
- `fuente` (dominio del sitio o identificador de la fuente)

**Ningún nodo derivado de web puede perder referencia al origen.** Si la URL
desaparece o queda inaccesible, el nodo se marca `fuente_caida=true` (no se
borra) y se degrada su `confianza`.

#### 4.14.6 Actualización de conocimiento existente

Cuando una investigación afecta a un nodo existente (`fact`, `domain`, `entity`,
`project`, `profile`, `skill`), la información nueva **no reemplaza
automáticamente** la antigua. Se aplican §4.8: `confianza`, `vigencia`,
`contradicción`, `recencia`.

#### 4.14.7 Restricción crítica

> **BRAIN no aprende porque algo sea nuevo. Aprende porque algo reduce
> incertidumbre.** Novedad ≠ conocimiento útil.

Toda investigación web debe justificar ≥1 de los siguientes efectos:

1. Reduce un `gap`.
2. Aumenta `confianza` de un nodo existente.
3. Resuelve una contradicción.
4. Amplía un dominio.
5. Crea un dominio nuevo justificado.
6. Actualiza conocimiento desactualizado (`vigente_hasta` vencido o `fuente_caida`).

Si no ocurre ninguno → **la información se descarta** (no se persiste, se
registra en `pipeline.log` como `investigacion_no_util`).

#### 4.14.8 Relación con la misión

La investigación web solo se considera exitosa si contribuye indirectamente a
§1.2:

- **Aprender por aprender** = prohibido.
- **Aprender para reducir incertidumbre** = permitido.
- **Aprender para reducir re-explicación futura** = objetivo.

---

## 5. Estado actual del trabajo

### Fase
**Fase 0 — Confirmaciones previas a escribir código.** Nada implementado.

### Pendientes bloqueantes para Fase 1 (6)

**Originales (4):**

1. **Rutas reales** confirmadas: `F:\_segundo_cerebro`, `F:\automatizaciones\homeLab\memoria_vectorial`.
2. **Ruta exacta de `cerebro.db`** (raíz vs `data/` vs `.cerebro/`).
3. **`consolidator.py`**: ¿existe? ¿ruta? ¿fase?
4. **Esquema de `cerebro.db`**: si no está a mano → adaptador defensivo con
   `PRAGMA table_info` + mapeo en `config.py`.

**Nuevos (2):**

5. **Ground truth de ciclo de vida de proyecto** (§4.9): decidir (a)/(b)/(c).
   Bloqueante para Fase 4; decidir en Fase 0.
6. **Política de contradicción, recencia, confianza y archivado** (§4.8): confirmar
   campos y tipos de relación. Bloqueante para Fase 3.

### Plan de fases

| Fase | Contenido | Criterio de aceptación | Dependencia |
|---|---|---|---|
| **0** | Confirmar 6 pendientes + leer esquema real + decidir §4.8/§4.9 | Informe con 6 respuestas + 2 decisiones binarias | — |
| **1** | `fuentes/disco.py` (solo lectura, tipos normalizados) | Cada summary expone material clasificable como dominio o proyecto; `no_clasificable` documentado | Fase 0 |
| **2** | `disk_sync.py` + `disk_sync_state.json` + reporte de transformaciones primarias | Cada lote: **≥1 transformación de §4.11** por input; `input_no_transformado` contado y reportado | Fase 1 |
| **3** | Migración `indice.sqlite`: `knowledge_nodes`, `knowledge_relations` con campos §4.8 + `derived_from` + `gap`/`propuesta` + campos web (§4.14.5) + relaciones nuevas | Columnas presentes; relaciones creadas; migración idempotente | Fase 2 + decisión §4.8 |
| **4** | Consolidación Dominio/Proyecto + ground truth (§4.9) + modelo de vistas derivadas (§4.4.2) | Proyectos con `estado` manual; `perfil`/`skill` **no** en jerarquía padre-hijo; `derived_from` operativo; consulta base Proyecto > Dominio > Hecho | Fase 3 + decisión §4.9 |
| **5** | `buscar_hibrido(ambito=...)` + anti-duplicados + filtrado vigencia/confianza/archivado + exposición `huecos()`/`propuestas()` | Colisión → gana Vault; caducados/archivados no aparecen; `huecos()`/`propuestas()` operativas pero **no auto-ejecutadas** | Fase 4 |
| **6** | MCP transparente | `mcp_server.py` único; tools incorporan `source='disk'`; `perfil()`/`skills()` sirven vistas; **patrones NO expuestos** hasta §4.9 maduro | Fase 5 |
| **7** | **Aprendizaje Web Activo formalizado** (§4.14): disparadores, watchlist, validación, trazabilidad, restricción crítica | `aprender_web.py`/`navegador.py` reescritos para cumplir §4.14; toda investigación con disparador válido; `investigacion_no_util` descartada y logueada; watchlist operativa; tools `investigar()`, `marcar_watchlist()`, `estado_investigacion()` | Fase 6 |
| **8** | **Transformaciones evolutivas** (`fusionar`/`archivar`/`consolidar`) + detección de patrones | ≥N proyectos con `fuente_estado=manual`; consolidaciones auditadas y reversibles; patrones solo sobre ground truth manual | Fase 7 + maduración |

**Nota sobre Fase 7:** `aprender_web.py` y `navegador.py` ya existen, pero
**no cumplen §4.14** (no hay política de disparadores, watchlist ni restricción
crítica formalizadas). Fase 7 los reescribe/adapta, no los crea desde cero.

**Nota sobre Fase 8:** no opcional a largo plazo — es lo que convierte BRAIN de
“memoria que se acumula” en “conocimiento que evoluciona”. Deliberadamente
posterior porque requiere volumen real.

---

## 6. Reglas de trabajo (para futuras sesiones)

1. **No escribir código que dependa de suposiciones** sobre rutas o esquema de CORE.
2. **Respetar invariantes de §2** antes de aceptar cualquier diseño.
3. **Reutilizar antes que crear.**
4. **Un cambio por fase.**
5. **Auditoría:** toda operación deja rastro en `pipeline.log` y `disk_sync_state.json`.
6. **Trazabilidad:** nada entra sin `generated_from` y referencia al origen.
7. **Documento derivado, no fuente.** `docs/integracion_CORE_BRAIN.md` es pasivo.
8. **Comprensión como criterio de aceptación.**
9. **Ninguna ingesta silenciosa** (§2.9).
10. **Transformaciones evolutivas nunca automáticas.** Auditadas y reversibles.
11. **Misión única.** Toda capacidad nueva justifica su contribución a §1.2.
12. **`Perfil` y `Skill` son vistas derivadas.** No hijos de `Proyecto`; usan
    `derived_from`, no `contains`/`belongs_to`.
13. **Investigación web con disparador.** Nunca aleatoria; siempre justificada
    (§4.14.1) y con trazabilidad (§4.14.5). Si no reduce incertidumbre, se
    descarta.

---

## 7. Glosario mínimo

- **CORE**: Segundo Cerebro Digital. Productor de información.
- **BRAIN**: Memoria Vectorial. Capa de comprensión persistente.
- **Misión de BRAIN**: mantener continuidad de contexto para reducir re-explicación.
- **Vault**: bóveda Obsidian, fuente humana soberana.
- **Eje de conocimiento**: `Documento → Chunk → Hecho → Entidad → Dominio → Proyecto`.
- **Vista derivada**: `Perfil`, `Skill`. Agregación inferida con `derived_from`.
- **Dominio**: conocimiento consolidado estable sobre área temática.
- **Proyecto**: agrupación de dominios con ciclo de vida definido.
- **source**: `'vault'` | `'web'` | `'disk'`.
- **disk_sync_state.json**: memoria de qué se sincronizó y su estado.
- **Contradicción**: dos nodos vigentes incompatibles. Resuelta por confianza + recencia.
- **Vigencia**: `[vigente_desde, vigente_hasta)` recuperable por defecto.
- **Archivado**: `archivado=true` — cierto y vigente pero no compite por atención.
- **Ground truth de proyecto**: etiqueta manual del estado real. Única base válida para patrones.
- **Transformación primaria**: verbo diario (§4.11).
- **Transformación evolutiva**: verbo de maduración (§4.12).
- **`gap`**: nodo meta de conocimiento faltante. No recuperable por `buscar_hibrido`.
- **`propuesta`**: nodo meta derivado de `gap`. No se auto-ejecuta.
- **`input_no_transformado`**: input sin transformación. Deuda explícita.
- **Disparador de investigación**: condición válida para iniciar aprendizaje web
  (§4.14.1). Sin disparador, no hay investigación.
- **Watchlist**: lista de dominios candidatos a revisión periódica (§4.14.2).
- **`investigacion_no_util`**: investigación web que no produjo transformación
  válida; se descarta y se loguea (§4.14.7).
- **`fuente_caida`**: nodo web cuya URL dejó de estar accesible; no se borra,
  se degrada su `confianza` (§4.14.5).

---

## 8. Indicadores de éxito

Sin estas métricas, BRAIN puede acumular 50.000 nodos y seguir sin demostrar
que ayuda. Se recalculan periódicamente y se exponen en `estado_memoria()`.

### 8.1 Métrica primaria (la que decide si BRAIN sirve)

| Métrica | Definición | Objetivo |
|---|---|---|
| **Reducción de contexto re-explicado** | Contexto que el usuario debe re-escribir a una IA por sesión, medido antes/después de usar BRAIN. | **Decreciente en el tiempo.** Si no baja, BRAIN no cumple su misión. |

### 8.2 Métricas secundarias (soporte a la primaria)

| Métrica | Qué mide | Objetivo |
|---|---|---|
| **Recuperación de decisiones pasadas** | Hit rate de “¿qué decidí sobre X?” con nodo vigente correcto. | >80% |
| **Cobertura de dominios** | Dominios con ≥1 hecho vigente / dominios existentes | >70% |
| **Ratio `input_no_transformado`** | Inputs sin transformación / inputs totales | <5% |
| **Gaps resueltos** | `gap` cerrados / `gap` generados (90d) | >30% |
| **Utilidad de propuestas** | `propuesta` aceptadas/ejecutadas / generadas | >25% |
| **Contradicciones pendientes** | `conflicting=true` sin resolver | Tendencia a 0 |
| **Vigencia mediana** | Tiempo desde `vigente_desde` de hechos vigentes | Estable o creciente |
| **Huérfanos de proyecto** | `fact`/`entity` sin `belongs_to` a dominio/proyecto | <10% |

### 8.3 Métricas de aprendizaje web

| Métrica | Qué mide | Objetivo |
|---|---|---|
| **Investigaciones con disparador válido** | Investigaciones iniciadas con ≥1 disparador §4.14.1 / total | **100%** (cero aleatorias) |
| **Ratio `investigacion_no_util`** | Investigaciones sin transformación / investigaciones totales | <20% |
| **Gaps resueltos vía web** | `gap` cerrados por investigación web / `gap` cerrados totales | >40% |
| **Trazabilidad web completa** | Nodos `origen='web'` con `url_origen`+`fecha_consulta`+`fuente` / total web | **100%** |
| **Fuentes caídas** | Nodos `fuente_caida=true` / nodos web | <10% |
| **Cobertura de watchlist** | Dominios vigilados revisados en ventana / dominios vigilados | >80% |

### 8.4 Métricas de salud arquitectónica (detectan degradación)

| Métrica | Qué detecta |
|---|---|
| **Duplicados Vault ↔ disk** | Fallos de §4.6 (anti-duplicados) |
| **Reutilización de embeddings CORE** | % compatibles reutilizados vs regenerados (§4.2) |
| **Reversiones evolutivas** | `fusionar`/`consolidar` deshechas / aplicadas (Fase 8) |

**Regla:** si la métrica primaria no mejora en 6 meses de uso, el diseño de
capacidades (§1.4) se revisa antes de añadir ninguna nueva.

---

## 9. Notas de versión

- **v1:** integración CORE → BRAIN (técnica, sin visión de comprensión).
- **v2:** sistema de evolución del conocimiento (9 verbos, §4.10–4.13, Fase 7 evolutivas).
- **v3:** misión única (§1.2), `Perfil`/`Skill` como vistas derivadas (§4.4.2),
  indicadores de éxito (§8), invariante #10, reglas 11–12.
- **v4 (actual):** §4.14 Aprendizaje Web Activo (disparadores, watchlist,
  validación, trazabilidad, restricción crítica), invariante #11, capacidad web
  en §1.4, campos web en §4.5, renumeración de fases: Web Activo pasa a Fase 7
  y Evolutivas a Fase 8, métricas web en §8.3, regla 13, glosario ampliado.
```

---

Archivo completo y autocontenido. No he añadido tablas de “resumen de cambios” al final — eso era mi comentario, no parte del archivo.

**Pendiente operativo único:** las 6 decisiones de Fase 0 (§5). Al resolverlas se actualiza §5 y §9 se cierra como “v4 cerrada”.