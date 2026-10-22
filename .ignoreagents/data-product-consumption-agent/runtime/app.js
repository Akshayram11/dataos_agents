const $ = selector => document.querySelector(selector);
let state = null;
let conversationId = crypto.randomUUID();
const oidcKey = `modern-oidc.user:${location.origin}/oidc:dataos_generic`;

function tokenFrom(value, depth = 0) {
  if (!value || depth > 2) return '';
  if (typeof value === 'string') {
    if (!value.trim().startsWith('{')) return '';
    try { return tokenFrom(JSON.parse(value), depth + 1); } catch { return ''; }
  }
  if (typeof value !== 'object') return '';
  const token = value.access_token || value.accessToken;
  const expiry = value.expires_at || value.expiresAt;
  if (token && (!expiry || Date.now() < Number(expiry) * 1000)) return token;
  for (const nested of Object.values(value)) {
    const found = tokenFrom(nested, depth + 1);
    if (found) return found;
  }
  return '';
}

function browserCredential() {
  for (const storage of [localStorage, sessionStorage]) {
    const keys = [oidcKey, ...Object.keys(storage).filter(key => /oidc|auth|token|user/i.test(key)), ...Object.keys(storage)];
    for (const key of new Set(keys)) {
      try { const found = tokenFrom(storage.getItem(key)); if (found) return found; } catch {}
    }
    for (const key of ['access_token', 'accessToken']) {
      const raw = storage.getItem(key); if (raw) return raw;
    }
  }
  return '';
}

const credential = browserCredential();

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options, credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(credential ? { Authorization: `Bearer ${credential}` } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function renderState(next) {
  state = next;
  $('#identity').textContent = `${next.tenant} · private to ${next.owner}`;
  $('#model').textContent = next.model;
  $('#mcp-state').textContent = next.mcp.configured ? `${next.mcp.server}${next.mcp.version ? ` ${next.mcp.version}` : ''}` : 'Not connected';
  $('#openai-state').textContent = next.openai.configured ? 'Connected securely' : 'Not connected';
  const dots = document.querySelectorAll('.connection-dot');
  dots[0]?.classList.toggle('ready', next.mcp.configured);
  dots[1]?.classList.toggle('ready', next.openai.configured);
  $('#status').classList.toggle('ready', next.ready);
  $('#status').lastChild.textContent = next.ready ? ' Ready' : ' Setup required';
  const usage = next.openai.usage || {};
  $('#cost').textContent = `$${Number(usage.estimatedCostUsd || 0).toFixed(6)}`;
  $('#requests').textContent = Number(usage.requests || 0).toLocaleString();
  $('#tokens').textContent = Number(usage.total || 0).toLocaleString();
  const pricing = next.openai.pricing || {};
  $('#pricing').textContent = `$${Number(pricing.inputPerMillion || 0).toFixed(2)} input · $${Number(pricing.cachedInputPerMillion || 0).toFixed(2)} cached · $${Number(pricing.outputPerMillion || 0).toFixed(2)} output / 1M`;
  const tools = $('#tools');
  tools.replaceChildren();
  if (!next.mcp.tools.length) tools.append(Object.assign(document.createElement('span'), { textContent: 'Connect keys to discover tools' }));
  for (const name of next.mcp.tools) tools.append(Object.assign(document.createElement('code'), { textContent: name }));
  if (!next.ready) $('#settings-dialog').showModal();
}

function appendInline(parent, source) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g;
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    if (match.index > cursor) parent.append(document.createTextNode(source.slice(cursor, match.index)));
    const token = match[0];
    if (token.startsWith('**')) {
      const strong = document.createElement('strong');
      strong.textContent = token.slice(2, -2);
      parent.append(strong);
    } else if (token.startsWith('`')) {
      const code = document.createElement('code');
      code.textContent = token.slice(1, -1);
      parent.append(code);
    } else {
      const parts = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
      const link = document.createElement('a');
      link.textContent = parts[1];
      link.href = parts[2];
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      parent.append(link);
    }
    cursor = match.index + token.length;
  }
  if (cursor < source.length) parent.append(document.createTextNode(source.slice(cursor)));
}

function tableCells(line) {
  return line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
}

