/* shared.js — utilities shared across all Observe standalone tools */

/* ── HTML escaping ───────────────────────────────────────────────────────── */
function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ── Date formatters ─────────────────────────────────────────────────────── */
function nanoToDatetime(ns) {
  if (!ns) return '';
  try {
    const ms = Math.floor(Number(ns) / 1e6);
    return new Date(ms).toLocaleString('en-US', {
      year: 'numeric', month: 'short', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short'
    });
  } catch { return String(ns); }
}

function isoToStr(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('en-US', {
      year: 'numeric', month: 'short', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short'
    });
  } catch { return iso; }
}

/* ── Alerts ──────────────────────────────────────────────────────────────── */
function showAlert(type, msg, elId = 'alertBox') {
  const el = document.getElementById(elId);
  if (!el) return;
  el.className = `alert ${type}`;
  el.textContent = msg;
}

function hideAlert(elId = 'alertBox') {
  const el = document.getElementById(elId);
  if (!el) return;
  el.className = 'alert';
  el.textContent = '';
}

/* ── Downloads ───────────────────────────────────────────────────────────── */
function downloadBlob(content, filename, mimeType = 'text/plain') {
  const blob = new Blob([content], { type: mimeType });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

function buildCSVString(headers, rows) {
  const csvRows = rows.map(row =>
    row.map(v => `"${String(v || '').replace(/"/g, '""')}"`).join(',')
  );
  return headers.join(',') + '\n' + csvRows.join('\n');
}

/* ── Clipboard ───────────────────────────────────────────────────────────── */
function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    btn.classList.add('ok');
    setTimeout(() => { btn.textContent = orig; btn.classList.remove('ok'); }, 1500);
  }).catch(() => {
    btn.textContent = 'Failed';
    btn.classList.add('err');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('err'); }, 1500);
  });
}

/* ── Observe URL builder ─────────────────────────────────────────────────── */
function buildObserveHost(cid, dom) {
  return dom.trim() ? `${cid}.${dom}.observeinc.com` : `${cid}.observeinc.com`;
}

function observeAuthHeaders(cid, tok) {
  return { 'Authorization': `Bearer ${cid} ${tok}`, 'Content-Type': 'application/json' };
}

/* ── Monitor badge / icon helpers ───────────────────────────────────────── */
function typeBadge(k) {
  const cls = { Promote: 'type-promote', Anomaly: 'type-anomaly', Count: 'type-count', Threshold: 'type-threshold' }[k] || 'type-other';
  return `<span class="type-badge ${cls}">${esc(k || '')}</span>`;
}

const ACTION_ORDER = { Email: 0, Webhook: 1, PagerDuty: 2, Slack: 3 };

function destIcons(rules = []) {
  const sorted = [...rules].sort((a, b) =>
    (ACTION_ORDER[a.definition?.type || ''] ?? 4) - (ACTION_ORDER[b.definition?.type || ''] ?? 4)
  );
  if (!sorted.length) return '<span class="dim">—</span>';
  return sorted.map(r => {
    const t = r.definition?.type || '';
    const url = r.definition?.webhook?.url || r.definition?.email?.addresses?.join(',') || t || 'Action';
    const em = t === 'Email' ? '✉' : t === 'PagerDuty' ? '📱' : t === 'Webhook' ? '🔗' : t === 'Slack' ? '💬' : '📣';
    return `<span class="dest-icon" title="${esc(url)}">${em}</span>`;
  }).join('');
}

function actionLabel(rule) {
  const defn = rule.definition || {};
  const t = defn.type || '';
  if (t === 'Email')     { const a = defn.email?.addresses || []; return `✉ ${a[0] || 'Email'}`; }
  if (t === 'PagerDuty') return `📱 PagerDuty`;
  if (t === 'Webhook')   return `🔗 ${defn.webhook?.url || 'Webhook'}`;
  if (t === 'Slack')     return `💬 ${defn.webhook?.url || 'Slack'}`;
  return `📣 ${defn.name || t || 'Action'}`;
}

/* ── Dataset ID extraction ───────────────────────────────────────────────── */
function extractDatasetIds(detail) {
  if (!detail) return [];
  const stages = (detail.definition?.inputQuery?.stages) || [];
  const seen = new Set();
  const ids = [];
  for (const stage of stages) {
    let inputs = stage.input;
    if (inputs && !Array.isArray(inputs)) inputs = [inputs];
    if (!Array.isArray(inputs)) continue;
    for (const inp of inputs) {
      const dsId = inp?.datasetId;
      if (dsId && !seen.has(dsId)) { seen.add(dsId); ids.push(dsId); }
    }
  }
  return ids;
}

