const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {downloadArchive, publishedBody, rendererArgs} = require('./publish.cjs');

const bytes = Buffer.from('a bounded artifact');
const digest = `sha256:${crypto.createHash('sha256').update(bytes).digest('hex')}`;

async function fixture(t, response) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'obligation-download-'));
  t.after(() => fs.rm(directory, {recursive: true, force: true}));
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({url, options});
    return calls.length === 1
      ? new Response(null, {status: 302, headers: {location: 'https://storage.example/archive'}})
      : response;
  };
  const destination = path.join(directory, 'evidence.zip');
  return {calls, destination, download: overrides => downloadArchive({
    apiUrl: 'https://api.github.com', repository: 'owner/project', artifactId: 123,
    token: 'test-token', digest, destination, fetcher, ...overrides,
  })};
}

test('download checks the digest and never sends the GitHub token to artifact storage', async t => {
  const f = await fixture(t, new Response(bytes));
  await f.download();
  assert.deepEqual(await fs.readFile(f.destination), bytes);
  assert.equal(f.calls[0].options.headers.authorization, 'Bearer test-token');
  assert.equal(f.calls[1].options.headers?.authorization, undefined);
  assert.equal(f.calls[1].options.redirect, 'error');
});

for (const advertised of [undefined, '1', '1000']) test(`stream budget holds with Content-Length ${advertised}`, async t => {
  const headers = advertised ? {'content-length': advertised} : {};
  const f = await fixture(t, new Response(bytes, {headers}));
  await assert.rejects(f.download({maxBytes: 4}), /limit/);
  await assert.rejects(fs.stat(f.destination), {code: 'ENOENT'});
});

test('a changed archive is discarded', async t => {
  const f = await fixture(t, new Response('changed'));
  await assert.rejects(f.download(), /digest/);
  await assert.rejects(fs.stat(f.destination), {code: 'ENOENT'});
});

