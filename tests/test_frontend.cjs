const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validateHistoryEntry}=require('../public/app.js');
const row={id:'a',created_at:'2026-10-14T12:00:00Z',filename:'ensaio.csv',machine:'Motor 1',rpm:3000,velocity:1.2,kurtosis:3,band_min:10,band_max:500,version:'2.0.0'};
test('histórico importado preserva somente campos de resumo',()=>{
  const out=validateHistoryEntry({...row,plots:{huge:'ignored'}});
  assert.equal(out.rpm,3000);assert.equal(out.machine,'Motor 1');assert.equal(out.plots,undefined);
});
test('histórico recusa indicadores não finitos e tipos incorretos',()=>{
  for(const invalid of [NaN,Infinity,'10',null,-1])assert.throws(()=>validateHistoryEntry({...row,velocity:invalid}));
});
test('histórico recusa datas e textos inválidos',()=>{
  assert.throws(()=>validateHistoryEntry({...row,created_at:'not-a-date'}));
  assert.throws(()=>validateHistoryEntry({...row,machine:'x'.repeat(121)}));
});
