// In-memory GitHub transport. Tests still execute the production resolver, downloader and writer.
const crypto = require('node:crypto');
const HEAD = 'a'.repeat(40);
const TOKEN = 'preview-test-secret-never-print';
const options = {pr:'https://github.com/target/app/pull/12', run:'https://github.com/author/app/actions/runs/100', stickyKey:'obligation'};

function githubFixture(bytes = Buffer.from('evidence archive')) {
  const target = {id:10, full_name:'target/app', private:false};
  const fork = {id:20, full_name:'author/app', private:false};
  const viewer = {id:30, login:'author', type:'User'};
  const state = {
    viewer, pr:{number:12, state:'open', user:viewer, head:{sha:HEAD, ref:'adopt', repo:{...fork}}, base:{repo:target}},
    run:{id:100, run_attempt:1, event:'push', status:'completed', conclusion:'success', head_sha:HEAD,
      head_branch:'adopt', head_repository:{...fork}, repository:{...fork}},
    artifacts:[{id:40, name:'obligation-obligation-1', expired:false, size_in_bytes:bytes.length,
      digest:`sha256:${crypto.createHash('sha256').update(bytes).digest('hex')}`}],
    comments:[], calls:[], writes:[], reads:0, beforePrRead:() => {},
  };
  const fetcher = async (url, init = {}) => {
    const method = init.method || 'GET';
    state.calls.push({url, ...init, method});
    const parsed = new URL(url);
    const route = parsed.pathname;
    let result;
    if (parsed.hostname === 'storage.example') return new Response(bytes);
    if (parsed.origin !== 'https://api.github.com') throw new Error(`Unexpected API origin: ${url}`);
    if (route === '/user') result = state.viewer;
    else if (route === '/repos/target/app/pulls/12') { state.beforePrRead(++state.reads); result = state.pr; }
    else if (route.match(/^\/repos\/author\/app\/actions\/runs\/100(?:\/attempts\/\d+)?$/)) result = state.run;
    else if (route === '/repos/author/app/actions/runs/100/artifacts') result = {artifacts:state.artifacts};
    else if (route === '/repos/author/app/actions/artifacts/40/zip') return new Response(null, {status:302, headers:{location:'https://storage.example/archive'}});
    else if (route === '/repos/target/app/issues/12/comments' && method === 'GET') result = state.comments;
    else if (route === '/repos/target/app/issues/12/comments' && method === 'POST') {
      result = {id:200 + state.comments.length, body:JSON.parse(init.body).body, user:viewer};
      state.comments.push(result); state.writes.push({method, ...result});
    } else if (route.startsWith('/repos/target/app/issues/comments/') && method === 'PATCH') {
      result = state.comments.find(c => c.id === Number(route.split('/').at(-1)));
      if (!result) throw new Error('Unknown comment');
      result.body = JSON.parse(init.body).body; state.writes.push({method, ...result});
    } else throw new Error(`Unexpected GitHub request: ${method} ${url}`);
    return Response.json(result);
  };
  return {state, fetcher, options:{...options}, token:TOKEN};
}

module.exports = {githubFixture, HEAD, TOKEN, options};
