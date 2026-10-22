import http from 'node:http';
import { createCipheriv, createDecipheriv, createHash, randomBytes, randomUUID } from 'node:crypto';
import { chmod, mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const CONSUMPTION_SKILL = join(HERE, 'skills', 'data-product-consumption', 'SKILL.md');
const ASSETS = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
  ['/styles.css', ['styles.css', 'text/css; charset=utf-8']],
]);

export const ALLOWED_MCP_TOOLS = new Set([
  'search', 'table_profile', 'get_lineage', 'vulcan_about',
  'vulcan_semantic_schema', 'vulcan_quality', 'vulcan_runs',
  'vulcan_query_submit', 'vulcan_query_result',
]);

export const MODEL_PRICING = Object.freeze({
  inputPerMillion: 0.20,
  cachedInputPerMillion: 0.02,
  outputPerMillion: 1.20,
  currency: 'USD',
  source: 'https://developers.openai.com/api/docs/models/gpt-5.6-luna',
  verifiedAt: '2026-10-21',
});

function integer(name, fallback, min, max) {
  const value = Number.parseInt(process.env[name] ?? String(fallback), 10);
  return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
}

export function configFromEnv() {
  return {
    port: integer('PORT', 8080, 1, 65535),
    fqdn: (process.env.AGENT_DATAOS_FQDN ?? process.env.DATAOS_FQDN ?? '')
      .replace(/^https?:\/\//, '').replace(/\/$/, ''),
    runtimeApiKey: process.env.DATAOS_RUN_AS_APIKEY ?? '',
    owner: process.env.AGENT_OWNER_ID ?? '',
    tenant: process.env.DATAOS_TENANT_ID ?? 'engineering',
    model: process.env.OPENAI_MODEL ?? 'gpt-5.6-luna',
    mcpUrl: process.env.ARGUSS_MCP_URL ?? '',
    stateFile: process.env.STATE_FILE ?? '/etc/dataos/persist/consumption-agent.json',
    secretsFile: process.env.SECRETS_FILE ?? '/etc/dataos/persist/consumption-agent-secrets.enc',
    maxToolRounds: integer('MAX_TOOL_ROUNDS', 16, 1, 20),
  };
}

function emptyState() {
  return {
    version: 1,
    conversations: {},
    modelUsage: { requests: 0, input: 0, cachedInput: 0, output: 0, total: 0, estimatedCostUsd: 0 },
    keyFingerprints: { dataos: '', openai: '' },
  };
}

async function loadState(path) {
  try {
    const value = JSON.parse(await readFile(path, 'utf8'));
    return value?.version === 1 ? value : emptyState();
  } catch (error) {
    if (error.code === 'ENOENT') return emptyState();
    throw error;
  }
}

async function atomicJson(path, value) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = `${path}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  await chmod(temporary, 0o600);
  await rename(temporary, path);
}

function encryptionKey(runtimeApiKey) {
  return createHash('sha256').update('dataos-consumption-agent:secrets:v1\0').update(runtimeApiKey).digest();
}

export async function saveEncryptedSecrets(path, secrets, runtimeApiKey) {
  if (!path || !runtimeApiKey || !secrets?.dataosKey || !secrets?.openaiKey) throw new Error('Encrypted secret storage is not configured');
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', encryptionKey(runtimeApiKey), iv);
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(secrets), 'utf8'), cipher.final()]);
  await atomicJson(path, {
    version: 1,
    algorithm: 'aes-256-gcm',
    iv: iv.toString('base64'),
    ciphertext: ciphertext.toString('base64'),
    tag: cipher.getAuthTag().toString('base64'),
  });
}

export async function loadEncryptedSecrets(path, runtimeApiKey) {
  try {
    const payload = JSON.parse(await readFile(path, 'utf8'));
    if (payload.version !== 1 || payload.algorithm !== 'aes-256-gcm') return null;
    const decipher = createDecipheriv('aes-256-gcm', encryptionKey(runtimeApiKey), Buffer.from(payload.iv, 'base64'));
    decipher.setAuthTag(Buffer.from(payload.tag, 'base64'));
    return JSON.parse(Buffer.concat([
      decipher.update(Buffer.from(payload.ciphertext, 'base64')), decipher.final(),
    ]).toString('utf8'));
  } catch {
    return null;
  }
}

export function extractBearerToken(value) {
  return String(value ?? '').match(/^Bearer\s+([^\s]+)$/i)?.[1] ?? '';
}

export function requestCredentialCandidates(headers) {
  const candidates = [];
  const bearer = extractBearerToken(headers.authorization);
  if (bearer) candidates.push(bearer);
  for (const part of String(headers.cookie ?? '').split(';')) {
    const separator = part.indexOf('=');
    if (separator < 1) continue;
    try {
      const value = decodeURIComponent(part.slice(separator + 1).trim());
      if (value.length >= 20 && value.length <= 4096) candidates.push(value);
    } catch {}
  }
  return [...new Set(candidates)].slice(0, 12);
}

export async function authorizeOwnerToken(token, cfg, fetchImpl = fetch) {
  if (!token) return { status: 401, error: 'Authentication required' };
  if (!cfg.fqdn || !cfg.owner) return { status: 503, error: 'Authorization is not configured' };
  try {
    const response = await fetchImpl(`https://${cfg.fqdn}/heimdall/api/v1/authorize`, {
      method: 'POST', signal: AbortSignal.timeout(10000),
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) return { status: 401, error: 'Invalid or expired DataOS session' };
    const result = await response.json();
    if (!result?.valid || !result?.allow) return { status: 401, error: 'Invalid or expired DataOS session' };
    if (result?.result?.id !== cfg.owner) return { status: 403, error: 'This application is restricted to its owner' };
    return { status: 200, userId: result.result.id };
  } catch {
    return { status: 503, error: 'DataOS authorization service is unavailable' };
  }
}

