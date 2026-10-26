// The credential-bearing process uses GitHub metadata, bounded bytes and captured Markdown.
// ZIP/XML/JSON parsing happens without credentials, network or a writable host mount.
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {resolveTriggeringRun, publishSticky} = require('../report/publish.cjs');

const execute = promisify(execFile);
const MAX_ARCHIVE_BYTES = 32 * 1024 * 1024;
const UNAVAILABLE = '**🟠 Evidence unavailable.** The evidence could not be processed within the publisher’s safety limits. See the original workflow artifacts and logs.';
const CONCLUSIONS = new Set(['success', 'failure', 'neutral', 'cancelled', 'skipped', 'timed_out', 'action_required', 'stale', 'startup_failure', 'in_progress', 'queued', 'requested', 'waiting', 'pending']);
// Statuses of a run that has not finished: its sticky is updated again when it does.
const RUNNING = new Set(['in_progress', 'queued', 'requested', 'waiting', 'pending']);

function dockerEnvironment(env = process.env) {
  // Docker needs the user's daemon configuration, not their GitHub/cloud credentials or interpreter hooks.
  const allowed = new Set(['PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP',
    'APPDATA', 'LOCALAPPDATA', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG', 'DOCKER_CERT_PATH', 'DOCKER_TLS_VERIFY']);
  return Object.fromEntries(Object.entries(env).filter(([key]) => allowed.has(key.toUpperCase())));
}

async function downloadArchive({apiUrl, repository, artifactId, token, digest, destination, maxBytes = MAX_ARCHIVE_BYTES, fetcher = fetch}) {
  if (!/^sha256:[a-f0-9]{64}$/.test(digest || '')) throw new Error('Artifact digest is missing or invalid.');
  const signal = AbortSignal.timeout(60_000);
  let file;
  try {
    const response = await fetcher(`${apiUrl}/repos/${repository}/actions/artifacts/${artifactId}/zip`, {
      headers: {authorization: `Bearer ${token}`, accept: 'application/vnd.github+json', 'x-github-api-version': '2022-11-28'},
      redirect: 'manual', signal,
    });
    const location = response.headers.get('location');
    if (response.status !== 302 || !location || new URL(location).protocol !== 'https:') {
      await response.body?.cancel();
      throw new Error('Artifact download is unavailable.');
    }
    await response.body?.cancel();
    // The signed storage URL needs no GitHub token. Never forward credentials on a redirect.
    const archive = await fetcher(location, {redirect: 'error', signal});
    if (!archive.ok || !archive.body || Number(archive.headers.get('content-length')) > maxBytes) {
      await archive.body?.cancel();
      throw new Error('Artifact download is unavailable or exceeds the byte limit.');
    }
    file = await fs.open(destination, 'wx', 0o644);
    const hash = crypto.createHash('sha256');
    let size = 0;
    for await (const chunk of archive.body) {
      size += chunk.length;
      if (size > maxBytes) throw new Error('Artifact exceeds the download byte limit.');
      hash.update(chunk);
      await file.writeFile(chunk);
    }
    if (`sha256:${hash.digest('hex')}` !== digest) throw new Error('Artifact digest mismatch.');
  } catch (error) {
    await file?.close();
    file = undefined;
    await fs.rm(destination, {force: true});
    throw error;
  } finally {
    await file?.close();
  }
}

function containerArgs(image, archive, name) {
  // Isolation boundary: no token/env, socket, checkout or writable host directory.
  return ['run', '--rm', '--name', name, '--network=none', '--read-only', '--cap-drop=ALL',
    '--security-opt=no-new-privileges', '--user=65534:65534', '--memory=512m', '--memory-swap=512m',
    '--cpus=1', '--pids-limit=32', '--ipc=none', '--log-driver=none',
    '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=96m,mode=1777',
    '--mount', `type=bind,src=${archive},dst=/input/evidence.zip,readonly`, image];
}

async function buildImage(actionPath) {
  const {stdout} = await execute('docker', ['build', '--quiet', '--file', path.join(actionPath, 'Dockerfile'), path.dirname(actionPath)],
    {timeout: 300_000, maxBuffer: 2 * 1024 * 1024, env:dockerEnvironment(), cwd:path.dirname(actionPath)});
  const image = stdout.trim();
  if (!/^sha256:[a-f0-9]{64}$/.test(image)) throw new Error('Renderer image was not built.');
  return image;
}

function rendererArgs(resolved, repositoryUrl, assetRef) {
  return ['--head-sha', resolved.headSha, '--run-id', String(resolved.runId), '--run-attempt', String(resolved.runAttempt),
    '--repository-url', repositoryUrl, '--asset-ref', assetRef,
    // A run still going has recorded what it recorded so far; no zero is final yet.
    ...(RUNNING.has(resolved.conclusion) ? ['--workflow-running'] : []),
    // Only a PR from a branch of this repository keeps its contract's mentions, references and links live.
    ...(resolved.sameRepository === true ? ['--own-text'] : [])];
}

async function renderSandbox(actionPath, archive, resolved, repositoryUrl, assetRef) {
  const image = await buildImage(actionPath);
  const name = `obligation-${crypto.randomUUID()}`;
  try {
    const {stdout} = await execute('docker', [...containerArgs(image, archive, name),
      ...rendererArgs(resolved, repositoryUrl, assetRef)],
    {timeout: 120_000, maxBuffer: 256 * 1024, encoding: 'utf8', env:dockerEnvironment(), cwd:actionPath});
    // Captured output never reaches the Actions command parser and is never interpreted as code.
    return stdout;
  } finally {
    // A timed-out Docker client leaves its container alive. Remove it explicitly, including on failure.
    await execute('docker', ['rm', '--force', name], {timeout: 15_000, maxBuffer: 16_384, env:dockerEnvironment(), cwd:actionPath}).catch(() => {});
  }
}

function workflowStatus(resolved, label = 'GitHub workflow') {
  const conclusion = CONCLUSIONS.has(resolved.conclusion) ? resolved.conclusion : 'unknown';
  if (conclusion === 'success') return '';
  if (RUNNING.has(conclusion)) {
    return `## ⏳ ${label} still running\n\n`
      + '> [!WARNING]\n'
      + `> **GitHub reports: ${conclusion}.**\n>\n`
      + '> These are the contract counts recorded so far; a count shown as ? is not known until the run finishes.\n\n';
  }
  const failed = ['failure', 'timed_out', 'startup_failure'].includes(conclusion);
  // API status is always the first visual verdict. Contributor evidence cannot replace this warning.
  return `## ${failed ? '🔴' : '🟠'} ${label} ${failed ? 'failed' : 'did not succeed'}\n\n`
    + `> [!${failed ? 'CAUTION' : 'WARNING'}]\n`
    + `> **GitHub reports: ${conclusion}.**\n>\n`
    + '> Contract counts below cover only obligation checks. Other tests or workflow steps can fail even with zero contract failures. '
    + 'Contributor-reported success does not override this workflow status.\n\n';
}

function publishedBody(markdown, resolved, repositoryUrl, {label = 'GitHub workflow', intro = ''} = {}) {
  const prefix = workflowStatus(resolved, label) + intro;
  const runLabel = resolved.runAttempt > 1 ? `run ${resolved.runAttempt}` : 'run';
  const footer = `\n\n[${runLabel}](${repositoryUrl}/actions/runs/${resolved.runId}/attempts/${resolved.runAttempt})`;
  const body = prefix + markdown + footer;
  return body.length <= 55_000 ? body : prefix + UNAVAILABLE + footer;
}

async function run({github, context, core}, env = process.env) {
  const resolved = await resolveTriggeringRun({github, context, core}, {
    runId: env.OBLIGATION_RUN_ID, runAttempt: env.OBLIGATION_RUN_ATTEMPT, stickyKey: env.OBLIGATION_STICKY_KEY,
  });
  if (!resolved) return;
  core.setOutput('pull-request', String(resolved.pullRequest));
  const directory = await fs.mkdtemp(path.join(env.RUNNER_TEMP, 'obligation-publish-'));
  const archive = path.join(directory, 'evidence.zip');
  const repository = `${context.repo.owner}/${context.repo.repo}`;
  const repositoryUrl = `${env.GITHUB_SERVER_URL}/${repository}`;
  let markdown = UNAVAILABLE;
  try {
    if (resolved.artifactBytes > MAX_ARCHIVE_BYTES) throw new Error('Artifact exceeds the byte limit.');
    await downloadArchive({apiUrl: env.GITHUB_API_URL, repository, artifactId: resolved.artifactId,
      token: env.OBLIGATION_TOKEN, digest: resolved.artifactDigest, destination: archive});
    markdown = await renderSandbox(env.OBLIGATION_ACTION_PATH, archive, resolved, repositoryUrl, env.OBLIGATION_ASSET_REF);
  } catch {
    // Keep a useful neutral comment. Never print artifact content, signed URLs or subprocess errors.
    core.warning('Evidence unavailable: download or isolated rendering did not complete within the safety limits.');
  } finally {
    await fs.rm(archive, {force: true});
  }
  const markdownPath = path.join(directory, 'report.md');
  await fs.writeFile(markdownPath, publishedBody(markdown, resolved, repositoryUrl), 'utf8');
  await core.summary.addRaw(await fs.readFile(markdownPath, 'utf8')).write();
  core.setOutput('markdown-path', markdownPath);
  core.setOutput('published', String(await publishSticky({github, context, core}, {
    ...resolved, stickyKey: env.OBLIGATION_STICKY_KEY, markdownPath,
  })));
}

module.exports = {run, downloadArchive, publishedBody, buildImage, containerArgs, rendererArgs, renderSandbox,
  dockerEnvironment, MAX_ARCHIVE_BYTES, UNAVAILABLE, CONCLUSIONS, RUNNING, workflowStatus};