/* ── Monitor transform logic ─────────────────────────────────────────────── */
function stripNulls(obj) {
  if (Array.isArray(obj)) return obj.map(stripNulls);
  if (obj && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj).filter(([, v]) => v != null).map(([k, v]) => [k, stripNulls(v)])
    );
  }
  return obj;
}

function cleanDefinition(defn) {
  defn = { ...defn };
  delete defn.layout;
  if (defn.inputQuery) {
    const iq = { ...defn.inputQuery };
    delete iq.layout;
    if (Array.isArray(iq.stages)) {
      iq.stages = iq.stages.map(s => {
        s = { ...s };
        delete s.layout;
        if (Array.isArray(s.input)) s.input = s.input[0];
        if (s.input && typeof s.input === 'object') {
          s.input = { ...s.input };
          delete s.input.datasetPath;
          delete s.input.stageId;
        }
        return s;
      });
    }
    defn.inputQuery = iq;
  }
  return defn;
}

function transformActionRule(rule) {
  const out = {};
  if ('definition' in rule) {
    let d = stripNulls({ ...rule.definition });
    delete d.actionId;
    if (!d.name && d.type) {
      if (d.type === 'Email') { const a = d.email?.addresses || []; d.name = `Email ${a[0] || 'action'}`; }
      else if (d.type === 'Webhook') d.name = 'Webhook action';
      else d.name = `${d.type} action`;
    }
    out.definition = d;
  } else if ('actionId' in rule) {
    out.actionId = rule.actionId;
  }
  for (const k of ['levels', 'conditions', 'sendEndNotifications', 'sendRemindersInterval']) {
    if (rule[k] != null) out[k] = rule[k];
  }
  return out;
}

function transformForCreate(data) {
  let body = stripNulls(JSON.parse(JSON.stringify(data)));
  for (const k of ['id', 'monitorVersion', 'effectiveScheduling']) delete body[k];
  body.name = (body.name || '') + ' (auto-generated)';
  if (body.definition) body.definition = cleanDefinition(body.definition);
  if (Array.isArray(body.actionRules)) body.actionRules = body.actionRules.map(transformActionRule);
  const ORDER = ['name', 'description', 'disabled', 'ruleKind', 'definition', 'actionRules'];
  const ordered = {};
  ORDER.forEach(k => { if (k in body) { ordered[k] = body[k]; delete body[k]; } });
  return { ...ordered, ...body };
}

function buildCurlCmd(data, cid, dom, tok) {
  const h = buildObserveHost(cid, dom);
  const body = transformForCreate(data);
  const json = JSON.stringify(body, null, 2).replace(/'/g, "'\\''");
  return `curl https://${h}/v1/monitors \\\n  --request POST \\\n  --header 'Content-Type: application/json' \\\n  --header 'Authorization: Bearer ${cid} ${tok}' \\\n  --data '${json}'`;
}

function buildPSCmd(data, cid, dom, tok) {
  const h = buildObserveHost(cid, dom);
  const body = transformForCreate(data);
  const json = JSON.stringify(body, null, 2).replace(/`/g, '``').replace(/'/g, "''");
  return `Invoke-RestMethod \`\n  -Uri 'https://${h}/v1/monitors' \`\n  -Method Post \`\n  -Headers @{\n    'Content-Type' = 'application/json'\n    'Authorization' = 'Bearer ${cid} ${tok}'\n  } \`\n  -Body '${json}'`;
}

/* ── Tab switching ───────────────────────────────────────────────────────── */
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const panel = document.getElementById(`tab-${btn.dataset.tab}`);
      if (panel) panel.classList.add('active');
    });
  });
}

/* ── Gzip compression (import_file) ─────────────────────────────────────── */
async function gzipBytes(data) {
  const cs = new CompressionStream('gzip');
  const writer = cs.writable.getWriter();
  writer.write(data instanceof Uint8Array ? data : new TextEncoder().encode(data));
  writer.close();
  const chunks = [];
  const reader = cs.readable.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) { out.set(c, off); off += c.length; }
  return out;
}

/* ── Base64 helpers (base64 tools) ──────────────────────────────────────── */
function decodeB64(b64) {
  try { return decodeURIComponent(escape(atob(b64))); }
  catch { return atob(b64); }
}

function tryPrettyJson(str) {
  try { return JSON.stringify(JSON.parse(str), null, 2); }
  catch { return str; }
}
