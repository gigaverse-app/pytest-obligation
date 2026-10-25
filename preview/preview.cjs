// This trusted host process handles GitHub credentials. Only the existing offline renderer opens evidence.
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {parseArgs} = require('node:util');
const {downloadArchive, renderSandbox, MAX_ARCHIVE_BYTES, UNAVAILABLE, CONCLUSIONS} = require('../publish/publish.cjs');

const API = 'https://api.github.com';
const ACTION_PATH = path.resolve(__dirname, '../publish');
const ASSET_REF = '6936ca68ce5252e4387e8f14de8bdb076b6b4777';
const TRAILER = /\n<!-- pytest-obligation-preview-snapshot:(.*?) -->\n(<!-- pytest-obligation-preview:[0-9a-f]{24} -->)\s*$/;
const BUDGET = 55000;
class PreviewError extends Error {}
function requireThat(condition, message) { if (!condition) throw new PreviewError(message); }
function positive(value) { return Number.isSafeInteger(Number(value)) && Number(value) > 0; }
function sameRepo(a, b) { return typeof a === 'string' && typeof b === 'string' && a.toLowerCase() === b.toLowerCase(); }

function parseOptions(argv) {
  let values;
  try {
    ({values} = parseArgs({args:argv, options:{pr:{type:'string'}, run:{type:'string'},
      'sticky-key':{type:'string', default:'obligation'}, help:{type:'boolean', short:'h'}}, strict:true}));
  } catch { throw new PreviewError('Use --pr URL --run URL [--sticky-key KEY]. Tokens are never command-line arguments.'); }
  if (values.help) return {help:true};
  const pr = /^https:\/\/github\.com\/([\w.-]+\/[\w.-]+)\/pull\/([1-9]\d*)\/?$/.exec(values.pr || '');
  const run = /^https:\/\/github\.com\/([\w.-]+\/[\w.-]+)\/actions\/runs\/([1-9]\d*)(?:\/attempts\/([1-9]\d*))?\/?$/.exec(values.run || '');
  requireThat(pr && run && positive(pr[2]) && positive(run[2]) && (!run[3] || positive(run[3])),
    'Supply a github.com PR URL and a fork workflow run URL, without query strings or fragments.');
  requireThat(/^[A-Za-z0-9_-]{1,80}$/.test(values['sticky-key']), 'The sticky key must be 1–80 letters, digits, underscores or hyphens.');
  return {pr:values.pr, run:values.run, stickyKey:values['sticky-key'], repository:pr[1], number:Number(pr[2]),
    sourceRepository:run[1], runId:Number(run[2]), attempt:run[3] ? Number(run[3]) : undefined};
}

function safeMessage(error) {
  return error instanceof PreviewError ? error.message
    : 'Preview could not finish. Check GitHub connectivity, gh authentication and Docker, then retry. No raw subprocess or artifact output is printed.';
}

