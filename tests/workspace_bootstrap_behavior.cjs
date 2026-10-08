const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const source=require('node:fs').readFileSync(require('node:path').join(__dirname,'../assets/workspace-bootstrap.js'),'utf8');
function app(path, mounted) {
  const scripts=[],root={textContent:'',setAttribute(name,value){this[name]=value;}};
  let callback;
  let available=mounted;
  vm.runInNewContext(source,{
    window:{location:{pathname:path}},
    document:{documentElement:{},body:{appendChild(script){scripts.push(script);}},getElementById(){return available?root:null;},createElement(){return {};},addEventListener(){}},
    MutationObserver:class{constructor(fn){callback=fn;}observe(){}disconnect(){}},
  });
  return {scripts,root,mount(){available=true;callback();}};
}
test('driver and loader mount once when their root appears',()=>{
  for (const [route,src] of [['/driver','/driver-app.js'],['/loader','/loader-app.js']]) {
    const a=app(route,false);assert.equal(a.scripts.length,0);
    a.mount();a.mount();assert.equal(a.scripts.length,1);assert.equal(a.scripts[0].src,src);
  }
});
test('administrative pages do not load cabinet scripts',()=>{
  const a=app('/',true);a.mount();assert.equal(a.scripts.length,0);
});
test('failed script load exposes a readable alert',()=>{
  const a=app('/driver',true);a.scripts[0].onerror();assert.equal(a.root.role,'alert');assert.ok(a.root.textContent);
});