export async function validateModelKey(apiKey, model, fetchImpl = fetch) {
  try {
    const response = await fetchImpl(`https://api.openai.com/v1/models/${encodeURIComponent(model)}`, {
      signal: AbortSignal.timeout(15000), headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' },
    });
    if (response.ok) return { ok: true };
    if (response.status === 401) return { ok: false, error: 'OpenAI rejected this API key' };
    if (response.status === 403 || response.status === 404) return { ok: false, error: `This API key cannot access ${model}` };
    return { ok: false, error: `OpenAI validation failed (HTTP ${response.status})` };
  } catch {
    return { ok: false, error: 'OpenAI could not be reached; keys were not saved' };
  }
}

export function parseMcpEnvelope(text, expectedId) {
  const candidates = String(text).split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trim())
    .filter(Boolean);
  if (!candidates.length && String(text).trim().startsWith('{')) candidates.push(String(text).trim());
  for (const candidate of candidates) {
    try {
      const value = JSON.parse(candidate);
      if (expectedId === undefined || value.id === expectedId) {
        if (value.error) throw new Error(value.error.message || 'MCP request failed');
        return value.result;
      }
    } catch (error) {
      if (error instanceof SyntaxError) continue;
      throw error;
    }
  }
  throw new Error('Arguss MCP returned no matching JSON-RPC response');
}

let rpcId = 100;
export async function mcpRequest(url, apiKey, method, params = {}, fetchImpl = fetch) {
  const id = ++rpcId;
  const response = await fetchImpl(url, {
    method: 'POST', signal: AbortSignal.timeout(method === 'tools/call' ? 60000 : 20000),
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      'MCP-Protocol-Version': '2025-03-26',
    },
    body: JSON.stringify({ jsonrpc: '2.0', id, method, params }),
  });
  const text = await response.text();
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) throw new Error('Arguss rejected this DataOS API key');
    throw new Error(`Arguss MCP HTTP ${response.status}`);
  }
  return parseMcpEnvelope(text, id);
}

export function safeMcpTools(result) {
  const tools = Array.isArray(result?.tools) ? result.tools : [];
  return tools.filter(tool => ALLOWED_MCP_TOOLS.has(tool.name)
    && tool.annotations?.readOnlyHint === true
    && tool.annotations?.destructiveHint === false);
}

export async function inspectMcp(url, apiKey, fetchImpl = fetch) {
  const initialized = await mcpRequest(url, apiKey, 'initialize', {
    protocolVersion: '2025-03-26', capabilities: {},
    clientInfo: { name: 'dataos-data-product-consumption-agent', version: '1.0.0' },
  }, fetchImpl);
  const listed = await mcpRequest(url, apiKey, 'tools/list', {}, fetchImpl);
  const tools = safeMcpTools(listed);
  if (!tools.length) throw new Error('Arguss exposed no approved read-only data-product tools');
  return {
    server: initialized?.serverInfo ?? {},
    instructions: String(initialized?.instructions ?? '').slice(0, 30000),
    tools,
  };
}

