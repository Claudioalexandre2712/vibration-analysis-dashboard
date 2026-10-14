const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
let JSDOM;
try{({JSDOM}=require('jsdom'));}catch(_){({JSDOM}=require('../.tools/node_modules/jsdom'));}
const curve={x:[0,50,100,500],y:[0,1,.1,0]};
const result={id:'fixture',created_at:'2026-10-14T12:00:00Z',version:'2.1.0',filename:'ensaio.csv',machine:'Motor A',
  measurement:{samples:2000,fs:1000,fs_source:'Informada',duration_s:2,resolution_hz:.5,nyquist_hz:500},
  rotation:{rpm:3000,method:'Manual',confidence:'Informada'},metrics:{rms:.707,velocity_rms_mm_s:2.25,peak:1,crest_factor:1.414,kurtosis:1.5,skewness:0,amplitude_1x:1,phase_1x_deg:0},
  diagnostics:[{tipo:'DESBALANCEAMENTO',titulo:'Possível desbalanceamento',descricao_quantitativa:'1X = 1 m/s²',sugestao:'Verificar rotor'}],
  warnings:[],tsa:'Não aplicada',rolling_window_samples:100,velocity_band_hz:[10,500],
  severity:{label:'Normal',level:'normal',description:'Referência orientativa'},bearing_frequencies:{},gear_mesh_hz:null,
  analysis_bands:[{kind:'unbalance',label:'Desbalanceamento · 1X',start_hz:45,end_hz:55,center_hz:50,truncated:false,description:'Componente 1X'}],
  spectral_regions:[{kind:'unbalance',label:'Desbalanceamento',start_hz:40,end_hz:60,observable:true,observed_end_hz:60,description:'Observe 1X'},{kind:'misalignment',label:'Desalinhamento',start_hz:90,end_hz:160,observable:true,observed_end_hz:160},{kind:'looseness',label:'Folga Mecânica',start_hz:150,end_hz:500,observable:true,observed_end_hz:500},{kind:'bearing',label:'Rolamentos',start_hz:500,end_hz:5000,observable:false},{kind:'lubrication',label:'Lubrificação',start_hz:5000,end_hz:null,observable:false}],
  peaks:[{hz:50,amplitude:1}],processed_peaks:[{hz:50,amplitude:1},{hz:150,amplitude:.2}],
  plots:{raw:curve,processed:curve,spectrum:curve,raw_spectrum:curve,processed_spectrum:curve,rolling_rms:curve,envelope:curve}};