test('workflow failure from the API stays visible above producer success claims', () => {
  const body = publishedBody('Test step (reported): **success**', {conclusion: 'failure', runId: 7, runAttempt: 2}, 'https://github.com/owner/project');
  assert.ok(body.startsWith('> [!CAUTION]\n> **GitHub reports: failure.**'));
  assert.doesNotMatch(body, /^## /m, 'the alert states the status; no heading repeats it');
  assert.match(body, /Other tests or workflow steps can fail/);
  assert.match(body, /attempts\/2/);
});

test('oversized renderer output recovers to an unavailable report with API status', () => {
  const body = publishedBody('x'.repeat(55001), {conclusion: 'success', runId: 7, runAttempt: 1}, 'https://github.com/owner/project');
  assert.ok(body.length < 55000);
  assert.match(body, /Evidence unavailable/);
  assert.match(body, /\[run\]\(https:\/\/github.com\/owner\/project\/actions\/runs\/7\/attempts\/1\)$/);
});

for (const attempt of [1, 2, 3]) test(`successful attempt ${attempt} has only a concise footer link`, () => {
  const body = publishedBody('The report', {conclusion:'success', runId:7, runAttempt:attempt}, 'https://github.com/owner/project');
  const label = attempt === 1 ? 'run' : `run ${attempt}`;
  assert.equal(body, `The report\n\n[${label}](https://github.com/owner/project/actions/runs/7/attempts/${attempt})`);
});

for (const conclusion of ['in_progress', 'queued', 'requested', 'waiting', 'pending']) {
  test(`${conclusion} reads as still running, not as a failed run`, () => {
    const body = publishedBody('The report', {conclusion, runId:7, runAttempt:1}, 'https://github.com/owner/project');
    assert.ok(body.startsWith('> [!WARNING]\n'), 'only the warning, no heading repeating it');
    assert.match(body, new RegExp(`GitHub reports: ${conclusion}`));
    assert.match(body, /recorded so far/);
    assert.doesNotMatch(body, /^## /m);
    assert.doesNotMatch(body, /did not succeed/);
  });
  test(`${conclusion} tells the renderer no zero is final yet`, () => {
    const args = rendererArgs({headSha:'f'.repeat(40), runId:7, runAttempt:1, conclusion}, 'https://github.com/owner/app', 'v1');
    assert.ok(args.includes('--workflow-running'));
  });
}

test('a finished run does not ask the renderer to hide its zeros', () => {
  for (const conclusion of ['success', 'failure', 'cancelled']) {
    const args = rendererArgs({headSha:'f'.repeat(40), runId:7, runAttempt:1, conclusion}, 'https://github.com/owner/app', 'v1');
    assert.ok(!args.includes('--workflow-running'), conclusion);
  }
});

for (const conclusion of ['timed_out', 'startup_failure', 'cancelled', 'neutral', 'skipped', 'unknown']) {
  test(`${conclusion} cannot be presented as a successful workflow`, () => {
    const body = publishedBody('Test step (reported): **success**', {conclusion, runId:7, runAttempt:1}, 'https://github.com/owner/project');
    const failed = ['timed_out', 'startup_failure'].includes(conclusion);
    assert.ok(body.startsWith(`> [!${failed ? 'CAUTION' : 'WARNING'}]\n> **GitHub reports: ${conclusion}.**`));
    assert.doesNotMatch(body, /^## /m);
  });
}

test('a titled report keeps its title first, with the workflow status right below it', () => {
  const report = '### Celery main\n\n> [!CAUTION]\n> **The test step failed.**\n\nThe counts';
  const body = publishedBody(report, {conclusion:'failure', runId:7, runAttempt:1}, 'https://github.com/owner/project');
  const lines = body.split('\n');
  assert.equal(lines[0], '### Celery main');
  assert.deepEqual(lines.slice(2, 4), ['> [!CAUTION]', '> **GitHub reports: failure.**']);
  assert.ok(body.indexOf('GitHub reports: failure') < body.indexOf('The test step failed'));
});

test('a failed workflow over a failed test step states the caveat once, in the report box', () => {
  for (const report of ['> [!CAUTION]\n> **The test step failed.**\n>\n> Contract counts cover only obligation checks.\n\nThe counts',
    '### Celery main\n\n> [!CAUTION]\n> **The test step failed.**\n>\n> Contract counts cover only obligation checks.\n\nThe counts']) {
    const body = publishedBody(report, {conclusion:'failure', runId:7, runAttempt:1}, 'https://github.com/owner/project');
    assert.match(body, /> \*\*GitHub reports: failure\.\*\*\n\n> \[!CAUTION\]\n> \*\*The test step failed\.\*\*/);
    assert.equal(body.match(/cover only obligation checks/g).length, 1);
  }
  // A report that claims success, or mentions the box anywhere but its top, keeps the full workflow caveat.
  for (const report of ['Test step (reported): **success**', 'The counts\n\n> [!CAUTION]\n> **The test step failed.**\n']) {
    const body = publishedBody(report, {conclusion:'failure', runId:7, runAttempt:1}, 'https://github.com/owner/project');
    assert.match(body, /Contributor-reported success does not override/);
  }
});

test('a report without a title gets the workflow status first', () => {
  const body = publishedBody('The counts', {conclusion:'in_progress', runId:7, runAttempt:1}, 'https://github.com/owner/project');
  assert.ok(body.startsWith('> [!WARNING]\n> **GitHub reports: in_progress.**'));
  assert.match(body, /\n\nThe counts\n\n\[run\]/);
});

test('only a PR from a branch of this repository renders its contract text live', () => {
  const resolved = {headSha:'f'.repeat(40), runId:200, runAttempt:2};
  const argsFor = sameRepository => rendererArgs({...resolved, sameRepository}, 'https://github.com/owner/app', 'v1');
  assert.ok(argsFor(true).includes('--own-text'));
  for (const fork of [false, undefined, 'true']) assert.ok(!argsFor(fork).includes('--own-text'), `${fork} must stay inert`);
});
