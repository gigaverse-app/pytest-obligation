const {test} = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const publishGraphics = require('./graphics.cjs');

// An in-memory Git object store exercises tree preservation, ref races and retries.
function store() {
  const commits = new Map(), trees = new Map(), calls = [];
  let ref = null, counter = 0, conflicts = 0;
  const hash = content => crypto.createHash('sha1').update(`blob ${Buffer.byteLength(content)}\0${content}`).digest('hex');
  const id = () => (++counter).toString(16).padStart(40, '0');
  const git = {
    getRef: async () => {if (!ref) throw {status:404}; return {data:{object:{sha:ref}}};},
    getCommit: async ({commit_sha}) => ({data:commits.get(commit_sha)}),
    getTree: async ({tree_sha}) => ({data:{tree:trees.get(tree_sha), truncated:false}}),
    createTree: async ({base_tree, tree}) => {
      const files = new Map((trees.get(base_tree) || []).map(e=>[e.path,e]));
      for (const e of tree) {
        if (e.sha === null) files.delete(e.path);
        else files.set(e.path,{path:e.path, type:'blob', mode:'100644', sha:hash(e.content)});
      }
      const sha=id(); trees.set(sha,[...files.values()]); calls.push(['tree',tree]); return {data:{sha}};
    },
    createCommit: async args => {const sha=id(); commits.set(sha,{...args,tree:{sha:args.tree}}); return {data:{sha}};},
    createRef: async ({ref: name, sha}) => {assert.equal(name,'refs/heads/pytest-obligation-assets'); if (ref) throw {status:422}; ref=sha; return {};},
    updateRef: async ({ref:name,sha,force}) => {
      assert.equal(name,'heads/pytest-obligation-assets'); assert.equal(force,false);
      if (conflicts-- > 0) throw {status:422}; ref=sha; return {};
    },
  };
  return {github:{rest:{git}}, calls, setConflicts:n=>{conflicts=n;}, files:()=>trees.get(commits.get(ref)?.tree.sha) || []};
}
const context = {repo:{owner:'owner',repo:'app'}, payload:{repository:{private:false}}};
const bundle = {version:1,markdown:'<img src="https://pytest-obligation.invalid/assets/totals-dark.svg">',assets:{'totals-dark.svg':'<svg xmlns="http://www.w3.org/2000/svg"><text>42</text></svg>'}};

test('graphics URLs point at immutable commit and identical evidence reuses assets',async()=>{
  const s=store();
  const body=await publishGraphics({github:s.github,context,bundle,prefix:'pr-12/key/'});
  assert.match(body,/raw\.githubusercontent\.com\/owner\/app\/[0-9a-f]{40}\/pr-12\/key\/totals-dark\.svg/);
  assert.equal(await publishGraphics({github:s.github,context,bundle,prefix:'pr-12/key/'}),body);
  assert.equal(s.calls.length,1);
});
test('updates keep other PR assets and recover a ref conflict without forcing',async()=>{
  const s=store();
  await publishGraphics({github:s.github,context,bundle,prefix:'pr-11/other/'});
  s.setConflicts(1);
  await publishGraphics({github:s.github,context,bundle,prefix:'pr-12/key/'});
  assert.equal(s.files().length,2);
  const next={...bundle,assets:{'totals-light.svg':bundle.assets['totals-dark.svg']},markdown:'https://pytest-obligation.invalid/assets/totals-light.svg'};
  await publishGraphics({github:s.github,context,bundle:next,prefix:'pr-12/key/'});
  assert.deepEqual(s.files().map(x=>x.path).sort(),['pr-11/other/totals-dark.svg','pr-12/key/totals-light.svg']);
});
test('private repositories and invalid bundles never write assets',async()=>{
  const s=store();
  for (const bad of [
    {...bundle,assets:{'../secret.svg':'<svg/>'}},
    {...bundle,assets:{'totals-dark.svg':'<svg><script>alert(1)</script></svg>'}},
    {...bundle,markdown:'<img src="https://pytest-obligation.invalid/assets/missing.svg">'},
  ]) await assert.rejects(publishGraphics({github:s.github,context,bundle:bad,prefix:'pr-12/key/'}));
  await assert.rejects(publishGraphics({github:s.github,context:{...context,payload:{repository:{private:true}}},bundle,prefix:'pr-12/key/'}));
  assert.equal(s.calls.length,0);
});