function githubApi(token, fetcher) {
  async function request(endpoint, method = 'GET', body) {
    // Every authenticated request is built here, on a fixed origin. Redirects and API-supplied URLs are never followed.
    const response = await fetcher(`${API}${endpoint}`, {method, redirect:'error', signal:AbortSignal.timeout(30_000),
      headers:{authorization:`Bearer ${token}`, accept:'application/vnd.github+json',
        'content-type':'application/json', 'x-github-api-version':'2022-11-28'},
      ...(body ? {body:JSON.stringify(body)} : {})});
    if (!response.ok) {
      await response.body?.cancel();
      throw new PreviewError(`GitHub request failed (HTTP ${response.status}). Check the URLs and your account's access; no changes are retried automatically.`);
    }
    const chunks = []; let size = 0;
    for await (const chunk of response.body) {
      size += chunk.length;
      requireThat(size <= 8 * 1024 * 1024, 'GitHub response exceeds the preview safety limit.');
      chunks.push(chunk);
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  }
  async function list(endpoint, field) {
    const result = [];
    for (let page = 1; page <= 10; page++) {
      const data = await request(`${endpoint}${endpoint.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
      const items = field ? data[field] : data;
      requireThat(Array.isArray(items), 'GitHub returned an invalid list.');
      result.push(...items);
      if (items.length < 100) return result;
    }
    throw new PreviewError('More than 1,000 GitHub entries need inspection. No comment was changed.');
  }
  return {request, list};
}

function validatePr(pr, input, viewer) {
  requireThat(pr.state === 'open', 'The target PR is closed. No preview was posted.');
  requireThat(pr.user?.id === viewer.id, 'Use the GitHub account that opened this adoption PR.');
  requireThat(pr.base?.repo?.private === false && pr.head?.repo?.private === false, 'Preview supports public repositories only.');
  requireThat(sameRepo(pr.base.repo.full_name, input.repository) && sameRepo(pr.head.repo.full_name, input.sourceRepository)
    && pr.base.repo.id !== pr.head.repo.id, 'The run must be in this PR\'s fork, and the PR must target the specified repository.');
  requireThat(/^[a-f0-9]{40}$/i.test(pr.head.sha), 'GitHub returned an invalid head commit.');
}

async function resolve(api, input) {
  const viewer = await api.request('/user');
  requireThat(positive(viewer.id) && viewer.type === 'User', 'Sign in with your GitHub user account using gh auth login.');
  const pr = await api.request(`/repos/${input.repository}/pulls/${input.number}`);
  validatePr(pr, input, viewer);
  const endpoint = `/repos/${input.sourceRepository}/actions/runs/${input.runId}`;
  const latest = await api.request(endpoint);
  const attempt = input.attempt || latest.run_attempt;
  requireThat(positive(attempt) && attempt <= latest.run_attempt, 'That run attempt does not exist.');
  const run = attempt === latest.run_attempt ? latest : await api.request(`${endpoint}/attempts/${attempt}`);
  // A fork push/dispatch tests this exact commit. A PR merge run has a different execution revision and is not interchangeable.
  requireThat(run.id === input.runId && run.run_attempt === attempt && run.status === 'completed'
    && ['push', 'workflow_dispatch'].includes(run.event), 'Choose a completed push or workflow_dispatch run in the fork.');
  requireThat(run.repository?.id === pr.head.repo.id && run.head_repository?.id === pr.head.repo.id
    && sameRepo(run.repository.full_name, input.sourceRepository) && sameRepo(run.head_repository.full_name, input.sourceRepository)
    && run.head_sha === pr.head.sha && run.head_branch === pr.head.ref, 'The fork run does not match the PR\'s current branch and commit.');
  const name = `obligation-${input.stickyKey}-${attempt}`;
  const artifacts = (await api.list(`${endpoint}/artifacts?name=${encodeURIComponent(name)}`, 'artifacts'))
    .filter(a => a.name === name && !a.expired);
  requireThat(artifacts.length === 1 && positive(artifacts[0].id), 'Expected one unexpired evidence artifact for this run attempt and sticky key.');
  return {viewer, headSha:pr.head.sha, sourceId:pr.head.repo.id, runId:run.id, runAttempt:attempt,
    conclusion:CONCLUSIONS.has(run.conclusion) ? run.conclusion : 'unknown', artifact:artifacts[0]};
}

function bodyFor(markdown, input, resolved) {
  const source = `https://github.com/${input.sourceRepository}`;
  const prefix = '**Preview from the PR contributor**\n\n'
    + 'No installation, repository access or credentials were requested from the target project. '
    + 'This is a report from the contributor\'s fork; viewing it runs no project code.\n\n'
    + `**Fork workflow: ${resolved.conclusion}** · [run ${resolved.runId}, attempt ${resolved.runAttempt}](${source}/actions/runs/${resolved.runId}/attempts/${resolved.runAttempt})\n\n`
    + `Commit: [\`${resolved.headSha}\`](${source}/commit/${resolved.headSha}). Results below are contributor-reported evidence, not the target project's CI or approval.\n\n`;
  return prefix + (prefix.length + markdown.length <= BUDGET ? markdown : UNAVAILABLE);
}

async function preview(options, {token, fetcher = fetch, render = renderSandbox}) {
  const input = parseOptions(['--pr', options.pr, '--run', options.run, '--sticky-key', options.stickyKey || 'obligation']);
  const api = githubApi(token, fetcher);
  const resolved = await resolve(api, input);
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'obligation-preview-'));
  const archive = path.join(directory, 'evidence.zip');
  let markdown = UNAVAILABLE;
  try {
    requireThat(Number.isSafeInteger(resolved.artifact.size_in_bytes) && resolved.artifact.size_in_bytes <= MAX_ARCHIVE_BYTES,
      'Artifact exceeds the download limit.');
    await downloadArchive({apiUrl:API, repository:input.sourceRepository, artifactId:resolved.artifact.id,
      token, digest:resolved.artifact.digest, destination:archive, fetcher});
    markdown = await render(ACTION_PATH, archive, resolved, `https://github.com/${input.sourceRepository}`, ASSET_REF);
  } catch {
    // Preserve a useful unavailable preview. No artifact text, signed URL or subprocess error may reach the terminal.
    markdown = UNAVAILABLE;
  } finally {
    await fs.rm(directory, {recursive:true, force:true});
  }
  const marker = `<!-- pytest-obligation-preview:${crypto.createHash('sha256').update(input.stickyKey).digest('hex').slice(0,24)} -->`;
  const snapshot = {head:resolved.headSha, repository:resolved.sourceId, run:resolved.runId, attempt:resolved.runAttempt};
  const comments = await api.list(`/repos/${input.repository}/issues/${input.number}/comments`);
  // An exact final trailer AND the authenticated numeric author ID are required; copied markers cannot select someone else's comment.
  const existing = comments.filter(c => c.user?.id === resolved.viewer.id && c.user?.type === 'User'
    && (c.body || '').match(TRAILER)?.[2] === marker).sort((a,b) => b.id - a.id)[0];
  const urlFor = id => `https://github.com/${input.repository}/pull/${input.number}#issuecomment-${id}`;
  if (existing) {
    let previous;
    try { previous = JSON.parse(existing.body.match(TRAILER)[1]); } catch { /* Repair our own malformed metadata. */ }
    if (previous?.repository === snapshot.repository && (previous.run > snapshot.run
      || (previous.run === snapshot.run && previous.attempt > snapshot.attempt))) {
      return {status:'newer-preview-exists', url:urlFor(existing.id)};
    }
  }
  const current = await api.request(`/repos/${input.repository}/pulls/${input.number}`);
  validatePr(current, input, resolved.viewer);
  requireThat(current.head.sha === resolved.headSha && current.head.repo.id === resolved.sourceId,
    'The PR changed while rendering. Run preview again with evidence for the new head.');
  // GitHub has no compare-and-swap for comments. Keep invocations for one PR/key sequential; recheck the head immediately before writing.
  const body = `${bodyFor(markdown, input, resolved)}\n\n<!-- pytest-obligation-preview-snapshot:${JSON.stringify(snapshot)} -->\n${marker}`;
  const comment = await api.request(existing ? `/repos/${input.repository}/issues/comments/${existing.id}`
    : `/repos/${input.repository}/issues/${input.number}/comments`, existing ? 'PATCH' : 'POST', {body});
  requireThat(positive(comment.id), 'GitHub did not return the comment identity. Inspect the PR before retrying.');
  return {status:existing ? 'updated' : 'created', url:urlFor(comment.id)};
}

module.exports = {preview, parseOptions, safeMessage, PreviewError};
