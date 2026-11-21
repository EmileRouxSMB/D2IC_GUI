const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
function harness(){
  const nodes={
    '#section-samples':{value:'5'},'#history-field':{value:'u1'},'#run-frame':{value:'2'}
  };
  const context={URLSearchParams,resultSections:new Map(),$:selector=>nodes[selector]};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function mapMeshPoint('),source.indexOf('  function updateAnalysisGraphs(')),context);
  return {context,nodes};
}
test('section click maps deformed pixels to reference and survives frame change',()=>{
  const {context:c}=harness();
  const reference={nodes_xy:[[0,0],[4,0],[4,3],[0,3]],elements:[[0,1,2,3]]};
  const current={...reference,nodes_xy:reference.nodes_xy.map(([x,y])=>[2*x+y+7,3*y-2])};
  for(const point of [[1,1],[3,2],[0,0],[4,3]]){
    const deformed=c.mapMeshPoint(point,reference,current);
    const recovered=c.mapMeshPoint(deformed,current,reference);
    assert.ok(Math.hypot(recovered[0]-point[0],recovered[1]-point[1])<1e-10);
  }
  assert.equal(c.mapMeshPoint([50,50],current,reference),null);
});
test('section export fixes reference endpoints and validates sampling',()=>{
  const {context:c,nodes}=harness();
  assert.throws(()=>c.sectionParameters('run'),/extrémités/);
  c.resultSections.set('run',[[1,2],[4,6]]);
  const params=c.sectionParameters('run','sequence');
  assert.equal(params.get('scope'),'sequence');assert.equal(params.get('frame'),'2');
  assert.equal(params.get('x0'),'1');assert.equal(params.get('y1'),'6');
  nodes['#section-samples'].value='1.5';assert.throws(()=>c.sectionParameters('run'),/échantillons/);
  nodes['#section-samples'].value='200';c.resultSections.set('run',[[1,2],[1,2]]);
  assert.throws(()=>c.sectionParameters('run'),/distinctes/);
});
