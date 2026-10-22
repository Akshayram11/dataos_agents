import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  ALLOWED_MCP_TOOLS, authorizeOwnerToken, extractBearerToken, inspectMcp,
  loadEncryptedSecrets, parseMcpEnvelope, requestCredentialCandidates,
  responseUsage, safeFailureMessage, safeMcpTools, saveEncryptedSecrets, validateModelKey,
} from './server.mjs';

test('pins the exact Arguss data-product tool boundary', () => {
  assert.deepEqual([...ALLOWED_MCP_TOOLS], [
    'search', 'table_profile', 'get_lineage', 'vulcan_about', 'vulcan_semantic_schema',
    'vulcan_quality', 'vulcan_runs', 'vulcan_query_submit', 'vulcan_query_result',
  ]);
});

test('accepts only allowlisted read-only non-destructive MCP tools', () => {
  const tools = safeMcpTools({ tools: [
    { name: 'search', annotations: { readOnlyHint: true, destructiveHint: false } },
    { name: 'delete_product', annotations: { readOnlyHint: false, destructiveHint: true } },
    { name: 'vulcan_about', annotations: { readOnlyHint: false, destructiveHint: false } },
  ] });
  assert.deepEqual(tools.map(tool => tool.name), ['search']);
});

test('parses streamable HTTP MCP envelopes', () => {
  assert.deepEqual(parseMcpEnvelope('event: message\ndata: {"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n\n', 7), { ok: true });
  assert.throws(() => parseMcpEnvelope('data: {"jsonrpc":"2.0","id":7,"error":{"message":"denied"}}', 7), /denied/);
});

test('MCP inspection discovers only approved tools', async () => {
  const fetchImpl = async (_url, options) => {
    const request = JSON.parse(options.body);
    const result = request.method === 'initialize'
      ? { serverInfo: { name: 'data-product-mcp', version: '4.1.0' }, instructions: 'Discovery first.' }
      : { tools: [
          { name: 'search', description: 'find', inputSchema: { type: 'object' }, annotations: { readOnlyHint: true, destructiveHint: false } },
          { name: 'unsafe', annotations: { readOnlyHint: false, destructiveHint: true } },
        ] };
    return new Response(`event: message\ndata: ${JSON.stringify({ jsonrpc: '2.0', id: request.id, result })}\n\n`, { status: 200 });
  };
  const result = await inspectMcp('https://dataos.test/arguss/mcp/', 'dataos-key', fetchImpl);
  assert.equal(result.server.name, 'data-product-mcp');
  assert.deepEqual(result.tools.map(tool => tool.name), ['search']);
});

test('encrypted storage binds both user keys to the runtime identity', async () => {
  const area = await mkdtemp(join(tmpdir(), 'consumption-agent-secrets-'));
  const path = join(area, 'keys.enc');
  try {
    const secrets = { dataosKey: 'dataos-user-key-that-is-long-enough', openaiKey: 'sk-openai-key-that-is-long-enough' };
    await saveEncryptedSecrets(path, secrets, 'runtime-identity-a');
    assert.deepEqual(await loadEncryptedSecrets(path, 'runtime-identity-a'), secrets);
    assert.equal(await loadEncryptedSecrets(path, 'runtime-identity-b'), null);
    assert.equal((await stat(path)).mode & 0o777, 0o600);
    const encrypted = await readFile(path, 'utf8');
    assert.equal(encrypted.includes(secrets.dataosKey), false);
    assert.equal(encrypted.includes(secrets.openaiKey), false);
  } finally { await rm(area, { recursive: true, force: true }); }
});

test('extracts bounded browser credentials', () => {
  assert.equal(extractBearerToken('Bearer opaque-token'), 'opaque-token');
  assert.equal(extractBearerToken('opaque-token'), '');
  assert.deepEqual(requestCredentialCandidates({
    authorization: 'Bearer header-token-value-12345', cookie: 'session=cookie-token-value-12345',
  }), ['header-token-value-12345', 'cookie-token-value-12345']);
});

test('Heimdall permits only the configured owner', async () => {
  const cfg = { fqdn: 'dataos.test', owner: 'akshaychametmdcio' };
  const reply = id => async () => new Response(JSON.stringify({ valid: true, allow: true, result: { id } }), { status: 200 });
  assert.equal((await authorizeOwnerToken('browser', cfg, reply('someone'))).status, 403);
  assert.equal((await authorizeOwnerToken('browser', cfg, reply('akshaychametmdcio'))).status, 200);
});

test('OpenAI validation reports model access', async () => {
  const reply = status => async () => new Response('{}', { status });
  assert.equal((await validateModelKey('key', 'gpt-5.6-luna', reply(200))).ok, true);
  assert.match((await validateModelKey('key', 'gpt-5.6-luna', reply(404))).error, /cannot access/);
});

test('meters GPT-5.6 Luna standard token pricing', () => {
  assert.deepEqual(responseUsage({ usage: { input_tokens: 1_000_000, output_tokens: 100_000,
    total_tokens: 1_100_000, input_tokens_details: { cached_tokens: 200_000 } } }), {
    input: 1_000_000, cachedInput: 200_000, output: 100_000, total: 1_100_000, estimatedCostUsd: 0.284,
  });
});

test('redacts secrets from recoverable tool failures', () => {
  const message = safeFailureMessage(new Error('bad Bearer secret-token and sk-supersecretkeyvalue'));
  assert.equal(message.includes('secret-token'), false);
  assert.equal(message.includes('sk-supersecretkeyvalue'), false);
});
