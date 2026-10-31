// Simulación end-to-end de los nodos Code del workflow Parte 1 (n8n).
// No reemplaza una corrida real en n8n: verifica que la lógica encadene y
// que el resumen final se arme con datos reales. Uso: node n8n/simular_flujo.js
const fs = require('fs');
const path = require('path');

const wf = JSON.parse(fs.readFileSync(path.join(__dirname, 'parte1_workflow.json'), 'utf8'));
const js = {};
for (const n of wf.nodes) if (n.parameters && n.parameters.jsCode) js[n.name] = n.parameters.jsCode;

// ---- mini-sandbox: emula $input / $(nombre) de n8n -------------------------
const store = {};
function runNode(nombre, inputItems) {
  const code = js[nombre];
  if (!code) throw new Error('no existe el nodo Code: ' + nombre);
  const fn = new Function('$', '$input', '$json', code);
  const $input = { all: () => inputItems, first: () => inputItems[0], item: inputItems[0] };
  const $ = (name) => {
    const items = store[name];
    if (!items) throw new Error('$(' + name + '): el nodo aun no se ejecuto');
    return { all: () => items, first: () => items[0], item: items[0] };
  };
  const out = fn($, $input, inputItems.length ? inputItems[0].json : {});
  store[nombre] = out;
  return out;
}

// ---- contexto simulado (forma estable que expone ingesta_web.py --contexto)
const contexto = {
  pesos_efectivos: { 'memoria para agentes': 0.95, 'RAG': 0.95, 'n8n': 1.0 },
  objetivos_activos: [{ id: 'OBJ-002' }],
  keywords: ['agent memory', 'rag'],
  huecos: [{ interes: 'RAG', motivo: 'sin notas' }],
  dominios_permitidos: ['github.com', 'api.github.com', 'huggingface.co', 'react.dev', 'ollama.com'],
  max_antiguedad_dias: 365,
  limites_por_ciclo: { max_consultas: 8, max_hallazgos: 20, max_evaluados: 10, max_guardados: 5 },
  descartar: ['contenido patrocinado', 'sitios de afiliados', 'spam seo'],
  urls_vistas: ['https://github.com/visto/demo'],
  fuentes_rss: [{ url: 'https://react.dev/rss.xml', nombre: 'React blog' }],
  releases_atom: [{ url: 'https://github.com/ollama/ollama/releases.atom', nombre: 'Ollama releases' }],
};
store['Parsear contexto'] = [{ json: { contexto } }];

// ---- respuestas HTTP simuladas (lo que devolvería cada tipo de fuente) ----
const atom = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
  + '<entry><title>v0.13.4 &amp; notas</title><link href="https://github.com/ollama/ollama/releases/tag/v0.13.4"/>'
  + '<published>2026-10-20T00:00:00Z</published><summary>Nueva version con <b>mejoras</b>.</summary></entry>'
  + '<entry><title>v0.9.0 vieja</title><link href="https://github.com/ollama/ollama/releases/tag/v0.9.0"/>'
  + '<published>2020-01-01T00:00:00Z</published><summary>antigua</summary></entry></feed>';
const rss = '<rss><channel>'
  + '<item><title>React 19.2</title><link>https://react.dev/blog/2026/10/01/react-v19-2</link>'
  + '<pubDate>Wed, 01 Oct 2026 00:00:00 GMT</pubDate><description><![CDATA[Contenido patrocinado: hay que descartarlo]]></description></item>'
  + '<item><title>Buen post</title><link>https://react.dev/blog/bueno</link>'
  + '<pubDate>Fri, 10 Oct 2026 00:00:00 GMT</pubDate><description>ok</description></item></channel></rss>';
const respuestas = {
  releases_atom: { statusCode: 200, data: atom },
  rss: { statusCode: 200, data: rss },
  github_api: { statusCode: 200, data: { items: [
    { html_url: 'https://github.com/visto/demo', full_name: 'visto/demo', pushed_at: '2026-10-01T00:00:00Z', description: 'ya vista', stargazers_count: 5 },
    { html_url: 'https://github.com/nueva/agent-memory', full_name: 'nueva/agent-memory', pushed_at: '2026-10-25T00:00:00Z', description: 'SQLite memory for agents', stargazers_count: 90 },
  ] } },
  huggingface_api: { statusCode: 200, data: [
    { modelId: 'nova/model-rag', lastModified: '2026-10-15T00:00:00Z', pipeline_tag: 'embeddings', downloads: 1200 },
  ] },
};

// ---- 1) Planificador -------------------------------------------------------
const consultas = runNode('Planificador', [{ json: {} }]);
console.log('[Planificador] ' + consultas.length + ' consultas');
consultas.forEach(c => console.log('   -', c.json.tipo_fuente, '|', c.json.disparador.tipo + ':' + c.json.disparador.detalle));

// ---- 2) HTTP Buscar (simulado) + Normalizar candidatos, por consulta -------
const normalizados = [];
for (const c of consultas) {
  const r = respuestas[c.json.tipo_fuente];
  // Así llega el ítem con "Include Input" = true: respuesta + _meta con la consulta
  normalizados.push(...runNode('Normalizar candidatos', [{ json: { statusCode: r.statusCode, data: r.data, _meta: c.json } }]));
}
// una fuente que cae (status >= 400)
normalizados.push(...runNode('Normalizar candidatos', [{ json: { statusCode: 503, _meta: { url: 'https://caida/feed', tipo_fuente: 'rss', disparador: { tipo: 'dominio_vigilado', detalle: 'x' } } } }]));
store['Normalizar candidatos'] = normalizados;

// ---- 3) Recolectar todo (rama done del Loop) --------------------------------
const recolectados = runNode('Recolectar todo', [{ json: {} }]);
console.log('[Recolectar todo] ' + recolectados.length + ' items');

// ---- 4) Filtrar candidatos --------------------------------------------------
const filtrados = runNode('Filtrar candidatos', recolectados);
console.log('[Filtrar candidatos] ' + filtrados.length + ' hallazgos');
filtrados.forEach(f => console.log('   *', f.json.titulo, '|', f.json.fecha_publicacion, '|', f.json.fuente));

// ---- 5) Resumen Parte 1 (nodo Code, ex-Markdown) ----------------------------
const resumen = runNode('Resumen Parte 1', filtrados);
console.log('\n--- RESUMEN ---\n' + resumen[0].json.resumen_texto);

// ---- verificaciones ---------------------------------------------------------
const titulos = filtrados.filter(f => f.json.titulo).map(f => f.json.titulo);
if (titulos.length === 0) throw new Error('no paso ningun candidato (el flujo no encadena)');
if (titulos.some(t => /patrocinado/i.test(t))) throw new Error('filtro de descarte no aplico');
if (titulos.some(t => /v0\.9\.0/.test(t))) throw new Error('filtro de antiguedad no aplico');
if (titulos.some(t => /visto\/demo/.test(t))) throw new Error('dedupe contra urls_vistas no aplico');
if (!resumen[0].json.ok) throw new Error('el resumen reporto estado de fallo');

// caso borde: ciclo sin hallazgos
const vacio = runNode('Resumen Parte 1', [{ json: { _resumen: 'sin candidatos nuevos', _fallidas: 'ninguna' } }]);
console.log('\n--- RESUMEN (ciclo vacio) ---\n' + vacio[0].json.resumen_texto);

console.log('\nOK: el flujo encadena de punta a punta.');