export function responseUsage(payload) {
  const usage = payload?.usage ?? {};
  const input = Math.max(0, Number(usage.input_tokens) || 0);
  const output = Math.max(0, Number(usage.output_tokens) || 0);
  const cachedInput = Math.min(input, Math.max(0, Number(usage.input_tokens_details?.cached_tokens) || 0));
  const estimatedCostUsd = ((input - cachedInput) * MODEL_PRICING.inputPerMillion
    + cachedInput * MODEL_PRICING.cachedInputPerMillion
    + output * MODEL_PRICING.outputPerMillion) / 1_000_000;
  return { input, cachedInput, output, total: Number(usage.total_tokens) || input + output, estimatedCostUsd };
}

function outputText(payload) {
  if (typeof payload?.output_text === 'string') return payload.output_text.trim();
  return (payload?.output ?? []).filter(item => item.type === 'message')
    .flatMap(item => item.content ?? []).map(item => item.text ?? '').join('\n').trim();
}

function fingerprint(value) {
  return createHash('sha256').update(value).digest('hex').slice(0, 12);
}

function publicState(state, secrets, catalog, cfg) {
  const conversations = Object.values(state.conversations ?? {})
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .map(item => ({
      id: item.id,
      title: item.title,
      createdAt: item.createdAt,
      updatedAt: item.updatedAt,
      messages: (item.messages ?? []).map(message => ({
        role: message.role,
        content: message.content,
        at: message.at,
        trace: (message.trace ?? []).map(entry => ({ tool: entry.tool, arguments: entry.arguments })),
      })),
    }));
  return {
    owner: cfg.owner,
    tenant: cfg.tenant,
    model: cfg.model,
    mcp: {
      configured: Boolean(secrets?.dataosKey),
      endpoint: cfg.mcpUrl ? new URL(cfg.mcpUrl).host : '',
      server: catalog?.server?.name ?? 'data-product-mcp',
      version: catalog?.server?.version ?? '',
      tools: (catalog?.tools ?? []).map(tool => tool.name),
    },
    openai: { configured: Boolean(secrets?.openaiKey), usage: state.modelUsage, pricing: MODEL_PRICING },
    ready: Boolean(secrets?.dataosKey && secrets?.openaiKey),
    conversations,
  };
}

function cleanToolResult(value) {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer [REDACTED]')
    .replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g, '[REDACTED_API_KEY]')
    .slice(0, 80000);
}

export function safeFailureMessage(error) {
  return String(error?.message || error || 'Tool call failed')
    .replace(/\bBearer\s+\S+/gi, 'Bearer [REDACTED]')
    .replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g, '[REDACTED_API_KEY]')
    .slice(0, 300);
}

function addUsage(total, payload) {
  const usage = responseUsage(payload);
  total.requests += 1;
  total.input += usage.input;
  total.cachedInput += usage.cachedInput;
  total.output += usage.output;
  total.total += usage.total;
  total.estimatedCostUsd += usage.estimatedCostUsd;
  return usage;
}

async function readBody(request, maximum = 20000) {
  let body = '';
  for await (const chunk of request) {
    body += chunk;
    if (body.length > maximum) throw new Error('Request body too large');
  }
  return JSON.parse(body || '{}');
}

