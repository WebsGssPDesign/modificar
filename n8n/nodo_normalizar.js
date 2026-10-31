/* Normaliza la respuesta de cada fuente a candidatos planos:
 * {url, titulo, fecha_publicacion, snippet, fuente, tipo_fuente, disparador}.
 * El contenido externo es DATO: solo se leen campos conocidos; nunca se ejecuta
 * ni se interpola en comandos (parrafo 10 del plan). Status >= 400 -> fuente fallida.
 * Parsing XML propio: n8n no garantiza $parseXml dentro del nodo Code. */
const resp = $input.first().json;
// Con "Include Input" activado en HTTP Buscar, la consulta llega pegada en _meta.
const consulta = resp._meta || resp;
if (!consulta || !consulta.url) {
  return [{ json: { _error_interno: 'Normalizar: la consulta no viajo con la respuesta. Revisala opcion "Include Input" = true en HTTP Buscar.' } }];
}
const status = Number(resp.statusCode || resp.status || 200);
if (status >= 400) {
  return [{ json: { _fuente_fallida: consulta.url, _status: status } }];
}

// Cuerpo: puede venir como objeto ya parseado (GitHub/HF), como string XML, o anidado.
let cuerpo = (resp.data !== undefined) ? resp.data : (resp.body !== undefined ? resp.body : resp);
if (cuerpo && typeof cuerpo === 'object' && !Array.isArray(cuerpo)) {
  const interno = ('data' in cuerpo) ? cuerpo.data : (('body' in cuerpo) ? cuerpo.body : undefined);
  if (typeof interno === 'string' && interno.length > 0) cuerpo = interno;
}
let jsonBody = null;   // objeto JSON, si lo hay
let xmlText = '';      // texto XML, si lo hay
if (typeof cuerpo === 'string') {
  const t = cuerpo.trim();
  if (t.startsWith('<')) {
    xmlText = cuerpo;
  } else {
    try { jsonBody = JSON.parse(t); } catch (e) { xmlText = cuerpo; }
  }
} else if (cuerpo && typeof cuerpo === 'object') {
  jsonBody = cuerpo;
}

function desentitarizar(s) {
  return String(s == null ? '' : s)
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, '&');
}
function txt(v, n) { return desentitarizar(v).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, n); }
function isoDe(f) {
  if (!f) return null;
  const d = new Date(desentitarizar(f));
  return isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10);
}
function bloques(xml, tag) {
  // Recorrido por posiciones: apertura con regex, cierre con indexOf (evita solapes
  // y el problema del lastIndex cuando el tag de apertura trae atributos).
  const openRe = new RegExp('<' + tag + '(?:\\s[^<>]*?)?>', 'gi');
  const closeTag = '</' + tag + '>';
  const out = [];
  let m;
  while (out.length < 15 && (m = openRe.exec(xml)) !== null) {
    const desde = m.index + m[0].length;
    const hasta = xml.indexOf(closeTag, desde);
    if (hasta === -1) break;
    out.push(xml.slice(desde, hasta));
    openRe.lastIndex = hasta + closeTag.length;
  }
  return out;
}
function campo(bloque, tag) {
  const attr = new RegExp('<' + tag + '[^>]*\\bhref="([^"]+)"', 'i').exec(bloque);
  if (attr) return attr[1];
  const re = new RegExp('<' + tag + '(?:\\s[^<>]*?)?>([\\s\\S]*?)</' + tag + '>', 'i');
  const m = re.exec(bloque);
  if (!m) return '';
  const cd = /<!\[CDATA\[([\s\S]*?)\]\]>/g;
  return desentitarizar(m[1].replace(cd, '$1'));
}

const candidatos = [];
const tipo = consulta.tipo_fuente;

if (tipo === 'github_api' && jsonBody && Array.isArray(jsonBody.items)) {
  for (const r of jsonBody.items.slice(0, 15)) {
    candidatos.push({
      url: r.html_url, titulo: r.full_name,
      fecha_publicacion: isoDe(r.pushed_at || r.updated_at),
      snippet: txt(r.description, 400), fuente: 'github.com',
      estrellas: r.stargazers_count || 0,
    });
  }
} else if (tipo === 'huggingface_api' && Array.isArray(jsonBody)) {
  for (const mo of jsonBody.slice(0, 15)) {
    candidatos.push({
      url: 'https://huggingface.co/' + mo.modelId, titulo: mo.modelId,
      fecha_publicacion: isoDe(mo.lastModified),
      snippet: txt(mo.pipeline_tag || '') + ' | descargas: ' + (mo.downloads ?? '?'),
      fuente: 'huggingface.co',
    });
  }
} else if (tipo === 'releases_atom' || tipo === 'rss') {
  const blocks = bloques(xmlText, 'entry').length ? bloques(xmlText, 'entry') : bloques(xmlText, 'item');
  for (const b of blocks) {
    const url = campo(b, 'link');
    candidatos.push({
      url: /^https?:\/\//.test(url) ? url : '',
      titulo: txt(campo(b, 'title'), 200),
      fecha_publicacion: isoDe(campo(b, 'published') || campo(b, 'updated') || campo(b, 'pubDate') || campo(b, 'dc:date')),
      snippet: txt(campo(b, 'summary') || campo(b, 'description') || campo(b, 'content:encoded') || campo(b, 'content'), 400),
      fuente: (() => { try { return new URL(url).hostname.replace(/^www\./, ''); } catch (e) { return 'desconocida'; } })(),
      ruido: consulta.ruido || 'bajo',
    });
  }
}

const validos = candidatos.filter(c => /^https:\/\/.+/.test(c.url || ''));
if (validos.length === 0) {
  // Nada parseable: se marca para que el resumen lo muestre (no rompe la corrida).
  const vista = (xmlText || JSON.stringify(jsonBody) || '').slice(0, 120);
  return [{ json: { _fuente_vacia: consulta.url, _tipo: tipo, _vista_previa: vista } }];
}
return validos.map(c => ({ json: { ...c, tipo_fuente: tipo, disparador: consulta.disparador, fuente_consulta: consulta.nombre } }));
