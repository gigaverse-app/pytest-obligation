const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const publish = require('./publish.cjs');
const {publishSticky, resolveTriggeringRun} = publish;

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'obligation-publish-'));
  t.after(() => fs.rmSync(dir, {recursive:true, force:true}));
  const file = path.join(dir, 'report.md');
  fs.writeFileSync(file, 'actual rendered report');
  const calls = [], comments = [], notices = [], summary = [], requests = [];
  const state = {head:'abc', forbidden:false, pulls:[], artifacts:[], run:{}};
  const github = {rest:{
    pulls:{
      get:async () => ({data:{head:{sha:state.head}}}),
      list:params => { requests.push(['pulls', params]); return state.pulls; },
    },
    issues:{
      listComments: () => {},
      createComment: async args => {if (state.forbidden) throw {status:403}; calls.push(['create', args]);},
      updateComment: async args => calls.push(['update', args]),
    },
    actions:{
      getWorkflowRun:async params => { requests.push(['run', params]); return {data:state.run}; },
      getWorkflowRunAttempt:async params => ({data:{...state.run, conclusion:state.attemptConclusion || 'failure', run_attempt:params.attempt_number}}),
      listWorkflowRunArtifacts:params => { requests.push(['artifacts', params]); return state.artifacts; },
    },
  }};
  github.paginate = async (method, params) => method === github.rest.issues.listComments ? comments : method(params);
  const context = {repo:{owner:'owner', repo:'app'}, eventName:'pull_request', payload:{pull_request:{number:12,
    head:{sha:'abc', repo:{full_name:'owner/app'}}}}};
  const core = {info:x => notices.push(x), warning:x => notices.push(x), notice:x => notices.push(x),
    summary:{addRaw(x) { summary.push(x); return this; }, async write() {}}};
  const env = {OBLIGATION_MARKDOWN:file, OBLIGATION_STICKY_KEY:'python', GITHUB_RUN_ID:'100', GITHUB_RUN_ATTEMPT:'1'};
  return {calls, comments, notices, summary, requests, state, context, env, github, core, file,
    run:() => publish({github, context, core}, env)};
}

const bot = body => ({id:42, body, user:{login:'github-actions[bot]', type:'Bot'}});

test('same key updates one bot-owned comment and carries source identity', async t => {
  const f = fixture(t);
  await f.run();
  assert.equal(f.calls[0][0], 'create');
  const body = f.calls[0][1].body;
  assert.ok(body.includes('"head":"abc","run":100,"attempt":1'));
  f.comments.push(bot(body));
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
  f.comments.push(bot(f.calls[0][1].body));
  f.env.OBLIGATION_STICKY_KEY = 'integration';
  await f.run(); assert.equal(f.calls[1][0], 'create');
});

for (const change of ['head', 'run', 'attempt']) test(`older ${change} never replaces fresh evidence`, async t => {
  const f = fixture(t); await f.run();
  f.comments.push(bot(f.calls[0][1].body));
  if (change === 'head') f.state.head = 'new-head';
  if (change === 'run') f.env.GITHUB_RUN_ID = '99';
  if (change === 'attempt') f.comments[0].body = f.comments[0].body.replace('"attempt":1', '"attempt":2');
  await f.run(); assert.equal(f.calls.length, 1);
});

test('forks never publish, even if caller requests publication', async t => {
  const f = fixture(t); f.context.payload.pull_request.head.repo.full_name = 'fork/app';
  await f.run(); assert.equal(f.calls.length, 0);
});

test('a fork run says, in its log and summary, who posts its sticky', async t => {
  const f = fixture(t); f.context.payload.pull_request.head.repo.full_name = 'fork/app';
  assert.equal(await f.run(), false);
  for (const text of [f.notices.join(' '), f.summary.join(' ')]) {
    assert.match(text, /workflow_run job using gigaverse-app\/pytest-obligation\/publish/);
  }
  assert.equal(f.requests.length, 0);
});

test('unavailable comment permission preserves summary-only delivery', async t => {
  const f = fixture(t); f.state.forbidden = true;
  await f.run(); assert.ok(f.notices.some(x => x.includes('retained in summary/artifact')));
});

test('broken bot snapshot is repairable', async t => {
  const f = fixture(t); await f.run();
  f.comments.push(bot(f.calls[0][1].body.replace(/snapshot:.*? -->/, 'snapshot:broken -->')));
  await f.run(); assert.equal(f.calls[1][0], 'update');
});

