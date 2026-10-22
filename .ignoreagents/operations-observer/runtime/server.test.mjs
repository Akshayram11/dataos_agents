import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { authorizeOwnerToken, classifyResource, createObserver, diagnosticPlan, extractBearerToken, loadEncryptedModelKey, normalizeResources, redactEvidence, requestCredentialCandidates, responseUsage, safeManifestArtifacts, sanitizeArtifactEvidence, saveEncryptedModelKey, validateModelKey } from './server.mjs';

test('normalizes DataOS thin resource payloads', () => {
  const resources = normalizeResources({ resources: [
    { name: 'orders-api', version: 'v1', type: 'service', status: 'active', runtime: 'running:1', owner: 'team' },
    { resourceId: 'workflow:v1:daily-sales', aggregateStatus: 'error', runtimeStatus: 'failed' },
  ] });
  assert.equal(resources.length, 2);
  assert.deepEqual(resources[0], { id: 'service:v1:orders-api', name: 'orders-api', version: 'v1', type: 'service', status: 'active', runtime: 'running:1', owner: 'team', error: '' });
  assert.equal(resources[1].name, 'daily-sales');
  assert.equal(resources[1].status, 'error');
});

test('opens failures immediately', () => {
  const result = classifyResource({ status: 'active', runtime: 'failed:1' }, null, Date.now(), 600000);
  assert.equal(result.kind, 'failure');
  assert.equal(result.severity, 'critical');
});

test('detects real DataOS crashing and replica shortfall runtimes', () => {
  assert.equal(classifyResource({ status: 'active', runtime: 'crashing:0/1' }, null, Date.now(), 600000).kind, 'failure');
  assert.equal(classifyResource({ status: 'active', runtime: 'failing:0/1' }, null, Date.now(), 600000).kind, 'failure');
  assert.equal(classifyResource({ status: 'active', runtime: 'running:0/1' }, null, Date.now(), 600000).kind, 'replica-shortfall');
});

test('detects a Vulcan plan failure as a data-product incident', () => {
  const result = classifyResource({ type: 'vulcan', status: 'active', runtime: 'vulcan-api:running:1; vulcan-plan:failed' }, null, Date.now(), 600000);
  assert.equal(result.kind, 'failure');
  assert.equal(result.severity, 'critical');
});

test('Vulcan diagnostics include runtime, logs, dependencies and product checks', () => {
  const plan = diagnosticPlan({ type: 'vulcan', version: 'v1alpha', name: 'customer-360' });
  assert.match(plan.commands.join('\n'), /get runtime/);
  assert.match(plan.commands.join('\n'), /resource log/);
  assert.match(plan.commands.join('\n'), /resource deps/);
  assert.deepEqual(plan.vulcanChecks, ['Vulcan catalog search', 'semantic schema', 'lineage', 'quality/freshness/SLO']);
});

test('escalates pending only after threshold', () => {
  const now = Date.now();
  const fresh = classifyResource({ status: 'active', runtime: 'pending' }, null, now, 600000);
  assert.equal(fresh.kind, null);
  const stuck = classifyResource({ status: 'active', runtime: 'pending' }, { pendingSince: new Date(now - 601000).toISOString() }, now, 600000);
  assert.equal(stuck.kind, 'stuck-pending');
  assert.equal(stuck.severity, 'warning');
});

test('accepts healthy service and completed workflow states', () => {
  assert.equal(classifyResource({ status: 'active', runtime: 'running:1' }, null, Date.now(), 600000).kind, null);
  assert.equal(classifyResource({ status: 'active', runtime: 'succeeded' }, null, Date.now(), 600000).kind, null);
});

test('diagnostic skill exposes only bounded read-only CLI operations', () => {
  const plan = diagnosticPlan({ type: 'service', version: 'v2alpha', name: 'orders-api' });
  assert.deepEqual(plan.commands, [
    'dataos-ctl resource get -i service:v2alpha:orders-api -d',
    'dataos-ctl resource get runtime -i service:v2alpha:orders-api -d',
    'dataos-ctl resource log -i service:v2alpha:orders-api -l 80',
    'dataos-ctl resource deps --id service:v2alpha:orders-api',
  ]);
  assert.ok(plan.commands.every(command => !/apply|delete|run |unSanitize|follow/.test(command)));
});

test('diagnostic evidence redacts credentials before model use', () => {
  const value = redactEvidence({ api_key: 'sk-abcdefghijklmnopqrstuvwxyz', authorization: 'Bearer abc.def-123' });
  assert.equal(value.includes('sk-abcdefghijklmnopqrstuvwxyz'), false);
  assert.equal(value.includes('abc.def-123'), false);
  assert.match(value, /REDACTED/);
});

test('dependency artifact evidence masks credential and IAM resources', () => {
  const safe = sanitizeArtifactEvidence({ dependencies: [
    { resourceId: 'depot:v2alpha:orders', type: 'depot', name: 'orders' },
    { resourceId: 'secret:v2alpha:warehouse-key', type: 'secret', name: 'warehouse-key', spec: { data: 'nope' } },
  ] });
  assert.equal(safe.dependencies[0].name, 'orders');
  assert.deepEqual(safe.dependencies[1], { restricted: true, type: 'secret' });
  assert.equal(JSON.stringify(safe).includes('warehouse-key'), false);
});