export async function createConsumptionAgent(overrides = {}) {
  const cfg = { ...configFromEnv(), ...overrides };
  let state = await loadState(cfg.stateFile);
  let secrets = await loadEncryptedSecrets(cfg.secretsFile, cfg.runtimeApiKey);
  let catalog = null;
  let catalogFingerprint = '';
  let catalogAt = 0;
  const skill = await readFile(CONSUMPTION_SKILL, 'utf8').catch(() => '');

  async function getCatalog(force = false) {
    if (!secrets?.dataosKey) throw new Error('Connect your DataOS API key first');
    const keyFingerprint = fingerprint(secrets.dataosKey);
    if (!force && catalog && catalogFingerprint === keyFingerprint && Date.now() - catalogAt < 300000) return catalog;
    catalog = await inspectMcp(cfg.mcpUrl, secrets.dataosKey);
    catalogFingerprint = keyFingerprint;
    catalogAt = Date.now();
    return catalog;
  }

  if (secrets?.dataosKey) {
    try { await getCatalog(true); } catch { catalog = null; }
  }

  const save = () => atomicJson(cfg.stateFile, state);

  async function openaiResponse(body) {
    const response = await fetch('https://api.openai.com/v1/responses', {
      method: 'POST', signal: AbortSignal.timeout(90000),
      headers: { Authorization: `Bearer ${secrets.openaiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload?.error?.message || `OpenAI HTTP ${response.status}`);
    addUsage(state.modelUsage, payload);
    return payload;
  }

  async function chat(message, conversationId) {
    if (!secrets?.dataosKey || !secrets?.openaiKey) throw new Error('Connect both API keys before chatting');
    const mcp = await getCatalog();
    const now = new Date().toISOString();
    const id = /^[a-zA-Z0-9-]{8,80}$/.test(conversationId ?? '') ? conversationId : randomUUID();
    const conversation = state.conversations[id] ?? {
      id, title: message.slice(0, 64), createdAt: now, updatedAt: now, messages: [],
    };
    const history = conversation.messages.slice(-16).map(item => ({ role: item.role, content: item.content }));
    let input = [...history, { role: 'user', content: message }];
    const tools = mcp.tools.map(tool => ({
      type: 'function', name: tool.name,
      description: String(tool.description ?? '').slice(0, 12000),
      parameters: tool.inputSchema ?? { type: 'object', properties: {}, additionalProperties: false },
      strict: false,
    }));
    const instructions = `Formatting re-enabled\nYou are the private DataOS Data Product Consumption Agent for ${cfg.owner}.\n` +
      `You may obtain external facts ONLY by calling the supplied Arguss MCP function tools. Never claim to use command-line access, web search, shell, files, direct platform APIs, or any unlisted tool.\n` +
      `All tools are read-only. Never invent tool results. Default operational tenant context is ${cfg.tenant}, while following the MCP discovery-first rules.\n` +
      `Give concise, decision-ready answers in Markdown. Name the data product and governed metric/filter/time window when answering data questions. Show limitations and owner escalation details when the MCP returns them.\n\n` +
      `${skill.slice(0, 30000)}\n\nMCP server instructions:\n${mcp.instructions}`;
    const trace = [];
    const failedCalls = new Set();
    let answer = '';

    for (let round = 0; round < cfg.maxToolRounds; round += 1) {
      const payload = await openaiResponse({
        model: cfg.model, instructions, input, tools, tool_choice: 'auto',
        max_output_tokens: 2200, store: false,
      });
      const calls = (payload.output ?? []).filter(item => item.type === 'function_call');
      if (!calls.length) {
        answer = outputText(payload);
        if (!answer) throw new Error('The model returned no answer');
        break;
      }
      const outputs = [];
      for (const call of calls) {
        if (!ALLOWED_MCP_TOOLS.has(call.name) || !mcp.tools.some(tool => tool.name === call.name)) {
          throw new Error(`Blocked unapproved tool: ${call.name}`);
        }
        let args;
        try { args = JSON.parse(call.arguments || '{}'); } catch { throw new Error(`Model returned invalid arguments for ${call.name}`); }
        const signature = `${call.name}:${JSON.stringify(args)}`;
        try {
          const result = await mcpRequest(cfg.mcpUrl, secrets.dataosKey, 'tools/call', { name: call.name, arguments: args });
          trace.push({ tool: call.name, arguments: args });
          outputs.push({ type: 'function_call_output', call_id: call.call_id, output: cleanToolResult(result) });
        } catch (error) {
          const reason = safeFailureMessage(error);
          const repeated = failedCalls.has(signature);
          failedCalls.add(signature);
          trace.push({ tool: call.name, arguments: args, error: reason });
          outputs.push({
            type: 'function_call_output', call_id: call.call_id,
            output: JSON.stringify({
              error: reason,
              recoverable: !repeated,
              instruction: repeated
                ? 'Do not repeat this call. Continue with available evidence and disclose the unavailable check.'
                : 'Re-check the tool schema and canonical discovery result, correct the arguments once, or continue with available evidence.',
            }),
          });
        }
      }
      input = [...input, ...(payload.output ?? []), ...outputs];
    }
    if (!answer) throw new Error(`Agent stopped after ${cfg.maxToolRounds} MCP rounds`);

    conversation.messages.push({ role: 'user', content: message, at: now });
    conversation.messages.push({ role: 'assistant', content: answer, trace, at: new Date().toISOString() });
    conversation.messages = conversation.messages.slice(-40);
    conversation.updatedAt = new Date().toISOString();
    state.conversations[id] = conversation;
    state.conversations = Object.fromEntries(Object.values(state.conversations)
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).slice(0, 20).map(item => [item.id, item]));
    await save();
    return { conversationId: id, answer, trace, usage: state.modelUsage };
  }

  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://consumption-agent.local');
    const headers = {
      'Cache-Control': 'no-store',
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
      'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
    };
    const json = (status, body) => {
      response.writeHead(status, { ...headers, 'Content-Type': 'application/json' });
      response.end(JSON.stringify(body));
    };
    try {
      if (request.method === 'GET' && url.pathname === '/healthz') return json(200, { ok: true });
      if (request.method === 'GET' && ASSETS.has(url.pathname)) {
        const [file, type] = ASSETS.get(url.pathname);
        response.writeHead(200, { ...headers, 'Content-Type': type });
        return response.end(await readFile(join(HERE, file)));
      }
      if (url.pathname.startsWith('/api/')) {
        const candidates = requestCredentialCandidates(request.headers);
        let authorization = { status: 401, error: 'Authentication required' };
        for (const candidate of candidates) {
          authorization = await authorizeOwnerToken(candidate, cfg);
          if ([200, 403, 503].includes(authorization.status)) break;
        }
        if (authorization.status !== 200) return json(authorization.status, { error: authorization.error });
      }
      if (request.method === 'GET' && url.pathname === '/api/state') return json(200, publicState(state, secrets, catalog, cfg));
      if (request.method === 'POST' && url.pathname === '/api/settings/keys') {
        if ((request.headers['sec-fetch-site'] ?? 'same-origin') === 'cross-site') return json(403, { error: 'Cross-site request rejected' });
        const body = await readBody(request, 4096);
        const dataosKey = String(body.dataosKey ?? '').trim();
        const openaiKey = String(body.openaiKey ?? '').trim();
        if (dataosKey.length < 40 || dataosKey.length > 2048 || /\s/.test(dataosKey)) return json(400, { error: 'Invalid DataOS API key' });
        if (openaiKey.length < 20 || openaiKey.length > 512 || /\s/.test(openaiKey)) return json(400, { error: 'Invalid OpenAI API key' });
        const inspected = await inspectMcp(cfg.mcpUrl, dataosKey);
        const modelValidation = await validateModelKey(openaiKey, cfg.model);
        if (!modelValidation.ok) return json(400, { error: modelValidation.error });
        await saveEncryptedSecrets(cfg.secretsFile, { dataosKey, openaiKey }, cfg.runtimeApiKey);
        const changed = state.keyFingerprints.dataos !== fingerprint(dataosKey)
          || state.keyFingerprints.openai !== fingerprint(openaiKey);
        secrets = { dataosKey, openaiKey };
        catalog = inspected;
        catalogFingerprint = fingerprint(dataosKey);
        catalogAt = Date.now();
        if (changed) state.modelUsage = emptyState().modelUsage;
        state.keyFingerprints = { dataos: fingerprint(dataosKey), openai: fingerprint(openaiKey) };
        await save();
        return json(200, { ready: true, tools: inspected.tools.map(tool => tool.name), message: 'Both keys validated and encrypted on the private stateful disk.' });
      }
      if (request.method === 'POST' && url.pathname === '/api/chat') {
        const body = await readBody(request);
        const message = String(body.message ?? '').trim();
        if (!message || message.length > 6000) return json(400, { error: 'Message must be between 1 and 6000 characters' });
        return json(200, await chat(message, String(body.conversationId ?? '')));
      }
      return json(404, { error: 'Not found' });
    } catch (error) {
      const message = safeFailureMessage(error);
      return json(500, { error: message });
    }
  });

  return {
    cfg, server, chat,
    start() { server.listen(cfg.port, '0.0.0.0'); return server; },
    async stop() { await new Promise(resolve => server.close(resolve)); },
    snapshot: () => publicState(state, secrets, catalog, cfg),
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const agent = await createConsumptionAgent();
  agent.start();
  console.log(JSON.stringify({ event: 'consumption-agent.started', port: agent.cfg.port, tenant: agent.cfg.tenant }));
}