test('fixed graphics publish with comment permission and never touch Git storage', async t => {
  const f = fixture(t);
  const body = '<picture><img src="https://raw.githubusercontent.com/gigaverse-app/pytest-obligation/main/docs/assets/report-glyphs/good-4-light.svg" alt="42 passed"></picture>';
  fs.writeFileSync(f.env.OBLIGATION_MARKDOWN, body);
  f.github.rest.git = new Proxy({}, {get() {assert.fail('report attempted to access Git storage');}});
  await f.run();
  assert.ok(f.calls[0][1].body.startsWith(body));
  assert.ok(f.calls[0][1].body.includes('"head":"abc","run":100,"attempt":1'));
});

// The workflow_run publisher: a fork's run, looked up through the API only.

const HEAD = 'f'.repeat(40);
const artifact = name => ({name, id:123, expired:false, size_in_bytes:1024, digest:`sha256:${'a'.repeat(64)}`});
const artifactIdentity = {artifactId:123, artifactBytes:1024, artifactDigest:`sha256:${'a'.repeat(64)}`, conclusion:'failure'};

function forkRun(f, overrides = {}) {
  f.context.eventName = 'workflow_run';
  f.context.payload = {workflow_run:{id:200, run_attempt:2}};
  f.state.head = HEAD;
  f.state.run = {id:200, run_attempt:3, event:'pull_request', head_sha:HEAD, head_branch:'feature',
    head_repository:{full_name:'fork/app', owner:{login:'fork'}}, conclusion:'failure', pull_requests:[], ...overrides};
  f.state.pulls = [{number:34, head:{sha:HEAD, repo:{full_name:'fork/app'}}, base:{repo:{full_name:'owner/app'}}}];
  f.state.artifacts = [artifact('obligation-python-2')];
}

const resolve = (f, input = {}) => resolveTriggeringRun({github:f.github, context:f.context, core:f.core}, {stickyKey:'python', ...input});

test('a fork PR is found by its head owner and branch, and must point at the run head', async t => {
  const f = fixture(t); forkRun(f);
  assert.deepEqual(await resolve(f), {pullRequest:34, headSha:HEAD, runId:200, runAttempt:2, artifact:'obligation-python-2', ...artifactIdentity});
  const [, query] = f.requests.find(([kind]) => kind === 'pulls');
  assert.deepEqual(query, {owner:'owner', repo:'app', state:'open', head:'fork:feature', per_page:100});
  const [, artifacts] = f.requests.find(([kind]) => kind === 'artifacts');
  assert.deepEqual(artifacts, {owner:'owner', repo:'app', run_id:200, name:'obligation-python-2', per_page:100});
});

for (const [name, mutate] of [
  ['head SHA moved on', f => { f.state.pulls[0].head.sha = 'e'.repeat(40); }],
  ['base is another repository', f => { f.state.pulls[0].base.repo.full_name = 'other/app'; }],
  ['head is another repository', f => { f.state.pulls[0].head.repo.full_name = 'fork/other'; }],
  ['no open pull request', f => { f.state.pulls = []; }],
  ['several matching pull requests', f => { f.state.pulls.push({...f.state.pulls[0], number:35}); }],
]) test(`no sticky when ${name}`, async t => {
  const f = fixture(t); forkRun(f); mutate(f);
  assert.equal(await resolve(f), null);
  assert.ok(f.notices.some(x => x.includes('Nothing to publish')));
  assert.ok(!f.requests.some(([kind]) => kind === 'artifacts'));
});

for (const event of ['push', 'pull_request_target', 'workflow_dispatch']) test(`a ${event} run is skipped before any PR lookup`, async t => {
  const f = fixture(t); forkRun(f, {event});
  assert.equal(await resolve(f), null);
  assert.ok(!f.requests.some(([kind]) => kind === 'pulls'));
});

test('a deleted fork is skipped', async t => {
  const f = fixture(t); forkRun(f, {head_repository:null});
  assert.equal(await resolve(f), null);
});

for (const artifacts of [[], [{name:'obligation-python-2', expired:true}], [{name:'obligation-python-3', expired:false}]]) {
  test(`absent artifact (${JSON.stringify(artifacts)}) is skipped cleanly`, async t => {
    const f = fixture(t); forkRun(f); f.state.artifacts = artifacts;
    assert.equal(await resolve(f), null);
    assert.ok(f.notices.some(x => x.includes('no unexpired obligation-python-2 artifact')));
  });
}

