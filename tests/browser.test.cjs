const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const {webcrypto,createHash}=require('node:crypto');
const {parseExport,reconcile,canonical,makeAPI,exportCSV}=require('../static/browser-demo.js');
const root=path.resolve(__dirname,'..');
const w=fs.readFileSync(path.join(root,'samples/warehouse.csv'),'utf8');
const t=fs.readFileSync(path.join(root,'samples/transport.csv'),'utf8');
const fixed=fs.readFileSync(path.join(root,'samples/transport-fixed.csv'),'utf8');
const header='record_id,shipment_id,sku,quantity\n';
function memory(){const map=new Map();return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v)};}
const post=(api,warehouse=w,transport=t,label='Sample')=>api('/api/runs',{method:'POST',body:JSON.stringify({label,warehouse,transport})});

test('browser comparison matches Python for fixtures and 100 generated cases',()=>{
  const pairs=[[w,t],[w,fixed]];
  for(let i=0;i<100;i++){
    let a=header,b=header;
    for(let j=0;j<12;j++){
      const shipment='S'+(j%4),sku='K'+(j%3),qty=(i*13+j*7)%99+1;
      a+=`W${j},${shipment},${sku},${qty}\n`;
      if((i+j)%5)b+=`T${j},${shipment},${sku},${qty+(j%2)}\n`;
    }
    pairs.push([a,b]);
  }
  const python=spawnSync('python3',['-c',
    "import json,sys,hashlib; from flowcheck.engine import parse_export,reconcile,RULE_VERSION; pairs=json.load(sys.stdin); out=[]\nfor a,b in pairs:\n w,t=parse_export(a,'WMS'),parse_export(b,'TMS'); c=json.dumps([RULE_VERSION,sorted(w,key=lambda r:r['record_id']),sorted(t,key=lambda r:r['record_id'])],sort_keys=True); out.append([reconcile(w,t),hashlib.sha256(c.encode()).hexdigest()])\nprint(json.dumps(out))"],{cwd:root,input:JSON.stringify(pairs),encoding:'utf8'});
  assert.equal(python.status,0,python.stderr);
  const expected=JSON.parse(python.stdout);
  for(let i=0;i<pairs.length;i++){
    const a=parseExport(pairs[i][0],'WMS'),b=parseExport(pairs[i][1],'TMS');
    assert.deepEqual(reconcile(a,b),expected[i][0]);
    assert.equal(createHash('sha256').update(canonical(a,b)).digest('hex'),expected[i][1]);
  }
});
test('quoted CSV, CRLF and BOM parse correctly',()=>{
  const rows=parseExport('\uFEFF'+header.replace('\n','\r\n')+'"A","S","K","2"\r\n','WMS');
  assert.equal(rows[0].quantity,2);
});
test('invalid imports and duplicates are rejected',()=>{
  for(const input of ['',header,header+'A,S,K,0',header+'A,S,K,-1',header+'A,S,K,1.5',header+'A,S,K,1\nA,S,K,1',header+'A,=SUM(A1),K,2',header+'"A,S,K,2',header+'A,S,K,2,extra'])assert.throws(()=>parseExport(input,'WMS'));
});
test('browser history retains original, deduplicates retry and verifies correction',async()=>{
  const api=makeAPI(memory(),webcrypto);
  const first=await post(api),retry=await post(api,w,t,'Relabeled'),corrected=await post(api,w,fixed,'Corrected');
  assert.equal(first.summary.exception_keys,3);
  assert.equal(retry.id,first.id);
  assert.equal(retry.label,'Sample');
  assert.equal(retry.audit.length,2);
  assert.equal(corrected.summary.exception_keys,0);
  assert.equal((await api('/api/runs')).length,2);
  assert.equal((await api('/api/runs/1')).source_records.WMS.length,9);
  assert.match(exportCSV(first),/QUANTITY_MISMATCH/);
});
test('failed imports and quota failures do not claim saved results',async()=>{
  const api=makeAPI(memory(),webcrypto);
  await assert.rejects(post(api,w,t+'T001,S,K,2\n'),/duplicate/);
  assert.equal((await api('/api/runs')).length,0);
  const full=makeAPI({getItem:()=>null,setItem:()=>{throw new Error('quota');}},webcrypto);
  await assert.rejects(post(full),/not saved/);
});
