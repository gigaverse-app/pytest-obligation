const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const publish = require('./publish.cjs');

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'obligation-publish-'));
  t.after(() => fs.rmSync(dir, {recursive:true, force:true}));
  const file = path.join(dir, 'report.md');
  fs.writeFileSync(file, 'actual rendered report');
  const calls = [], comments = [], notices = [];
  const state = {head:'abc', forbidden:false};
  const github = {rest:{pulls:{get:async () => ({data:{head:{sha:state.head}}})}, issues:{
    listComments: () => {},
    createComment: async args => {if (state.forbidden) throw {status:403}; calls.push(['create', args]);},
    updateComment: async args => calls.push(['update', args]),
  }}, paginate:async () => comments};
  const context = {repo:{owner:'owner', repo:'app'}, eventName:'pull_request', payload:{pull_request:{number:12,
    head:{sha:'abc', repo:{full_name:'owner/app'}}}}};
  const core = {info:x => notices.push(x), warning:x => notices.push(x)};
  const env = {OBLIGATION_MARKDOWN:file, OBLIGATION_STICKY_KEY:'python', GITHUB_RUN_ID:'100', GITHUB_RUN_ATTEMPT:'1'};
  return {calls, comments, notices, state, context, env, run:() => publish({github, context, core}, env)};
}

test('same key updates one bot-owned comment and carries source identity', async t => {
  const f = fixture(t);
  await f.run();
  assert.equal(f.calls[0][0], 'create');
  const body = f.calls[0][1].body;
  assert.ok(body.includes('"head":"abc","run":100,"attempt":1'));
  f.comments.push({id:42, body, user:{login:'github-actions[bot]', type:'Bot'}});
  await f.run();
  assert.equal(f.calls[1][0], 'update');
  assert.equal(f.calls[1][1].comment_id, 42);
});

test('human marker spoof never overwrites a human comment', async t => {
  const f = fixture(t); await f.run();
  f.comments.push({id:42, body:f.calls[0][1].body, user:{login:'aviad', type:'User'}});
  await f.run(); assert.equal(f.calls[1][0], 'create');
});

test('different lanes retain separate stickies', async t => {
  const f = fixture(t); await f.run();
  f.comments.push({id:42, body:f.calls[0][1].body, user:{login:'github-actions[bot]', type:'Bot'}});
  f.env.OBLIGATION_STICKY_KEY = 'integration';
  await f.run(); assert.equal(f.calls[1][0], 'create');
});

for (const change of ['head', 'run', 'attempt']) test(`older ${change} never replaces fresh evidence`, async t => {
  const f = fixture(t); await f.run();
  f.comments.push({id:42, body:f.calls[0][1].body, user:{login:'github-actions[bot]', type:'Bot'}});
  if (change === 'head') f.state.head = 'new-head';
  if (change === 'run') f.env.GITHUB_RUN_ID = '99';
  if (change === 'attempt') f.comments[0].body = f.comments[0].body.replace('"attempt":1', '"attempt":2');
  await f.run(); assert.equal(f.calls.length, 1);
});

test('forks never publish, even if caller requests publication', async t => {
  const f = fixture(t); f.context.payload.pull_request.head.repo.full_name = 'fork/app';
  await f.run(); assert.equal(f.calls.length, 0);
});

test('unavailable comment permission preserves summary-only delivery', async t => {
  const f = fixture(t); f.state.forbidden = true;
  await f.run(); assert.ok(f.notices.some(x => x.includes('retained in summary/artifact')));
});

test('broken bot snapshot is repairable', async t => {
  const f = fixture(t); await f.run();
  f.comments.push({id:42, body:f.calls[0][1].body.replace(/snapshot:.*? -->/, 'snapshot:broken -->'), user:{login:'github-actions[bot]', type:'Bot'}});
  await f.run(); assert.equal(f.calls[1][0], 'update');
});
