const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const {preview, parseOptions, safeMessage} = require('./preview.cjs');
const {dockerEnvironment} = require('../publish/publish.cjs');
const {githubFixture, HEAD, TOKEN} = require('./test-support.cjs');

function fixture() {
  const f = githubFixture();
  f.renderCalls = [];
  f.render = async (...args) => { f.renderCalls.push(args); return 'Test step (reported): **success**'; };
  f.publish = () => preview(f.options, {token:f.token, fetcher:f.fetcher, render:f.render});
  return f;
}

test('explicit fork evidence creates then updates one author-owned preview with API provenance', async () => {
  const f = fixture();
  const first = await f.publish();
  f.state.run.conclusion = 'failure';
  const second = await f.publish();
  assert.equal(first.url, 'https://github.com/target/app/pull/12#issuecomment-200');
  assert.equal(second.url, first.url);
  assert.deepEqual(f.state.writes.map(c => c.method), ['POST', 'PATCH']);
  const body = f.state.comments[0].body;
  assert.match(body, /Preview from the PR contributor/);
  assert.match(body, /^## 🔴 Fork workflow failed/);
  assert.match(body, /> \[!CAUTION\]/);
  assert.match(body, /No installation, repository access or credentials were requested/);
  assert.match(body, /Test step \(reported\): \*\*success\*\*/);
  assert.ok(body.includes(HEAD));
  assert.match(body, /https:\/\/github.com\/author\/app\/actions\/runs\/100\/attempts\/1/);
  assert.equal(JSON.stringify(f.renderCalls).includes(TOKEN), false);
  for (const call of f.state.calls) {
    assert.equal(call.headers?.authorization, call.url.startsWith('https://api.github.com/') ? `Bearer ${TOKEN}` : undefined);
  }
  await assert.rejects(fs.stat(f.renderCalls[0][1]), {code:'ENOENT'});
});

for (const [name, change] of [
  ['closed PR', f => { f.state.pr.state = 'closed'; }],
  ['another author', f => { f.state.pr.user = {id:999}; }],
  ['bot authentication', f => { f.state.viewer.type = 'Bot'; }],
  ['deleted fork', f => { f.state.pr.head.repo = null; }],
  ['private target', f => { f.state.pr.base.repo.private = true; }],
  ['private fork', f => { f.state.pr.head.repo.private = true; }],
  ['different fork', f => { f.state.run.repository.id = 99; }],
  ['different commit', f => { f.state.run.head_sha = 'b'.repeat(40); }],
  ['different branch', f => { f.state.run.head_branch = 'other'; }],
  ['incomplete run', f => { f.state.run.status = 'in_progress'; }],
  ['PR merge run', f => { f.state.run.event = 'pull_request'; }],
  ['no artifact', f => { f.state.artifacts = []; }],
  ['ambiguous artifact', f => { f.state.artifacts.push({...f.state.artifacts[0], id:41}); }],
  ['expired artifact', f => { f.state.artifacts[0].expired = true; }],
]) test(`${name} cannot publish`, async () => {
  const f = fixture(); change(f);
  await assert.rejects(f.publish());
  assert.equal(f.state.writes.length, 0);
});

test('an explicitly selected older attempt keeps its own GitHub conclusion', async () => {
  const f = fixture();
  f.state.attempts[1] = {...f.state.run, conclusion:'failure'};
  f.state.run.run_attempt = 2;
  f.options.run += '/attempts/1';
  await f.publish();
  assert.match(f.state.comments[0].body, /^## 🔴 Fork workflow failed/);
  assert.match(f.state.comments[0].body, /"attempt":1/);
});

test('a deleted preview is recreated and malformed author-owned metadata is repaired', async () => {
  const f = fixture(); await f.publish();
  f.state.comments[0].body = f.state.comments[0].body.replace(/preview-snapshot:.*? -->/, 'preview-snapshot:broken -->');
  await f.publish();
  assert.equal(f.state.writes.at(-1).method, 'PATCH');
  assert.match(f.state.comments[0].body, /"attempt":1/);
  f.state.comments.length = 0;
  await f.publish();
  assert.equal(f.state.writes.at(-1).method, 'POST');
});

test('PR movement during rendering preserves the previous comment', async () => {
  const f = fixture(); await f.publish();
  const before = f.state.comments[0].body;
  f.render = async () => { f.state.pr.head.sha = 'b'.repeat(40); return 'new output'; };
  await assert.rejects(f.publish(), /changed/);
  assert.equal(f.state.writes.length, 1);
  assert.equal(f.state.comments[0].body, before);
});

test('copied trailers, Actions comments and markers inside prose cannot claim the author preview', async () => {
  const f = fixture(); await f.publish();
  const original = f.state.comments.pop();
  const others = [
    {...original, id:501, user:{id:999, login:'intruder', type:'User'}},
    {...original, id:502, user:{id:998, login:'github-actions[bot]', type:'Bot'}},
    {...original, id:503, body:`${original.body}\nordinary discussion after the marker`},
  ];
  f.state.comments.push(...others);
  await f.publish();
  assert.equal(f.state.writes.at(-1).method, 'POST');
  assert.deepEqual(f.state.comments.slice(0, 3), others);
});

test('older run attempts never replace newer preview evidence', async () => {
  const f = fixture(); await f.publish();
  f.state.comments[0].body = f.state.comments[0].body.replace('"attempt":1', '"attempt":2');
  const result = await f.publish();
  assert.equal(result.status, 'newer-preview-exists');
  assert.equal(f.state.writes.length, 1);
});

for (const kind of ['invalid digest', 'oversize download', 'renderer failure', 'oversize output']) test(`${kind} gives an unavailable preview without raw diagnostics`, async () => {
  const f = fixture();
  if (kind === 'invalid digest') f.state.artifacts[0].digest = 'invalid';
  if (kind === 'oversize download') f.state.artifacts[0].size_in_bytes = 33 * 1024 * 1024;
  if (kind === 'renderer failure') f.render = async () => { throw new Error(`stderr ${TOKEN}`); };
  if (kind === 'oversize output') f.render = async () => 'x'.repeat(56000);
  await f.publish();
  assert.match(f.state.comments[0].body, /Evidence unavailable/);
  assert.equal(f.state.comments[0].body.includes(TOKEN), false);
});

test('API redirects never receive a second authenticated request', async () => {
  const f = fixture();
  let calls = 0;
  f.fetcher = async (url, options) => { calls++; assert.equal(options.redirect, 'error'); return new Response(null, {status:302}); };
  await assert.rejects(f.publish(), /GitHub/);
  assert.equal(calls, 1);
});

test('Docker receives a small operating-system environment, never caller credentials or interpreter hooks', () => {
  const env = dockerEnvironment({PATH:'/bin', HOME:'/home/example', SYSTEMROOT:'C:\\Windows',
    GH_TOKEN:TOKEN, GITHUB_TOKEN:TOKEN, AWS_SECRET_ACCESS_KEY:TOKEN, NODE_OPTIONS:'--require=evil',
    PYTHONPATH:'/untrusted', DOCKER_AUTH_CONFIG:TOKEN});
  assert.deepEqual(env, {PATH:'/bin', HOME:'/home/example', SYSTEMROOT:'C:\\Windows'});
});

test('options accept only explicit GitHub public PR/run URLs and a bounded artifact key', () => {
  const args = ['--pr','https://github.com/target/app/pull/12','--run','https://github.com/author/app/actions/runs/100/attempts/2'];
  assert.equal(parseOptions(args).attempt, 2);
  for (const bad of ['https://evil.invalid/target/app/pull/12', 'https://github.com@evil.invalid/target/app/pull/12', 'https://github.com/target/app/pull/12?token=secret']) {
    assert.throws(() => parseOptions(['--pr',bad,...args.slice(2)]));
  }
  assert.throws(() => parseOptions([...args,'--token',TOKEN]));
  assert.throws(() => parseOptions([...args,'--sticky-key','../unsafe']));
  assert.equal(safeMessage(new Error(`raw subprocess output ${TOKEN}`)).includes(TOKEN), false);
});
