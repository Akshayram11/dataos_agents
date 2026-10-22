import http from 'node:http';
import { createCipheriv, createDecipheriv, createHash, randomBytes, randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, writeFile, chmod } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ASSETS = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
  ['/styles.css', ['styles.css', 'text/css; charset=utf-8']],
  ['/enhancements.css', ['enhancements.css', 'text/css; charset=utf-8']],
]);
const FAILURE_WORDS = ['error', 'fail', 'failed', 'failing', 'failure', 'crash', 'crashing', 'crashloopbackoff', 'degraded', 'unhealthy', 'aborted', 'terminated'];
const PENDING_WORDS = ['pending', 'queued', 'initializing', 'provisioning', 'starting', 'reconciling', 'waiting'];
const HEALTHY_WORDS = ['active', 'running', 'succeeded', 'success', 'completed', 'healthy', 'ready'];
// Deliberately excludes secret, grant, role and user resources. The observer
// needs the tenant's operational graph, never credential or IAM payloads.
export const MONITORED_TYPES = new Set([
  'app', 'bundle', 'compute', 'dataplane', 'depot', 'lakehouse', 'link',
  'minerva', 'nilus-v5', 'service', 'stack', 'volume', 'vulcan', 'vulcantest',
  'worker', 'workflow',
]);
const DEFAULT_RESOURCE_TYPES = [...MONITORED_TYPES].join(',');
const RUNTIME_TYPES = new Set(['app', 'bundle', 'lakehouse', 'minerva', 'nilus-v5', 'service', 'vulcan', 'vulcantest', 'worker', 'workflow']);
const DATA_PRODUCT_TYPES = new Set(['vulcan', 'vulcantest']);
// Official GPT-5.6 Luna standard text-token prices, USD per 1M tokens,
// verified 2026-10-19. This app does not invoke separately billed tools.
const MODEL_PRICING = Object.freeze({
  inputPerMillion: 0.20,
  cachedInputPerMillion: 0.02,
  outputPerMillion: 1.20,
  currency: 'USD',
  source: 'https://developers.openai.com/api/docs/models/gpt-5.6-luna',
  verifiedAt: '2026-10-19',
});

function integer(name, fallback, min, max) {
  const value = Number.parseInt(process.env[name] ?? String(fallback), 10);
  return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
}

