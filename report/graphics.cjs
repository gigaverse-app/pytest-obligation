// Publish generated SVG data on an assets-only branch; never execute report content.
const crypto = require('node:crypto');
const PLACEHOLDER = 'https://pytest-obligation.invalid/assets/';
const BRANCH = 'pytest-obligation-assets';
const blobHash = content => crypto.createHash('sha1').update(`blob ${Buffer.byteLength(content)}\0${content}`).digest('hex');

module.exports = async function publishGraphics({github, context, bundle, prefix}) {
  if (context.payload.repository?.private !== false) throw new Error('Public image hosting is unavailable for this repository.');
  if (!/^pr-[1-9]\d*\/[a-z0-9-]+\/$/.test(prefix)) throw new Error('Invalid image namespace.');
  if (bundle?.version !== 1 || typeof bundle.markdown !== 'string' || bundle.markdown.length > 55000 || !bundle.assets || Array.isArray(bundle.assets)) {
    throw new Error('Invalid graphics bundle.');
  }
  const files = Object.entries(bundle.assets);
  if (!files.length || files.length > 202 || Buffer.byteLength(JSON.stringify(bundle)) > 2_000_000) throw new Error('Invalid graphics size.');
  for (const [name, svg] of files) {
    if (!/^(totals|app-[0-9a-f]{16})-(dark|light)\.svg$/.test(name) || typeof svg !== 'string' || !svg.startsWith('<svg ')) throw new Error('Invalid SVG asset.');
    if (/<(?:script|foreignObject|image|a|style)\b|\bon[a-z]+\s*=|\b(?:href|src|style)\s*=|url\s*\(|<!/i.test(svg)) throw new Error('Active SVG content is forbidden.');
    if ([...svg.matchAll(/<\/?([A-Za-z][\w:-]*)\b/g)].some(m=>!['svg','title','text','g','rect','path'].includes(m[1]))) throw new Error('Unsupported SVG element.');
  }
  const referenced = [...bundle.markdown.matchAll(/https:\/\/pytest-obligation\.invalid\/assets\/([^"\s<>]+)/g)].map(m=>m[1]);
  if (!referenced.length || referenced.some(name=>!Object.hasOwn(bundle.assets,name))) throw new Error('Missing image asset.');
  const git = github.rest.git;
  const raw = context.serverUrl && context.serverUrl !== 'https://github.com'
    ? `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/raw`
    : `https://raw.githubusercontent.com/${context.repo.owner}/${context.repo.repo}`;
  for (let attempt=0; attempt<3; attempt++) {
    let previous = null, baseTree, existing = [];
    try {
      previous = (await git.getRef({...context.repo,ref:`heads/${BRANCH}`})).data.object.sha;
      baseTree = (await git.getCommit({...context.repo,commit_sha:previous})).data.tree.sha;
      const result = (await git.getTree({...context.repo,tree_sha:baseTree,recursive:'1'})).data;
      if (result.truncated) throw new Error('Image index is too large; preserving the Markdown report.');
      existing = result.tree.filter(e=>e.path.startsWith(prefix));
    } catch (error) { if (error.status !== 404) throw error; }
    const desired = new Map(files.map(([name,content])=>[prefix+name,{content,sha:blobHash(content)}]));
    let sha = previous;
    const unchanged = previous && existing.length === files.length && existing.every(e=>desired.get(e.path)?.sha === e.sha);
    if (!unchanged) {
      const tree = files.map(([name,content])=>({path:prefix+name,mode:'100644',type:'blob',content}));
      for (const entry of existing) if (entry.type === 'blob' && !desired.has(entry.path)) tree.push({path:entry.path,mode:'100644',type:'blob',sha:null});
      const created = await git.createTree({...context.repo,...(baseTree ? {base_tree:baseTree} : {}),tree});
      sha = (await git.createCommit({...context.repo,message:`chore(report): refresh ${prefix} graphics`,tree:created.data.sha,parents:previous ? [previous] : []})).data.sha;
      try {
        if (previous) await git.updateRef({...context.repo,ref:`heads/${BRANCH}`,sha,force:false});
        else await git.createRef({...context.repo,ref:`refs/heads/${BRANCH}`,sha});
      } catch (error) {
        if ([409,422].includes(error.status) && attempt<2) continue;
        throw error;
      }
    }
    return bundle.markdown.replaceAll(PLACEHOLDER,`${raw}/${sha}/${prefix}`);
  }
  throw new Error('Image publication could not resolve a concurrent update.');
};