test('manifest fallback extracts safe artifacts without exposing secrets', () => {
  const result = safeManifestArtifacts({ spec: {
    compute: 'engineering-compute', depots: ['dataos://cartwelldepot?purpose=full'],
    repo: { secretId: 'engineering:git-sync' },
  }, status: { activeProperties: {
    api: '{"resourceId":"service:v2alpha:customer-360-api"}',
    plan: '{"resourceId":"workflow:v2alpha:customer-360-plan"}',
  } } }, 'vulcan:v1alpha:customer-360');
  assert.deepEqual(result.artifacts, [
    { type: 'compute', version: 'unknown', name: 'engineering-compute' },
    { type: 'depot', version: 'unknown', name: 'cartwelldepot' },
    { type: 'service', version: 'v2alpha', name: 'customer-360-api' },
    { type: 'workflow', version: 'v2alpha', name: 'customer-360-plan' },
  ]);
  assert.equal(result.restrictedReferences, 1);
  assert.equal(JSON.stringify(result).includes('git-sync'), false);
});

test('extracts only a well-formed bearer credential', () => {
  assert.equal(extractBearerToken('Bearer opaque-token'), 'opaque-token');
  assert.equal(extractBearerToken('opaque-token'), '');
  assert.equal(extractBearerToken('Bearer two tokens'), '');
});

test('collects bounded bearer and same-origin cookie credential candidates', () => {
  const values = requestCredentialCandidates({ authorization: 'Bearer header-token-value-12345', cookie: 'short=x; session=cookie-token-value-12345' });
  assert.deepEqual(values, ['header-token-value-12345', 'cookie-token-value-12345']);
});

test('Heimdall authorization allows only the configured owner', async () => {
  const cfg = { fqdn: 'dataos.test', owner: 'akshaychametmdcio' };
  const response = body => async (_url, options) => {
    assert.equal(JSON.parse(options.body).token, 'browser-token');
    return new Response(JSON.stringify(body), { status: 200 });
  };
  assert.equal((await authorizeOwnerToken('', cfg, response({}))).status, 401);
  assert.equal((await authorizeOwnerToken('browser-token', cfg, response({
    valid: true, allow: true, result: { id: 'someone-else', tags: [] },
  }))).status, 403);
  assert.equal((await authorizeOwnerToken('browser-token', cfg, response({
    valid: true, allow: true, result: { id: 'akshaychametmdcio', tags: [] },
  }))).status, 200);
});

test('OpenAI key validation distinguishes credentials from model access', async () => {
  const reply = status => async () => new Response('{}', { status });
  assert.equal((await validateModelKey('key', 'gpt-5.6-luna', reply(200))).ok, true);
  assert.equal((await validateModelKey('key', 'gpt-5.6-luna', reply(401))).error, 'OpenAI rejected this API key');
  assert.match((await validateModelKey('key', 'gpt-5.6-luna', reply(404))).error, /cannot access/);
});

test('calculates GPT-5.6 Luna usage and estimated standard API cost', () => {
  const usage = responseUsage({ usage: { input_tokens: 1_000_000, output_tokens: 100_000,
    total_tokens: 1_100_000, input_tokens_details: { cached_tokens: 200_000 } } });
  assert.deepEqual(usage, { input: 1_000_000, cachedInput: 200_000, output: 100_000,
    total: 1_100_000, estimatedCostUsd: 0.284 });
});

test('persists the model key encrypted and bound to the runtime identity', async () => {
  const area = await mkdtemp(join(tmpdir(), 'observer-key-test-'));
  const path = join(area, 'openai-key.enc');
  try {
    await saveEncryptedModelKey(path, 'sk-test-key-that-is-long-enough', 'dataos-runtime-key-a');
    assert.equal(await loadEncryptedModelKey(path, 'dataos-runtime-key-a'), 'sk-test-key-that-is-long-enough');
    assert.equal(await loadEncryptedModelKey(path, 'dataos-runtime-key-b'), '');
    assert.equal((await stat(path)).mode & 0o777, 0o600);
    assert.equal((await readFile(path, 'utf8')).includes('sk-test-key-that-is-long-enough'), false);
  } finally {
    await rm(area, { recursive: true, force: true });
  }
});

test('scan persists, publishes, and auto-resolves an incident', async () => {
  const area = await mkdtemp(join(tmpdir(), 'observer-test-'));
  const stateFile = join(area, 'state.json');
  const originalFetch = globalThis.fetch;
  let runtime = 'crashing:0/1';
  globalThis.fetch = async () => new Response(JSON.stringify({ resources: [
    { name: 'orders-api', version: 'v2alpha', type: 'service', status: 'active', runtime },
  ] }), { status: 200, headers: { 'content-type': 'application/json' } });
  try {
    const observer = await createObserver({ fqdn: 'dataos.test', tenant: 'engineering', apiKey: 'test',
      resourceTypes: ['service'], stateFile, modelKeyFile: join(area, 'missing-key'), pendingMs: 600000 });
    await observer.scan();
    assert.equal(observer.snapshot().counts.critical, 1);
    assert.equal((await stat(stateFile)).mode & 0o777, 0o600);
    runtime = 'running:1';
    await observer.scan();
    assert.equal(observer.snapshot().counts.active, 0);
    assert.equal(observer.snapshot().counts.resolved, 1);
  } finally {
    globalThis.fetch = originalFetch;
    await rm(area, { recursive: true, force: true });
  }
});