test('cinco abas isolam diagnósticos, defeitos, cinco gráficos, envelope e saúde',async()=>{
  const root=path.join(__dirname,'..');
  const dom=new JSDOM(fs.readFileSync(path.join(root,'templates/index.html'),'utf8'),{url:'http://localhost',runScripts:'outside-only'});
  const w=dom.window, doc=w.document, charts=[];
  w.HTMLElement.prototype.scrollIntoView=function(){};
  w.Plotly={newPlot:(id,data,layout)=>{charts.push({id,data,layout});return Promise.resolve();},purge:()=>{}};
  w.fetch=async url=>{
    if(url.startsWith('/api/examples/'))return {ok:true,blob:async()=>new w.Blob(['tempo,aceleracao\n0,1'])};
    if(url==='/api/inspect')return {ok:true,json:async()=>({columns:['tempo','aceleracao'],samples:2000,time_column:'tempo',signal_column:'aceleracao'})};
    if(url==='/api/analyze')return {ok:true,json:async()=>result};
    throw new Error(url);
  };
  w.localStorage.setItem('vibra.history.v2',JSON.stringify([{id:'legacy',created_at:'2026-10-14T11:00:00Z',filename:'antigo.csv',machine:'Motor A',rpm:3000,velocity:1,kurtosis:3,band_min:10,band_max:500,version:'2.0.0'}]));
  w.eval(fs.readFileSync(path.join(root,'public/app.js'),'utf8'));
  const tick=()=>new Promise(resolve=>setImmediate(resolve));
  await tick();doc.querySelector('[data-example="normal"]').click();for(let i=0;i<4;i++)await tick();
  doc.getElementById('analysis-form').dispatchEvent(new w.Event('submit',{cancelable:true,bubbles:true}));for(let i=0;i<4;i++)await tick();
  assert.equal(doc.getElementById('error').hidden,true,doc.getElementById('error').textContent);
  assert.deepEqual([...doc.querySelectorAll('[data-panel]')].map(b=>b.textContent),['Diagnóstico Geral','Gráfico de Defeitos','Gráficos de Análise','Análise de Rolamentos','Status de Saúde']);
  assert.equal(doc.getElementById('diagnostics').closest('[role=tabpanel]').id,'panel-indicators');
  assert.equal(doc.getElementById('metrics-table').closest('[role=tabpanel]').id,'panel-health');
  assert.equal(doc.getElementById('panel-indicators').hidden,false);
  for(const name of ['spectrum','wave','bearing','health']){
    doc.querySelector(`[data-panel="${name}"]`).click();
    assert.equal(doc.getElementById('panel-'+name).hidden,false);
    assert.equal([...doc.querySelectorAll('[role=tabpanel]')].filter(p=>!p.hidden).length,1);
  }
  for(const id of ['raw-wave-chart','raw-fft-chart','processed-wave-chart','processed-fft-chart','rms-chart','envelope-chart','polar-chart'])assert.ok(charts.some(c=>c.id===id),id);
  const spectral=charts.find(c=>c.id==='spectrum-chart');
  assert.equal(spectral.data[1].marker.symbol,'diamond');
  assert.equal(spectral.data[1].x[0],50);
  assert.ok(spectral.layout.shapes.every(s=>s.x0>=0&&s.x1<=500));
  assert.ok(spectral.layout.annotations.some(a=>a.text==='1X'));
  assert.equal(charts.find(c=>c.id==='polar-chart').data[0].theta[0],0);
  assert.match(doc.getElementById('processed-wave-title').textContent,/sem offset/);
  assert.equal(doc.getElementById('health-label').textContent,'Normal');
  assert.equal(doc.getElementById('bands-table').rows.length,3);
  assert.equal(doc.querySelectorAll('#zone-legend .zone-item').length,5);
  assert.equal(doc.querySelectorAll('#zone-legend .zone-unavailable').length,2);
  assert.ok(spectral.layout.annotations.some(a=>a.text==='9X'&&a.x===450));
  assert.ok(spectral.layout.annotations.some(a=>a.text.includes('Pico 3X')&&a.x===150&&a.y===.2));
  doc.getElementById('nav-history').click();
  assert.equal(doc.getElementById('history-trends').hidden,false);
  for(const id of ['history-chart','history-kurtosis-chart','history-amplitude-chart','history-rpm-chart'])assert.ok(charts.some(c=>c.id===id));
  assert.equal(doc.getElementById('history-body').rows.length,2);
  assert.equal(doc.getElementById('history-body').rows[0].cells.length,10);
  assert.match(doc.getElementById('history-body').rows[1].textContent,/Não registrado/);
  assert.equal(charts.find(c=>c.id==='history-chart').layout.shapes,undefined);
  assert.match(doc.getElementById('history-velocity-reference').textContent,/ocultas/);
  const amplitude=charts.find(c=>c.id==='history-amplitude-chart');
  assert.equal(amplitude.data[0].y[0],null);
  assert.equal(amplitude.data[0].y[1],1);
  assert.match(doc.getElementById('history-body').rows[0].textContent,/Possível desbalanceamento/);
  result.rotation.rpm=0;
  doc.getElementById('analysis-form').dispatchEvent(new w.Event('submit',{cancelable:true,bubbles:true}));for(let i=0;i<4;i++)await tick();
  assert.equal(doc.getElementById('spectrum-harmonics').disabled,true);
  result.rotation.rpm=3000;
  dom.window.close();
});
