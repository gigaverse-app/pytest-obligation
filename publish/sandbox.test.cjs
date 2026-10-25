// Runs against Docker, not a mock. CI's actions lane and the fork rehearsal execute this file.
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const {buildImage, containerArgs, renderSandbox} = require('./publish.cjs');
const execute = promisify(execFile);
let image, directory, archive;

before(async () => {
  image = await buildImage(__dirname);
  directory = await fs.mkdtemp(path.join(os.tmpdir(), 'obligation-sandbox-'));
  archive = path.join(directory, 'evidence.zip');
  // Exercise the real producer, then poison only the uploaded Markdown and an irrelevant Python file.
  const producer = `
import sys, base64, tempfile, zipfile, json
from pathlib import Path
sys.path.insert(0, '/opt/reporter')
from pytest_obligation.reporting.__main__ import main
from pytest_obligation.profiles.coverage import Assessment, CaseEvidence, ProfileCoverage, SuiteCoverage
with tempfile.TemporaryDirectory() as root:
    root = Path(root)
    case = CaseEvidence(family='derive', collected=True, selected=True, outcomes={phase:['passed'] for phase in ('setup', 'call', 'teardown')})
    suite = SuiteCoverage(name='Orders', profiles={'F':ProfileCoverage(title='Discovery', assessment=Assessment(state='claimed'), cases={'derive':case})})
    (root/'report.json').write_text(json.dumps({'example.TestOrders':suite.model_dump(mode='json')}))
    main(['--input', str(root/'report.json'), '--output', str(root/'original.md'), '--stage-artifact', str(root/'artifact'), '--test-outcome', 'success'])
    (root/'artifact/report.md').write_text('FORGED MARKDOWN https://evil.invalid')
    (root/'artifact/sitecustomize.py').write_text('raise RuntimeError("UNTRUSTED IMPORT")')
    with zipfile.ZipFile(root/'archive.zip', 'w') as output:
        for item in (root/'artifact').rglob('*'):
            if item.is_file(): output.write(item, item.relative_to(root/'artifact').as_posix())
    print(base64.b64encode((root/'archive.zip').read_bytes()).decode())
`;
  const {stdout} = await execute('docker', ['run', '--rm', '--network=none', '--entrypoint', 'python', image, '-I', '-c', producer], {maxBuffer: 256 * 1024});
  await fs.writeFile(archive, Buffer.from(stdout.trim(), 'base64'), {mode: 0o644});
});
after(async () => { if (directory) await fs.rm(directory, {recursive:true, force:true}); });

test('real producer archive renders in the sandbox without importing or posting planted files', async () => {
  const body = await renderSandbox(__dirname, archive, {headSha:'a'.repeat(40), runId:7, runAttempt:1}, 'https://github.com/example/project', 'main');
  assert.match(body, /1 checks passed/);
  assert.match(body, /Test step \(reported\): \*\*success\*\*/);
  assert.doesNotMatch(body, /FORGED MARKDOWN|evil.invalid|UNTRUSTED IMPORT|Evidence unavailable/);
});

test('the actual container has no credentials, network, host workspace or write access to its input', async () => {
  const name = `obligation-probe-${process.pid}`;
  const args = containerArgs(image, archive, name);
  args.splice(args.length - 1, 0, '--entrypoint', 'python');
  const probe = `
import os, json, socket
from pathlib import Path
def writable(path):
    try:
        with open(path, 'a') as stream: stream.write('probe')
        return True
    except OSError: return False
try:
    socket.create_connection(('1.1.1.1', 443), timeout=0.2)
    network = True
except OSError: network = False
print(json.dumps(dict(
    uid=os.getuid(), token_present='OBLIGATION_TOKEN' in os.environ,
    network=network, interfaces=sorted(p.name for p in Path('/sys/class/net').iterdir()),
    root_writable=writable('/opt/probe'), input_writable=writable('/input/evidence.zip'),
    docker_socket=Path('/var/run/docker.sock').exists(), workspace=Path('/github/workspace').exists(),
    memory=Path('/sys/fs/cgroup/memory.max').read_text().strip(),
    processes=Path('/sys/fs/cgroup/pids.max').read_text().strip(),
    status=Path('/proc/self/status').read_text()
)))
`;
  const {stdout} = await execute('docker', [...args, '-I', '-c', probe], {env:{...process.env, OBLIGATION_TOKEN:'must-not-enter-container'}, timeout:15_000});
  const facts = JSON.parse(stdout);
  assert.equal(facts.uid, 65534);
  for (const field of ['token_present', 'network', 'root_writable', 'input_writable', 'docker_socket', 'workspace']) assert.equal(facts[field], false, field);
  assert.deepEqual(facts.interfaces, ['lo']);
  assert.equal(facts.memory, String(512 * 1024 * 1024));
  assert.equal(facts.processes, '32');
  assert.match(facts.status, /CapEff:\s+0000000000000000/);
  assert.match(facts.status, /NoNewPrivs:\s+1/);
});
