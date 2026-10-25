// Only Markdown rendered by this action revision crosses this boundary. Never execute report or PR code.
const fs = require('node:fs');
const crypto = require('node:crypto');

const BUDGET = 55000;
const SNAPSHOT = /<!-- pytest-obligation-snapshot:(.*?) -->/;

function positive(value, what) {
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 1) throw new Error(`A positive ${what} is required for sticky publication.`);
  return number;
}

function markerFor(stickyKey) {
  const key = crypto.createHash('sha256').update(stickyKey || 'obligation').digest('hex').slice(0, 24);
  return `<!-- pytest-obligation:${key} -->`;
}

// The single sticky owner for both entry points: one bot comment per PR and key, never replaced by an
// older run/attempt or by evidence for a head the PR has moved past. Returns whether it wrote.
async function publishSticky({github, context, core}, {pullRequest, headSha, runId, runAttempt, stickyKey, markdownPath}) {
  const number = positive(pullRequest, 'pull request number');
  const marker = markerFor(stickyKey);
  const snapshot = {head: headSha, run: positive(runId, 'source run ID'), attempt: positive(runAttempt, 'source run attempt')};
  const body = fs.readFileSync(markdownPath, 'utf8');
  if (body.length > BUDGET) throw new Error('Rendered report exceeds the comment budget.');
  const metadata = `<!-- pytest-obligation-snapshot:${JSON.stringify(snapshot)} -->`;
  try {
    const {data: current} = await github.rest.pulls.get({...context.repo, pull_number: number});
    if (current.head.sha !== snapshot.head) {
      core.info('PR head changed; old evidence retained as an artifact without replacing the sticky.');
      return false;
    }
    const comments = await github.paginate(github.rest.issues.listComments, {...context.repo, issue_number: number, per_page: 100});
    const existing = comments.find(c => c.user?.login === 'github-actions[bot]' && c.user?.type === 'Bot' && (c.body || '').includes(marker));
    if (existing) {
      const match = existing.body.match(SNAPSHOT);
      if (match) {
        let previous;
        try { previous = JSON.parse(match[1]); } catch { /* Repair malformed bot-owned metadata. */ }
        if (previous && (previous.run > snapshot.run || (previous.run === snapshot.run && previous.attempt > snapshot.attempt))) {
          core.info('A newer run/attempt already owns this sticky.');
          return false;
        }
      }
    }
    // Recheck after pagination. Callers serialize the publishing step per PR/key
    // with workflow concurrency; GitHub's comment API has no compare-and-swap.
    const {data: latest} = await github.rest.pulls.get({...context.repo, pull_number: number});
    if (latest.head.sha !== snapshot.head) return false;
    const payload = {...context.repo, body: `${body}\n\n${metadata}\n${marker}`};
    if (existing) await github.rest.issues.updateComment({...payload, comment_id: existing.id});
    else await github.rest.issues.createComment({...payload, issue_number: number});
    return true;
  } catch (error) {
    if ([403, 404].includes(error.status)) {
      core.warning('PR comment unavailable with this token; report retained in summary/artifact.');
      return false;
    }
    throw error;
  }
}

const FORK_NOTE = 'Fork pull request: this run\'s token cannot comment, so it keeps the job summary and the '
  + 'evidence artifact. A trusted workflow_run job using gigaverse-app/pytest-obligation/publish posts the '
  + 'sticky when the repository configures one.';

// The report action's entry point: the pull_request run publishes its own evidence when it may.
async function publish({github, context, core}, env = process.env) {
  const pr = context.payload.pull_request;
  if (context.eventName !== 'pull_request' || !pr) {
    core.info('No pull request; report retained in summary/artifact.');
    return false;
  }
  if (pr.head.repo?.full_name !== `${context.repo.owner}/${context.repo.repo}`) {
    core.notice(FORK_NOTE);
    if (core.summary) await core.summary.addRaw(`\n> [!NOTE]\n> ${FORK_NOTE}\n`).write();
    return false;
  }
  return publishSticky({github, context, core}, {
    pullRequest: pr.number,
    headSha: pr.head.sha,
    runId: env.GITHUB_RUN_ID,
    runAttempt: env.GITHUB_RUN_ATTEMPT,
    stickyKey: env.OBLIGATION_STICKY_KEY,
    markdownPath: env.OBLIGATION_MARKDOWN,
  });
}

// The publish action's first step: which run, PR and artifact, all from the API. Nothing here comes
// from the artifact, and the PR is accepted only when it still points at the run's head commit.
async function resolveTriggeringRun({github, context, core}, {runId, runAttempt, stickyKey}) {
  const repository = `${context.repo.owner}/${context.repo.repo}`;
  const event = context.payload.workflow_run;
  const id = positive(runId || event?.id, 'triggering run ID (run publish on workflow_run, or pass run-id)');
  const {data: run} = await github.rest.actions.getWorkflowRun({...context.repo, run_id: id});
  // A workflow_run event names the attempt that completed; a re-run may already be newer.
  const attempt = positive(runAttempt || (event?.id === id ? event.run_attempt : run.run_attempt), 'triggering run attempt');
  const skip = reason => { core.info(`${reason} Nothing to publish.`); return null; };
  if (run.event !== 'pull_request') return skip(`Run ${id} was triggered by ${run.event}, not pull_request.`);
  if (attempt > run.run_attempt) return skip(`Run ${id} has no attempt ${attempt}.`);
  // A re-run can finish while this publisher waits. Its conclusion cannot describe the older artifact.
  const sourceRun = attempt === run.run_attempt ? run : (await github.rest.actions.getWorkflowRunAttempt({
    ...context.repo, run_id:id, attempt_number:attempt,
  })).data;
  const head = run.head_repository;
  if (!head?.owner?.login || !run.head_branch) return skip(`Run ${id} has no head repository or branch.`);
  const candidates = await github.paginate(github.rest.pulls.list, {
    ...context.repo, state: 'open', head: `${head.owner.login}:${run.head_branch}`, per_page: 100,
  });
  const matches = candidates.filter(pr => pr.head?.sha === run.head_sha
    && pr.head?.repo?.full_name === head.full_name && pr.base?.repo?.full_name === repository);
  if (matches.length !== 1) {
    return skip(`${matches.length ? 'Several' : 'No'} open pull requests in ${repository} have head ${run.head_sha} from ${head.full_name}.`);
  }
  const name = `obligation-${stickyKey || 'obligation'}-${attempt}`;
  const artifacts = await github.paginate(github.rest.actions.listWorkflowRunArtifacts, {...context.repo, run_id: id, name, per_page: 100});
  const matchingArtifacts = artifacts.filter(artifact => artifact.name === name && !artifact.expired);
  if (matchingArtifacts.length !== 1) {
    return skip(`Run ${id} attempt ${attempt} has no unexpired ${name} artifact.`);
  }
  const artifact = matchingArtifacts[0];
  return {pullRequest: matches[0].number, headSha: run.head_sha, runId: id, runAttempt: attempt, artifact: name,
    artifactId:positive(artifact.id, 'artifact ID'), artifactBytes:artifact.size_in_bytes, artifactDigest:artifact.digest,
    conclusion:sourceRun.conclusion || sourceRun.status};
}

module.exports = publish;
module.exports.publish = publish;
module.exports.publishSticky = publishSticky;
module.exports.resolveTriggeringRun = resolveTriggeringRun;
module.exports.markerFor = markerFor;
