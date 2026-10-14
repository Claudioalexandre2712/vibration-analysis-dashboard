const {test}=require('node:test');
const assert=require('node:assert/strict');
let JSDOM;
try {({JSDOM}=require('jsdom'));} catch (_) {({JSDOM}=require('../.tools/node_modules/jsdom'));}
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'..');
test('formulário envia RPM, unidade, geometria, máquina e TSA antes de bloquear controles',async()=>{
  const dom=new JSDOM(fs.readFileSync(path.join(root,'templates/index.html'),'utf8'),{url:'http://localhost',runScripts:'outside-only'});
  const w=dom.window;
  w.HTMLElement.prototype.scrollIntoView=function(){};
  let submitted;
  w.fetch=async(url,opts)=>{
    if(url.startsWith('/api/examples/'))return {ok:true,blob:async()=>new w.Blob(['tempo,aceleracao\n0,1'])};
    if(url==='/api/inspect')return {ok:true,json:async()=>({columns:['tempo','aceleracao'],samples:1000,time_column:'tempo',signal_column:'aceleracao'})};
    if(url==='/api/analyze'){submitted=opts.body;return {ok:false,json:async()=>({error:'Fim do teste de envio.'})};}
    throw new Error(url);
  };
  w.eval(fs.readFileSync(path.join(root,'public/app.js'),'utf8'));
  await new Promise(resolve=>setImmediate(resolve));
  w.document.querySelector('[data-example="normal"]').click();
  for(let i=0;i<4;i++)await new Promise(resolve=>setImmediate(resolve));
  const set=(id,value)=>w.document.getElementById(id).value=value;
  set('rpm-manual','3000');set('unit','g');set('machine','Motor A');set('sampling-frequency','1000');
  set('n','8');set('d','8');set('p','40');set('theta','0');
  w.document.getElementById('tsa').checked=true;
  w.document.getElementById('analysis-form').dispatchEvent(new w.Event('submit',{cancelable:true,bubbles:true}));
  for(let i=0;i<4;i++)await new Promise(resolve=>setImmediate(resolve));
  assert.ok(submitted);
  for(const [key,value]of Object.entries({rpm_manual:'3000',unit:'g',machine:'Motor A',sampling_frequency:'1000',n:'8',theta:'0',tsa:'on',signal_column:'aceleracao'}))assert.equal(submitted.get(key),value,key);
  dom.window.close();
});