function renderMarkdown(source) {
  const root = document.createElement('div');
  root.className = 'markdown';
  const lines = String(source).replace(/\r/g, '').split('\n');
  const isTableDivider = line => /^\s*\|?\s*:?-{3,}/.test(line) && line.includes('|');
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    if (line.trim().startsWith('```')) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith('```')) codeLines.push(lines[index++]);
      if (index < lines.length) index += 1;
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.textContent = codeLines.join('\n');
      pre.append(code); root.append(pre); continue;
    }
    if (line.includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      const wrap = document.createElement('div');
      wrap.className = 'table-wrap';
      const table = document.createElement('table');
      const thead = document.createElement('thead');
      const headRow = document.createElement('tr');
      for (const value of tableCells(line)) { const th = document.createElement('th'); appendInline(th, value); headRow.append(th); }
      thead.append(headRow); table.append(thead);
      const tbody = document.createElement('tbody');
      index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        const row = document.createElement('tr');
        for (const value of tableCells(lines[index])) { const td = document.createElement('td'); appendInline(td, value); row.append(td); }
        tbody.append(row); index += 1;
      }
      table.append(tbody); wrap.append(table); root.append(wrap); continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const node = document.createElement(`h${heading[1].length}`);
      appendInline(node, heading[2]); root.append(node); index += 1; continue;
    }
    if (/^>\s?/.test(line)) {
      const quote = document.createElement('blockquote');
      const parts = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) parts.push(lines[index++].replace(/^>\s?/, ''));
      appendInline(quote, parts.join(' ')); root.append(quote); continue;
    }
    const unordered = /^\s*[-*]\s+/.test(line);
    const ordered = /^\s*\d+\.\s+/.test(line);
    if (unordered || ordered) {
      const list = document.createElement(ordered ? 'ol' : 'ul');
      const expression = ordered ? /^\s*\d+\.\s+/ : /^\s*[-*]\s+/;
      while (index < lines.length && expression.test(lines[index])) {
        const item = document.createElement('li');
        appendInline(item, lines[index++].replace(expression, ''));
        list.append(item);
      }
      root.append(list); continue;
    }
    const paragraph = [];
    while (index < lines.length && lines[index].trim()
      && !/^(#{1,3})\s+/.test(lines[index])
      && !/^\s*([-*]|\d+\.)\s+/.test(lines[index])
      && !/^>\s?/.test(lines[index])
      && !lines[index].trim().startsWith('```')
      && !(lines[index].includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1]))) {
      paragraph.push(lines[index++].trim());
    }
    const node = document.createElement('p');
    appendInline(node, paragraph.join(' ')); root.append(node);
  }
  return root;
}

function message(role, content, trace = []) {
  const article = document.createElement('article');
  article.className = `message ${role}`;
  const label = document.createElement('span');
  label.className = 'message-label';
  label.setAttribute('aria-label', role === 'user' ? 'You' : 'Agent');
  const body = document.createElement('div');
  body.className = 'message-body';
  if (role === 'assistant') {
    try { body.append(renderMarkdown(content)); }
    catch { body.textContent = content; }
  } else body.textContent = content;
  article.append(label, body);
  if (trace.length) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = `${trace.length} Arguss MCP tool call${trace.length === 1 ? '' : 's'}`;
    details.append(summary);
    for (const item of trace) {
      const call = document.createElement('div');
      call.className = 'tool-call';
      const name = document.createElement('strong');
      name.textContent = item.tool;
      const args = document.createElement('code');
      args.textContent = JSON.stringify(item.arguments);
      call.append(name, args);
      details.append(call);
    }
    article.append(details);
  }
  const messages = $('#messages');
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;
}

function resetConversation() {
  conversationId = crypto.randomUUID();
  $('#messages').replaceChildren();
  const welcome = document.createElement('article');
  welcome.className = 'welcome compact';
  welcome.textContent = 'New governed data conversation';
  $('#messages').append(welcome);
  $('#prompt').focus();
}

async function load() {
  try { renderState(await api('api/state')); }
  catch (error) {
    $('#status').lastChild.textContent = ' Unauthorized';
    message('assistant', error.message);
  }
}

$('#settings').addEventListener('click', () => $('#settings-dialog').showModal());
$('#new-chat').addEventListener('click', resetConversation);
for (const button of document.querySelectorAll('.starter')) button.addEventListener('click', () => {
  $('#prompt').value = button.dataset.prompt; $('#prompt').focus();
});

$('.tools-toggle').addEventListener('click', event => {
  const button = event.currentTarget;
  const expanded = button.getAttribute('aria-expanded') === 'true';
  button.setAttribute('aria-expanded', String(!expanded));
  $('#tools').hidden = expanded;
});

$('#save-keys').addEventListener('click', async event => {
  const dataos = $('#dataos-key');
  const openai = $('#openai-key');
  event.currentTarget.disabled = true;
  $('#settings-status').textContent = 'Validating Arguss MCP and OpenAI access…';
  try {
    const result = await api('api/settings/keys', {
      method: 'POST', body: JSON.stringify({ dataosKey: dataos.value, openaiKey: openai.value }),
    });
    dataos.value = ''; openai.value = '';
    $('#settings-status').textContent = result.message;
    renderState(await api('api/state'));
    setTimeout(() => $('#settings-dialog').close(), 1000);
  } catch (error) { $('#settings-status').textContent = error.message; }
  finally { event.currentTarget.disabled = false; }
});

$('#composer').addEventListener('submit', async event => {
  event.preventDefault();
  const prompt = $('#prompt');
  const value = prompt.value.trim();
  if (!value) return;
  if (!state?.ready) { $('#settings-dialog').showModal(); return; }
  message('user', value);
  prompt.value = '';
  $('#send').disabled = true;
  const pending = document.createElement('article');
  pending.className = 'message assistant pending';
  pending.textContent = 'Agent is selecting read-only MCP tools…';
  $('#messages').append(pending);
  try {
    const result = await api('api/chat', { method: 'POST', body: JSON.stringify({ message: value, conversationId }) });
    conversationId = result.conversationId;
    pending.remove();
    message('assistant', result.answer, result.trace);
    renderState(await api('api/state'));
  } catch (error) {
    pending.remove();
    message('assistant', `Request failed: ${error.message}`);
  } finally { $('#send').disabled = false; prompt.focus(); }
});

$('#prompt').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); $('#composer').requestSubmit(); }
});

await load();
