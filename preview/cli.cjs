#!/usr/bin/env node
// Run from a reviewed pytest-obligation checkout, never from the adopter's repository.
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {preview, parseOptions, safeMessage, PreviewError} = require('./preview.cjs');
const execute = promisify(execFile);

async function main() {
  const options = parseOptions(process.argv.slice(2));
  if (options.help) {
    console.log('Usage: node preview/cli.cjs --pr https://github.com/OWNER/REPO/pull/NUMBER --run https://github.com/FORK/REPO/actions/runs/ID[/attempts/N] [--sticky-key KEY]\n\nPosts or updates your contributor preview. Requires Node 22+, Docker and gh auth login.\nOnly public fork push/dispatch runs matching your own open PR are accepted.\nNever runs tests or checks out contributor code. Keep invocations for one PR/key sequential.');
    return;
  }
  let token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
  if (!token) {
    try {
      // stdout is captured in memory, never printed or written. No token appears in the command's arguments.
      const result = await execute('gh', ['auth', 'token', '--hostname', 'github.com'],
        {cwd:__dirname, timeout:15_000, maxBuffer:16_384});
      token = result.stdout.trim();
    } catch { throw new PreviewError('Sign in with gh auth login --hostname github.com, then retry.'); }
  }
  if (!token || /\s/.test(token)) throw new PreviewError('GitHub authentication is unavailable. Check gh auth status.');
  const result = await preview(options, {token});
  console.log(`${result.status}: ${result.url}`);
}

main().catch(error => { console.error(safeMessage(error)); process.exitCode = 1; });