export function configFromEnv() {
  return {
    port: integer('PORT', 8080, 1, 65535),
    fqdn: (process.env.DATAOS_FQDN ?? '').replace(/^https?:\/\//, '').replace(/\/$/, ''),
    tenant: process.env.DATAOS_TENANT_ID ?? '',
    apiKey: process.env.DATAOS_RUN_AS_APIKEY ?? '',
    owner: process.env.OBSERVER_OWNER_ID ?? '',
    pollMs: integer('POLL_INTERVAL_SECONDS', 60, 30, 3600) * 1000,
    pendingMs: integer('PENDING_THRESHOLD_SECONDS', 600, 60, 86400) * 1000,
    resourceTypes: (process.env.RESOURCE_TYPES ?? DEFAULT_RESOURCE_TYPES).split(',').map(x => x.trim()).filter(x => MONITORED_TYPES.has(x)),
    stateFile: process.env.STATE_FILE ?? '/etc/dataos/work/state/observer.json',
    modelKeyFile: process.env.MODEL_KEY_FILE ?? '/etc/dataos/work/state/openai-key.enc',
    model: process.env.OPENAI_MODEL ?? 'gpt-5.6-luna',
    skillFile: process.env.DIAGNOSTIC_SKILL_FILE ?? '/etc/dataos/work/observer/skills/dataos-cli-diagnostics/SKILL.md',
  };
}

function emptyState() {
  return { version: 1, resources: {}, incidents: {}, lastScanAt: null, scanError: null, coverageErrors: [], scans: 0,
    modelUsage: { requests: 0, input: 0, cachedInput: 0, output: 0, total: 0, estimatedCostUsd: 0 } };
}

function stringValue(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
}

function pick(object, paths) {
  for (const path of paths) {
    let value = object;
    for (const part of path.split('.')) value = value && typeof value === 'object' ? value[part] : undefined;
    const scalar = stringValue(value).trim();
    if (scalar) return scalar;
  }
  return '';
}

function itemsFromPayload(payload) {
  if (Array.isArray(payload)) return payload;
  for (const key of ['resources', 'items', 'data', 'results']) {
    if (Array.isArray(payload?.[key])) return payload[key];
    if (Array.isArray(payload?.[key]?.resources)) return payload[key].resources;
  }
  return [];
}

export function normalizeResources(payload) {
  return itemsFromPayload(payload).map(item => {
    const resourceId = pick(item, ['resourceId', 'resource_id', 'id', 'metadata.resourceId']);
    const parts = resourceId.split(':');
    const type = pick(item, ['type', 'resourceType', 'metadata.type']) || parts[0] || 'unknown';
    const version = pick(item, ['version', 'resourceVersion', 'metadata.version']) || parts[1] || 'unknown';
    const name = pick(item, ['name', 'resourceName', 'metadata.name']) || parts[2] || resourceId || 'unknown';
    const status = pick(item, ['status.aggregateStatus', 'status.status', 'aggregateStatus', 'status', 'state']);
    const runtime = pick(item, ['status.runtimeStatus', 'status.runtime', 'runtimeStatus', 'runtime.status', 'runtime']);
    const owner = pick(item, ['owner', 'metadata.owner', 'createdBy']);
    const error = pick(item, ['error', 'status.error', 'message']);
    const id = resourceId || `${type}:${version}:${name}`;
    return { id, name, type, version, status: status || 'unknown', runtime: runtime || 'unknown', owner, error };
  }).filter(resource => resource.name !== 'unknown');
}

function includesAny(value, words) {
  const normalized = String(value ?? '').toLowerCase();
  return words.some(word => normalized.includes(word));
}

export function diagnosticPlan(resource) {
  const id = `${resource.type}:${resource.version}:${resource.name}`;
  const commands = [
    `dataos-ctl resource get -i ${id} -d`,
    `dataos-ctl resource deps --id ${id}`,
  ];
  const requests = [
    ['resource', ''],
    ['dependencies', '/dependencies'],
  ];
  if (RUNTIME_TYPES.has(resource.type)) {
    commands.splice(1, 0,
      `dataos-ctl resource get runtime -i ${id} -d`,
      `dataos-ctl resource log -i ${id} -l 80`);
    requests.splice(1, 0,
      ['runtime', '/runtime'],
      ['logs', '/log?tailLines=80']);
  }
  return {
    commands, requests,
    artifactChecks: [
      `Inspect direct dependencies returned for ${id}`,
      `Correlate unhealthy dependencies by timestamp before assigning root cause`,
    ],
    vulcanChecks: DATA_PRODUCT_TYPES.has(resource.type) ? [
      'Vulcan catalog search', 'semantic schema', 'lineage', 'quality/freshness/SLO',
    ] : [],
  };
}

export function redactEvidence(value, maximum = 5000) {
  let text = typeof value === 'string' ? value : JSON.stringify(value);
  text = text
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer [REDACTED]')
    .replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g, '[REDACTED_API_KEY]')
    .replace(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g, '[REDACTED_TOKEN]')
    .replace(/("(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)"\s*:\s*")[^"]*(")/gi, '$1[REDACTED]$2');
  return text.slice(0, maximum);
}

export function sanitizeArtifactEvidence(value, depth = 0) {
  if (depth > 8) return '[TRUNCATED]';
  if (Array.isArray(value)) return value.map(item => sanitizeArtifactEvidence(item, depth + 1));
  if (!value || typeof value !== 'object') return value;
  const identity = [value.type, value.resourceType, value.resourceId, value.id].filter(Boolean).join(':');
  if (/(^|:)(secret|grant|role|user)(:|$)/i.test(identity)) {
    return { restricted: true, type: String(value.type || value.resourceType || 'sensitive-artifact') };
  }
  const safe = {};
  for (const [key, item] of Object.entries(value)) {
    if (/^(password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|spec)$/i.test(key)) safe[key] = '[REDACTED]';
    else safe[key] = sanitizeArtifactEvidence(item, depth + 1);
  }
  return safe;
}

// A dependency graph can be denied when it contains Secret/IAM nodes. In that
// case, derive only allowlisted operational references from the already
// sanitized resource manifest instead of widening the observer's privileges.
export function safeManifestArtifacts(value, source = '') {
  const artifacts = new Map();
  let restrictedReferences = 0;
  const add = (type, version, name) => {
    if (!MONITORED_TYPES.has(type) || !name) return;
    const id = `${type}:${version || 'unknown'}:${name}`;
    if (id !== source) artifacts.set(id, { type, version: version || 'unknown', name });
  };
  const walk = (item, key = '', depth = 0) => {
    if (depth > 10 || item === null || item === undefined) return;
    if (/password|passwd|secret|token|api[_-]?key|access[_-]?key|credential/i.test(key)) {
      restrictedReferences += 1;
      return;
    }
    if (Array.isArray(item)) {
      for (const child of item) walk(child, key, depth + 1);
      return;
    }
    if (typeof item === 'object') {
      for (const [childKey, child] of Object.entries(item)) walk(child, childKey, depth + 1);
      return;
    }
    if (typeof item !== 'string') return;
    for (const match of item.matchAll(/\b([a-z][a-z0-9-]*):(v\d+(?:alpha|beta)?):([a-z0-9][a-z0-9._-]*)\b/gi)) {
      add(match[1].toLowerCase(), match[2].toLowerCase(), match[3]);
    }
    if (/^compute$/i.test(key)) add('compute', '', item);
    if (/depots?/i.test(key)) {
      const depot = item.match(/^dataos:\/\/([^?/#]+)/i)?.[1];
      if (depot) add('depot', '', depot);
    }
  };
  walk(value);
  return {
    source,
    note: 'Dependency graph included restricted nodes; showing only safe operational references derived from the sanitized resource manifest.',
    artifacts: [...artifacts.values()].sort((a, b) => `${a.type}:${a.name}`.localeCompare(`${b.type}:${b.name}`)),
    restrictedReferences,
  };
}

export function responseUsage(payload) {
  const usage = payload?.usage ?? {};
  const input = Math.max(0, Number(usage.input_tokens) || 0);
  const output = Math.max(0, Number(usage.output_tokens) || 0);
  const cachedInput = Math.min(input, Math.max(0, Number(usage.input_tokens_details?.cached_tokens) || 0));
  const uncachedInput = input - cachedInput;
  const estimatedCostUsd = (uncachedInput * MODEL_PRICING.inputPerMillion
    + cachedInput * MODEL_PRICING.cachedInputPerMillion
    + output * MODEL_PRICING.outputPerMillion) / 1_000_000;
  return { input, cachedInput, output, total: Number(usage.total_tokens) || input + output, estimatedCostUsd };
}

export function extractBearerToken(value) {
  const match = String(value ?? '').match(/^Bearer\s+([^\s]+)$/i);
  return match?.[1] ?? '';
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
      method: 'POST',
      signal: AbortSignal.timeout(10000),
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) return { status: 401, error: 'Invalid or expired DataOS session' };
    const result = await response.json();
    if (!result?.valid || !result?.allow) return { status: 401, error: 'Invalid or expired DataOS session' };
    if (result?.result?.id !== cfg.owner) return { status: 403, error: 'This dashboard is restricted to its owner' };
    return { status: 200, userId: result.result.id };
  } catch {
    return { status: 503, error: 'DataOS authorization service is unavailable' };
  }
}

export async function validateModelKey(apiKey, model, fetchImpl = fetch) {
  try {
    const response = await fetchImpl(`https://api.openai.com/v1/models/${encodeURIComponent(model)}`, {
      signal: AbortSignal.timeout(15000),
      headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' },
    });
    if (response.ok) return { ok: true };
    if (response.status === 401) return { ok: false, error: 'OpenAI rejected this API key' };
    if (response.status === 403 || response.status === 404) return { ok: false, error: `This API key cannot access ${model}` };
    return { ok: false, error: `OpenAI validation failed (HTTP ${response.status})` };
  } catch {
    return { ok: false, error: 'OpenAI could not be reached; the key was not saved' };
  }
}

export function classifyResource(resource, previous, nowMs, pendingMs) {
  const signal = `${resource.status} ${resource.runtime} ${resource.error ?? ''}`.toLowerCase();
  if (includesAny(signal, FAILURE_WORDS)) {
    const error = resource.error ? `; error ${resource.error}` : '';
    return { kind: 'failure', severity: 'critical', reason: `Status ${resource.status}; runtime ${resource.runtime}${error}`, pendingSince: null };
  }
  const replicas = String(resource.runtime).match(/^running:(\d+)\/(\d+)$/i);
  if (replicas && Number(replicas[1]) < Number(replicas[2])) {
    return { kind: 'replica-shortfall', severity: 'critical', reason: `Only ${replicas[1]} of ${replicas[2]} replicas are running`, pendingSince: null };
  }
  if (includesAny(signal, PENDING_WORDS)) {
    const pendingSince = previous?.pendingSince ?? new Date(nowMs).toISOString();
    const age = nowMs - Date.parse(pendingSince);
    if (age >= pendingMs) {
      return { kind: 'stuck-pending', severity: 'warning', reason: `Pending for ${Math.round(age / 60000)} minutes`, pendingSince };
    }
    return { kind: null, pendingSince };
  }
  if (resource.status !== 'unknown' && resource.runtime !== 'unknown' && !includesAny(signal, HEALTHY_WORDS)) {
    return { kind: 'unexpected-state', severity: 'warning', reason: `Unexpected status ${resource.status}; runtime ${resource.runtime}`, pendingSince: null };
  }
  return { kind: null, pendingSince: null };
}

function publicState(state, modelInfo, cfg) {
  const incidents = Object.values(state.incidents).sort((a, b) => b.lastSeenAt.localeCompare(a.lastSeenAt));
  const resources = Object.values(state.resources).sort((a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name));
  const byType = Object.fromEntries(cfg.resourceTypes.map(type => [type, resources.filter(item => item.type === type).length]));
  const products = resources.filter(item => DATA_PRODUCT_TYPES.has(item.type));
  return {
    tenant: cfg.tenant,
    owner: cfg.owner,
    monitoredTypes: cfg.resourceTypes,
    pollIntervalSeconds: cfg.pollMs / 1000,
    pendingThresholdSeconds: cfg.pendingMs / 1000,
    lastScanAt: state.lastScanAt,
    scanError: state.scanError,
    coverageErrors: state.coverageErrors ?? [],
    scans: state.scans,
    resources,
    incidents,
    counts: {
      resources: resources.length,
      active: incidents.filter(x => x.state === 'active').length,
      critical: incidents.filter(x => x.state === 'active' && x.severity === 'critical').length,
      resolved: incidents.filter(x => x.state === 'resolved').length,
      products: products.length,
      unhealthyProducts: incidents.filter(x => x.state === 'active' && DATA_PRODUCT_TYPES.has(x.resource.type)).length,
      byType,
    },
    model: modelInfo,
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

async function saveState(path, state) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = `${path}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
  await chmod(temporary, 0o600);
  await rename(temporary, path);
}

function modelKeyEncryptionKey(runtimeApiKey) {
  return createHash('sha256').update('dataos-operations-observer:model-key:v1\0').update(runtimeApiKey).digest();
}

export async function saveEncryptedModelKey(path, modelKey, runtimeApiKey) {
  if (!path || !modelKey || !runtimeApiKey) throw new Error('Encrypted model-key storage is not configured');
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', modelKeyEncryptionKey(runtimeApiKey), iv);
  const ciphertext = Buffer.concat([cipher.update(modelKey, 'utf8'), cipher.final()]);
  const payload = { version: 1, algorithm: 'aes-256-gcm', iv: iv.toString('base64'),
    ciphertext: ciphertext.toString('base64'), tag: cipher.getAuthTag().toString('base64') };
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = `${path}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(payload)}\n`, { mode: 0o600 });
  await chmod(temporary, 0o600);
  await rename(temporary, path);
}

export async function loadEncryptedModelKey(path, runtimeApiKey) {
  try {
    const payload = JSON.parse(await readFile(path, 'utf8'));
    if (payload.version !== 1 || payload.algorithm !== 'aes-256-gcm') return '';
    const decipher = createDecipheriv('aes-256-gcm', modelKeyEncryptionKey(runtimeApiKey), Buffer.from(payload.iv, 'base64'));
    decipher.setAuthTag(Buffer.from(payload.tag, 'base64'));
    return Buffer.concat([decipher.update(Buffer.from(payload.ciphertext, 'base64')), decipher.final()]).toString('utf8');
  } catch {
    return '';
  }
}

function outputText(payload) {
  if (typeof payload?.output_text === 'string') return payload.output_text.trim();
  return (payload?.output ?? []).flatMap(x => x.content ?? []).map(x => x.text ?? '').join('\n').trim();
}

export async function createObserver(overrides = {}) {
  const cfg = { ...configFromEnv(), ...overrides };
  let state = await loadState(cfg.stateFile);
  let sessionModelKey = await loadEncryptedModelKey(cfg.modelKeyFile, cfg.apiKey);
  let modelUsage = { requests: 0, input: 0, cachedInput: 0, output: 0, total: 0, estimatedCostUsd: 0,
    ...(state.modelUsage ?? {}) };
  let diagnosticSkill = '';
  try { diagnosticSkill = await readFile(cfg.skillFile, 'utf8'); } catch { diagnosticSkill = 'Use only supplied read-only DataOS evidence. Never claim an unverified root cause or remediation.'; }
  let scanPromise = null;
  const clients = new Set();

  const modelInfo = () => ({
    configured: Boolean(sessionModelKey),
    source: sessionModelKey ? 'encrypted stateful storage' : 'none',
    model: cfg.model,
    usage: modelUsage,
    pricing: MODEL_PRICING,
  });

  const broadcast = () => {
    const event = `event: state\ndata: ${JSON.stringify(publicState(state, modelInfo(), cfg))}\n\n`;
    for (const response of clients) response.write(event);
  };

  const dataosHeaders = () => ({ apikey: cfg.apiKey, Authorization: `Bearer ${cfg.apiKey}`, Accept: 'application/json' });

  async function diagnosticEvidence(incident) {
    const plan = diagnosticPlan(incident.resource);
    const root = `https://${cfg.fqdn}/poros/api/v2/tenants/${encodeURIComponent(cfg.tenant)}/resources/${encodeURIComponent(incident.resource.type)}/${encodeURIComponent(incident.resource.name)}`;
    const evidence = {};
    const errors = [];
    for (const [label, suffix] of plan.requests) {
      try {
        const response = await fetch(root + suffix, { signal: AbortSignal.timeout(15000), headers: dataosHeaders() });
        if (!response.ok) {
          errors.push(`${label}: HTTP ${response.status}`);
          continue;
        }
        const payload = await response.json();
        evidence[label] = redactEvidence(label === 'dependencies' ? sanitizeArtifactEvidence(payload) : payload, label === 'logs' ? 6000 : 4000);
      } catch (error) {
        errors.push(`${label}: ${String(error.message || error).slice(0, 100)}`);
      }
    }
    return { commands: plan.commands, evidence, errors };
  }

  async function enrichArtifacts(incident) {
    if (incident.diagnostics?.artifacts) return;
    const root = `https://${cfg.fqdn}/poros/api/v2/tenants/${encodeURIComponent(cfg.tenant)}/resources/${encodeURIComponent(incident.resource.type)}/${encodeURIComponent(incident.resource.name)}`;
    const diagnostics = { ...(incident.diagnostics ?? {}), commands: diagnosticPlan(incident.resource).commands, collectedAt: new Date().toISOString() };
    try {
      const response = await fetch(`${root}/dependencies`, { signal: AbortSignal.timeout(15000), headers: dataosHeaders() });
      if (response.status === 204) {
        diagnostics.artifacts = JSON.stringify({ inbound: [], outbound: [] });
      } else if (response.status === 403) {
        const resourceResponse = await fetch(root, { signal: AbortSignal.timeout(15000), headers: dataosHeaders() });
        if (!resourceResponse.ok) throw new Error(`Dependency API HTTP 403; safe manifest fallback HTTP ${resourceResponse.status}`);
        const manifest = await resourceResponse.json();
        diagnostics.artifacts = redactEvidence(safeManifestArtifacts(manifest, incident.resource.id), 4000);
      } else {
        if (!response.ok) throw new Error(`Dependency API HTTP ${response.status}`);
        diagnostics.artifacts = redactEvidence(sanitizeArtifactEvidence(await response.json()), 4000);
      }
      delete diagnostics.artifactError;
    } catch (error) {
      diagnostics.artifactError = String(error.message || error).slice(0, 120);
    }
    incident.diagnostics = diagnostics;
    await saveState(cfg.stateFile, state);
    broadcast();
  }

  async function analyzeIncident(incident) {
    const key = sessionModelKey;
    if (!key || incident.analysis) return;
    try {
      const diagnostics = await diagnosticEvidence(incident);
      incident.diagnostics = {
        ...(incident.diagnostics ?? {}),
        commands: diagnostics.commands,
        artifacts: diagnostics.evidence.dependencies ?? '',
        available: Object.keys(diagnostics.evidence),
        errors: diagnostics.errors,
        collectedAt: new Date().toISOString(),
      };
      const response = await fetch('https://api.openai.com/v1/responses', {
        method: 'POST', signal: AbortSignal.timeout(30000),
        headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: cfg.model,
          instructions: diagnosticSkill.slice(0, 12000),
          input: JSON.stringify({ tenant: cfg.tenant, resource: incident.resource, reason: incident.reason,
            firstSeenAt: incident.firstSeenAt, readOnlyDiagnostics: diagnostics }),
          max_output_tokens: 550,
        }),
      });
      if (!response.ok) throw new Error(`model HTTP ${response.status}`);
      const payload = await response.json();
      const usage = responseUsage(payload);
      modelUsage = {
        requests: modelUsage.requests + 1,
        input: modelUsage.input + usage.input,
        cachedInput: modelUsage.cachedInput + usage.cachedInput,
        output: modelUsage.output + usage.output,
        total: modelUsage.total + usage.total,
        estimatedCostUsd: modelUsage.estimatedCostUsd + usage.estimatedCostUsd,
      };
      state.modelUsage = modelUsage;
      incident.llmUsage = usage;
      const text = outputText(payload);
      if (text) incident.analysis = text.slice(0, 4000);
    } catch (error) {
      incident.analysisError = String(error.message || error).slice(0, 200);
    }
    await saveState(cfg.stateFile, state);
    broadcast();
  }

  async function fetchResources() {
    if (!cfg.fqdn || !cfg.tenant || !cfg.apiKey) throw new Error('DataOS runtime identity is not projected');
    const base = `https://${cfg.fqdn}/poros/api/v2/tenants/${encodeURIComponent(cfg.tenant)}/resources`;
    const groups = await Promise.all(cfg.resourceTypes.map(async type => {
      try {
        const response = await fetch(`${base}/${encodeURIComponent(type)}`, { signal: AbortSignal.timeout(25000), headers: dataosHeaders() });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return { type, resources: normalizeResources(await response.json()), error: '' };
      } catch (error) {
        return { type, resources: [], error: String(error.message || error).slice(0, 120) };
      }
    }));
    const errors = groups.filter(group => group.error).map(group => `${group.type}: ${group.error}`);
    if (errors.length === groups.length) throw new Error(`Every DataOS resource API failed: ${errors.join('; ')}`);
    return { resources: groups.flatMap(group => group.resources), errors };
  }

  async function scan() {
    if (scanPromise) return scanPromise;
    scanPromise = (async () => {
      try {
        const now = new Date();
        const nowMs = now.getTime();
        const fetched = await fetchResources();
        const resources = fetched.resources;
        const observedIncidentIds = new Set();
        const newIncidents = [];
        const seenResources = new Set();
        for (const resource of resources) {
          seenResources.add(resource.id);
          const previous = state.resources[resource.id];
          const result = classifyResource(resource, previous, nowMs, cfg.pendingMs);
          state.resources[resource.id] = { ...resource, pendingSince: result.pendingSince, observedAt: now.toISOString() };
          if (!result.kind) continue;
          const incidentId = `${resource.id}:${result.kind}`;
          observedIncidentIds.add(incidentId);
          const existing = state.incidents[incidentId];
          if (existing) {
            existing.state = 'active';
            existing.lastSeenAt = now.toISOString();
            existing.reason = result.reason;
            existing.occurrences += 1;
            existing.resource = resource;
          } else {
            state.incidents[incidentId] = {
              id: incidentId, kind: result.kind, severity: result.severity, state: 'active', acknowledged: false,
              reason: result.reason, resource, firstSeenAt: now.toISOString(), lastSeenAt: now.toISOString(),
              resolvedAt: null, occurrences: 1, analysis: '', analysisError: '',
            };
            newIncidents.push(state.incidents[incidentId]);
          }
        }
        for (const incident of Object.values(state.incidents)) {
          if (incident.state === 'active' && seenResources.has(incident.resource.id) && !observedIncidentIds.has(incident.id)) {
            incident.state = 'resolved';
            incident.resolvedAt = now.toISOString();
          }
        }
        const retained = Object.values(state.incidents).sort((a, b) => b.lastSeenAt.localeCompare(a.lastSeenAt)).slice(0, 1000);
        state.incidents = Object.fromEntries(retained.map(item => [item.id, item]));
        state.lastScanAt = now.toISOString();
        state.coverageErrors = fetched.errors;
        state.scanError = fetched.errors.length ? `Partial scan: ${fetched.errors.length} resource type${fetched.errors.length === 1 ? '' : 's'} unavailable` : null;
        state.scans += 1;
        await saveState(cfg.stateFile, state);
        broadcast();
        for (const incident of Object.values(state.incidents).filter(item => item.state === 'active' && !item.analysis)) {
          if (!incident.diagnostics?.artifacts) void enrichArtifacts(incident).then(() => analyzeIncident(incident));
          else void analyzeIncident(incident);
        }
        return publicState(state, modelInfo(), cfg);
      } catch (error) {
        state.scanError = String(error.message || error).slice(0, 300);
        state.lastScanAt = new Date().toISOString();
        state.scans += 1;
        await saveState(cfg.stateFile, state);
        broadcast();
        throw error;
      } finally {
        scanPromise = null;
      }
    })();
    return scanPromise;
  }

  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://observer.local');
    const headers = {
      'Cache-Control': 'no-store',
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
      'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
    };
    const json = (status, body) => { response.writeHead(status, { ...headers, 'Content-Type': 'application/json' }); response.end(JSON.stringify(body)); };
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
          if (authorization.status === 200 || authorization.status === 403 || authorization.status === 503) break;
        }
        if (authorization.status !== 200) return json(authorization.status, { error: authorization.error });
      }
      if (request.method === 'GET' && url.pathname === '/api/state') return json(200, publicState(state, modelInfo(), cfg));
      if (request.method === 'GET' && url.pathname === '/api/events') {
        response.writeHead(200, { ...headers, 'Content-Type': 'text/event-stream', Connection: 'keep-alive' });
        clients.add(response);
        response.write(`event: state\ndata: ${JSON.stringify(publicState(state, modelInfo(), cfg))}\n\n`);
        request.on('close', () => clients.delete(response));
        return;
      }
      if (request.method === 'POST' && url.pathname === '/api/scan') {
        await scan();
        return json(202, { ok: true });
      }
      if (request.method === 'POST' && url.pathname === '/api/settings/model-key') {
        if ((request.headers['sec-fetch-site'] ?? 'same-origin') === 'cross-site') return json(403, { error: 'Cross-site request rejected' });
        let body = '';
        for await (const chunk of request) { body += chunk; if (body.length > 4096) throw new Error('Request body too large'); }
        const key = String(JSON.parse(body || '{}').apiKey ?? '').trim();
        if (key.length < 20 || key.length > 512 || /\s/.test(key)) return json(400, { error: 'Invalid API key' });
        const validation = await validateModelKey(key, cfg.model);
        if (!validation.ok) return json(400, { error: validation.error });
        await saveEncryptedModelKey(cfg.modelKeyFile, key, cfg.apiKey);
        const fingerprint = createHash('sha256').update(key).digest('hex').slice(0, 16);
        if (state.modelKeyFingerprint !== fingerprint) {
          modelUsage = { requests: 0, input: 0, cachedInput: 0, output: 0, total: 0, estimatedCostUsd: 0 };
        }
        sessionModelKey = key;
        state.modelKeyFingerprint = fingerprint;
        state.modelUsage = modelUsage;
        await saveState(cfg.stateFile, state);
        broadcast();
        const pending = Object.values(state.incidents).filter(item => item.state === 'active' && !item.analysis);
        for (const incident of pending) {
          incident.analysisError = '';
          void analyzeIncident(incident);
        }
        return json(200, { configured: true, source: 'encrypted stateful storage', pendingAnalyses: pending.length,
          message: pending.length ? `Saved securely. Diagnosing ${pending.length} active incident${pending.length === 1 ? '' : 's'}…` : 'Saved securely. New incidents will be diagnosed automatically.' });
      }
      const match = url.pathname.match(/^\/api\/incidents\/(.+)\/ack$/);
      if (request.method === 'POST' && match) {
        const id = decodeURIComponent(match[1]);
        if (!state.incidents[id]) return json(404, { error: 'Incident not found' });
        state.incidents[id].acknowledged = true;
        state.incidents[id].acknowledgedAt = new Date().toISOString();
        await saveState(cfg.stateFile, state);
        broadcast();
        return json(200, { ok: true });
      }
      return json(404, { error: 'Not found' });
    } catch (error) {
      return json(500, { error: String(error.message || error).slice(0, 200) });
    }
  });

  let timer;
  return {
    cfg, server, scan,
    start() {
      server.listen(cfg.port, '0.0.0.0');
      void scan().catch(() => {});
      timer = setInterval(() => void scan().catch(() => {}), cfg.pollMs);
      timer.unref();
      return server;
    },
    async stop() { clearInterval(timer); await new Promise(resolve => server.close(resolve)); },
    snapshot: () => publicState(state, modelInfo(), cfg),
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const observer = await createObserver();
  observer.start();
  console.log(JSON.stringify({ event: 'observer.started', port: observer.cfg.port, tenant: observer.cfg.tenant }));
}