test('the attempt comes from the event, an explicit input, or the run, in that order of authority', async t => {
  const f = fixture(t); forkRun(f);
  assert.equal((await resolve(f)).runAttempt, 2);
  f.state.artifacts = [artifact('obligation-python-1')];
  assert.equal((await resolve(f, {runAttempt:'1'})).runAttempt, 1);
  f.context.payload = {};
  f.state.artifacts = [artifact('obligation-python-3')];
  assert.deepEqual(await resolve(f, {runId:'200'}), {pullRequest:34, headSha:HEAD, runId:200, runAttempt:3, artifact:'obligation-python-3', ...artifactIdentity});
});

test('the conclusion belongs to the requested attempt, not a newer retry', async t => {
  const f = fixture(t); forkRun(f, {conclusion:'success'});
  f.state.attemptConclusion = 'cancelled';
  assert.equal((await resolve(f)).conclusion, 'cancelled');
});

test('ambiguous artifact names never choose an arbitrary upload', async t => {
  const f = fixture(t); forkRun(f);
  f.state.artifacts.push({...artifact('obligation-python-2'), id:456});
  assert.equal(await resolve(f), null);
});

test('without a workflow_run event or run-id there is nothing to resolve', async t => {
  const f = fixture(t); forkRun(f); f.context.payload = {};
  await assert.rejects(resolve(f), /triggering run ID/);
});

const sticky = (f, resolved, key = 'python') => publishSticky({github:f.github, context:f.context, core:f.core},
  {...resolved, stickyKey:key, markdownPath:f.file});

test('the publisher and the report action share one sticky per PR and key', async t => {
  const f = fixture(t);
  f.context.payload.pull_request.head.sha = f.state.head = HEAD;
  await f.run();
  f.comments.push(bot(f.calls[0][1].body));
  const resolved = {pullRequest:12, headSha:HEAD, runId:100, runAttempt:1};
  assert.equal(await sticky(f, resolved), true);
  assert.deepEqual(f.calls.map(([kind]) => kind), ['create', 'update']);
  assert.equal(f.calls[1][1].comment_id, 42);
  assert.equal(await sticky(f, resolved, 'integration'), true);
  assert.equal(f.calls[2][0], 'create');
});

for (const [name, run, attempt, writes] of [
  ['a later attempt of the triggering run replaces it', 200, 3, true],
  ['the same run and attempt republish idempotently', 200, 2, true],
  ['an earlier attempt never replaces it', 200, 1, false],
  ['an older run never replaces it', 199, 9, false],
]) test(`ordering with triggering run ids: ${name}`, async t => {
  const f = fixture(t); forkRun(f);
  assert.equal(await sticky(f, {pullRequest:34, headSha:HEAD, runId:200, runAttempt:2}), true);
  f.comments.push(bot(f.calls[0][1].body));
  assert.ok(f.calls[0][1].body.includes(`"head":"${HEAD}","run":200,"attempt":2`));
  assert.equal(await sticky(f, {pullRequest:34, headSha:HEAD, runId:run, runAttempt:attempt}), writes);
  assert.equal(f.calls.length, writes ? 2 : 1);
});

test('the publisher refuses evidence for a head the PR has moved past', async t => {
  const f = fixture(t); forkRun(f); f.state.head = 'e'.repeat(40);
  assert.equal(await sticky(f, {pullRequest:34, headSha:HEAD, runId:200, runAttempt:2}), false);
  assert.equal(f.calls.length, 0);
});

test('the publisher degrades to a warning without comment permission', async t => {
  const f = fixture(t); forkRun(f); f.state.forbidden = true;
  assert.equal(await sticky(f, {pullRequest:34, headSha:HEAD, runId:200, runAttempt:2}), false);
  assert.ok(f.notices.some(x => x.includes('PR comment unavailable')));
});

test('the publisher keeps the comment budget', async t => {
  const f = fixture(t); forkRun(f);
  fs.writeFileSync(f.file, 'x'.repeat(55001));
  await assert.rejects(sticky(f, {pullRequest:34, headSha:HEAD, runId:200, runAttempt:2}), /comment budget/);
});

for (const bad of [{pullRequest:'34; rm'}, {runId:0}, {runAttempt:'x'}]) test(`malformed identity ${JSON.stringify(bad)} is refused`, async t => {
  const f = fixture(t); forkRun(f);
  await assert.rejects(sticky(f, {pullRequest:34, headSha:HEAD, runId:200, runAttempt:2, ...bad}), /positive/);
  assert.equal(f.calls.length, 0);
});
