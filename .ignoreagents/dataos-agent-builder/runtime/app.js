const $ = selector => document.querySelector(selector);
const welcome = $('#welcome');
let state = null;
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

async function api(path, options = {}) {
  const credential = browserCredential();
  const response = await fetch(path, {
    ...options,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(credential ? { Authorization: `Bearer ${credential}` } : {}),
      ...(options.headers || {}),
    },
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(value.error || `Request failed (${response.status})`);
  return value;
}

function textNode(tag, className, value) {
  const node = document.createElement(tag); if (className) node.className = className; node.textContent = value; return node;
}

function message(item) {
  const row = textNode('article', `message ${item.role}`, '');
  row.append(textNode('div', 'avatar', item.role === 'assistant' ? 'AI' : 'YOU'));
  row.append(textNode('pre', '', item.content));
  if (item.trace?.length) row.append(textNode('div', 'trace', `${item.trace.length} read-only DataOS tool call${item.trace.length === 1 ? '' : 's'}`));
  $('#messages').append(row);
}

function renderProject(project) {
  const box = $('#project'); box.replaceChildren();
  if (!project) { box.hidden = true; $('#deploy-box').hidden = true; return; }
  box.hidden = false;
  box.append(textNode('h3', '', project.project_name));
  box.append(textNode('p', '', project.summary || 'Validated agent project'));
  const list = document.createElement('ul');
  for (const id of project.deploy_order || []) list.append(textNode('li', '', id));
  box.append(list); box.append(textNode('p', '', `${project.files?.length || 0} files · ${project.resources?.length || 0} resources · lint passed`));
  if (project.accessPlan) box.append(textNode('p', '', `Application identity: ${project.accessPlan.applicationId} · ${project.accessPlan.policies.length} least-privilege policies`));
  $('#deploy-box').hidden = project.status !== 'validated';
  $('#confirmation').placeholder = `DEPLOY ${project.project_name}`;
}

function workflow() {
  const prd = state.prd, project = state.project;
  for (const id of ['discovery','prd','generate','deploy']) $(`#step-${id}`).className = '';
  if (!prd) $('#step-discovery').className = 'active';
  else { $('#step-discovery').className = 'done'; $('#step-prd').className = prd.status === 'approved' ? 'done' : 'active'; }
  if (prd?.status === 'approved') $('#step-generate').className = project ? 'done' : 'active';
  if (project) $('#step-deploy').className = state.deployments?.at(-1)?.status === 'verified' ? 'done' : 'active';
}

function render(next) {
  state = next;
  $('#identity').textContent = `${state.tenant} · private to ${state.owner}`;
  $('#model-name').textContent = state.model;
  $('#ready').textContent = state.ready ? 'Ready' : 'Connect keys'; $('#ready').className = `status${state.ready ? ' ready' : ''}`;
  $('#tool-count').textContent = `${state.toolCount} read-only planning tools`;
  $('#cost').textContent = `$${Number(state.usage.estimatedCostUsd || 0).toFixed(6)}`;
  $('#tokens').textContent = `${state.usage.requests || 0} requests · ${(state.usage.total || 0).toLocaleString()} tokens`;
  $('#messages').replaceChildren();
  if (!state.conversation.length) $('#messages').append(welcome);
  else for (const item of state.conversation) message(item);
  const prd = state.prd;
  $('#artifact-empty').hidden = Boolean(prd); $('#prd').hidden = !prd; $('#artifact-actions').hidden = !prd;
  $('#artifact-title').textContent = prd ? `PRD · ${prd.revision}` : 'No PRD yet';
  $('#artifact-status').textContent = prd?.status || 'Discovery'; $('#artifact-status').className = `pill ${prd?.status || ''}`;
  if (prd) $('#prd').textContent = prd.content;
  $('#approve-prd').hidden = !prd || prd.status !== 'draft';
  $('#generate-project').hidden = !prd || prd.status !== 'approved' || Boolean(state.project);
  renderProject(state.project); workflow();
  const last = state.deployments?.at(-1); $('#deployment').hidden = !last;
  if (last) $('#deployment').textContent = JSON.stringify(last, null, 2);
  $('#messages').scrollTop = $('#messages').scrollHeight;
}

async function refresh() { render(await api('api/state')); }

async function action(button, label, work) {
  const original = button.textContent; button.disabled = true; button.textContent = label;
  try { await work(); await refresh(); } catch (error) { alert(error.message); }
  finally { button.disabled = false; button.textContent = original; }
}

$('#composer').addEventListener('submit', event => {
  event.preventDefault(); const prompt = $('#prompt'); const value = prompt.value.trim(); if (!value) return;
  message({ role: 'user', content: value }); prompt.value = '';
  const pending = textNode('div', 'pending', 'Builder is checking requirements and platform evidence…'); $('#messages').append(pending);
  action($('#send'), '…', async () => { const result = await api('api/chat', { method: 'POST', body: JSON.stringify({ message: value }) }); pending.remove(); message({ role: 'assistant', content: result.answer, trace: result.trace }); });
});

for (const button of document.querySelectorAll('.starters button')) button.addEventListener('click', () => { $('#prompt').value = button.dataset.prompt; $('#prompt').focus(); });
$('#connections').addEventListener('click', () => $('#connection-dialog').showModal());
$('#save-keys').addEventListener('click', () => action($('#save-keys'), 'Validating…', async () => {
  $('#connection-error').textContent = '';
  try {
    await api('api/settings/keys', { method: 'POST', body: JSON.stringify({ dataosKey: $('#dataos-key').value, openaiKey: $('#openai-key').value }) });
    $('#dataos-key').value = ''; $('#openai-key').value = ''; $('#connection-dialog').close();
  } catch (error) { $('#connection-error').textContent = error.message; throw error; }
}));
$('#reset').addEventListener('click', () => { if (confirm('Start a new agent design? Existing PRD and generated project will be cleared.')) action($('#reset'), 'Resetting…', () => api('api/reset', { method: 'POST', body: '{}' })); });
$('#generate-prd').addEventListener('click', () => action($('#generate-prd'), 'Generating…', () => api('api/prd/generate', { method: 'POST', body: '{}' })));
$('#approve-prd').addEventListener('click', () => action($('#approve-prd'), 'Approving…', () => api('api/prd/approve', { method: 'POST', body: JSON.stringify({ revision: state.prd.revision }) })));
$('#generate-project').addEventListener('click', () => action($('#generate-project'), 'Generating + linting…', () => api('api/project/generate', { method: 'POST', body: '{}' })));
$('#deploy').addEventListener('click', () => action($('#deploy'), 'Deploying + verifying…', () => api('api/deploy', { method: 'POST', body: JSON.stringify({ revision: state.project.revision, confirmation: $('#confirmation').value }) })));

refresh().catch(error => { $('#messages').replaceChildren(textNode('div', 'pending', error.message)); });
