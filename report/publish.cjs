// Only rendered Markdown crosses this boundary. Never execute report or PR code.
const fs = require('node:fs');
const crypto = require('node:crypto');
const publishGraphics = require('./graphics.cjs');

module.exports = async function publish({github, context, core}, env = process.env) {
  const pr = context.payload.pull_request;
  if (context.eventName !== 'pull_request' || !pr || pr.head.repo.full_name !== `${context.repo.owner}/${context.repo.repo}`) {
    core.info('No same-repository pull request; report retained in summary/artifact.');
    return;
  }
  const key = crypto.createHash('sha256').update(env.OBLIGATION_STICKY_KEY || 'obligation').digest('hex').slice(0, 24);
  const marker = `<!-- pytest-obligation:${key} -->`;
  const snapshot = {head: pr.head.sha, run: Number(env.GITHUB_RUN_ID), attempt: Number(env.GITHUB_RUN_ATTEMPT)};
  if (!Number.isSafeInteger(snapshot.run) || !Number.isSafeInteger(snapshot.attempt) || snapshot.run < 1 || snapshot.attempt < 1) {
    throw new Error('A source run ID and attempt are required for sticky publication.');
  }
  let body = fs.readFileSync(env.OBLIGATION_MARKDOWN, 'utf8');
  if (body.length > 55000) throw new Error('Rendered report exceeds the comment budget.');
  const metadata = `<!-- pytest-obligation-snapshot:${JSON.stringify(snapshot)} -->`;
  try {
    const {data: current} = await github.rest.pulls.get({...context.repo, pull_number: pr.number});
    if (current.head.sha !== snapshot.head) {
      core.info('PR head changed; old evidence retained as an artifact without replacing the sticky.');
      return;
    }
    const comments = await github.paginate(github.rest.issues.listComments, {...context.repo, issue_number: pr.number, per_page: 100});
    const existing = comments.find(c => c.user?.login === 'github-actions[bot]' && c.user?.type === 'Bot' && (c.body || '').includes(marker));
    if (existing) {
      const match = existing.body.match(/<!-- pytest-obligation-snapshot:(.*?) -->/);
      if (match) {
        let previous;
        try { previous = JSON.parse(match[1]); } catch { /* Repair malformed bot-owned metadata. */ }
        if (previous && (previous.run > snapshot.run || (previous.run === snapshot.run && previous.attempt > snapshot.attempt))) {
          core.info('A newer run/attempt already owns this sticky.');
          return;
        }
      }
    }
    if (env.OBLIGATION_GRAPHICS && env.OBLIGATION_USE_GRAPHICS === 'true') {
      try {
        if (fs.statSync(env.OBLIGATION_GRAPHICS).size > 2_000_000) throw new Error('Graphics bundle too large.');
        const bundle = JSON.parse(fs.readFileSync(env.OBLIGATION_GRAPHICS, 'utf8'));
        if (Object.keys(bundle.assets || {}).length) {
          body = await publishGraphics({github,context,bundle,prefix:`pr-${pr.number}/${key}/`});
        }
      } catch (error) {
        core.warning('Graphics unavailable; preserving the complete text report. Rich graphics require a public repository, contents: write, and an unprotected pytest-obligation-assets branch.');
      }
    }
    // Recheck after pagination. Callers serialize the publishing step per PR/key
    // with workflow concurrency; GitHub's comment API has no compare-and-swap.
    const {data: latest} = await github.rest.pulls.get({...context.repo, pull_number: pr.number});
    if (latest.head.sha !== snapshot.head) return;
    const payload = {...context.repo, body: `${body}\n\n${metadata}\n${marker}`};
    if (existing) await github.rest.issues.updateComment({...payload, comment_id: existing.id});
    else await github.rest.issues.createComment({...payload, issue_number: pr.number});
  } catch (error) {
    if ([403, 404].includes(error.status)) {
      core.warning('PR comment unavailable with this token; report retained in summary/artifact.');
      return;
    }
    throw error;
  }
};
