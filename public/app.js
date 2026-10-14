'use strict';

function validateHistoryEntry(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Registro inválido.');
  const text = (key, max) => {
    if (typeof value[key] !== 'string' || value[key].length > max) throw new Error('Texto inválido no histórico.');
    return value[key];
  };
  const num = (key, min = 0, max = 1e12) => {
    if (typeof value[key] !== 'number' || !Number.isFinite(value[key]) || value[key] < min || value[key] > max) throw new Error('Indicador inválido no histórico.');
    return value[key];
  };
  const created_at = text('created_at', 50);
  if (!Number.isFinite(Date.parse(created_at))) throw new Error('Data inválida no histórico.');
  return {id:text('id',80),created_at,filename:text('filename',200),machine:text('machine',120),
    rpm:num('rpm'),velocity:num('velocity'),kurtosis:num('kurtosis'),band_min:num('band_min'),band_max:num('band_max'),version:text('version',30)};
}

if (typeof module !== 'undefined') module.exports = {validateHistoryEntry};

function startApplication() {
  const $ = id => document.getElementById(id);
  const form = $('analysis-form');
  const storageKey = 'vibra.history.v2';
  let selectedFile = null, currentResult = null, history = [], selectionTicket = 0, inspecting = false, analyzing = false;
  let storageWorks = true;
  const number = (value, places=3) => value == null ? '—' : new Intl.NumberFormat('pt-BR', {maximumFractionDigits:places}).format(value);
  const node = (tag, content, className) => {const el=document.createElement(tag); if(content!=null)el.textContent=content; if(className)el.className=className; return el;};
  function icon(kind='signal') {
    const paths={signal:'M2 12h4l3-8 5 16 4-12 2 4h2',rotor:'M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m7.2 7.2 2.8 2.8M5.6 18.4l2.8-2.8m7.2-7.2 2.8-2.8',tool:'M14 5a5 5 0 0 0-6 6L3 16a3 3 0 0 0 4 4l5-5a5 5 0 0 0 7-6l-3 3-4-4 3-3',align:'M3 6h6v12H3zm12 0h6v12h-6zM9 10h6m-6 4h6',electric:'m13 2-8 12h6l-1 8 9-13h-6l1-7',check:'m6 12 4 4 8-8',info:'M12 10v7m0-11v1'};
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');
    if(['rotor','check','info'].includes(kind)){const circle=document.createElementNS(svg.namespaceURI,'circle');circle.setAttribute('cx','12');circle.setAttribute('cy','12');circle.setAttribute('r',kind==='rotor'?'5':'9');svg.append(circle);}
    const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[kind]||paths.signal);svg.append(path);return svg;
  }
  const explanations={
    DESBALANCEAMENTO:{icon:'rotor',meaning:'A vibração acompanha principalmente uma volta do eixo. Esse padrão pode ocorrer quando a massa do rotor está distribuída de forma desigual.',checks:['Balanceamento e limpeza do rotor','Acúmulo de sujeira, corrosão ou desgaste irregular','Fixação do rotor e condições de montagem'],confirm:'Compare fase e amplitude nas direções radial e axial; confirme a rotação medida.'},
    DESALINHAMENTO:{icon:'align',meaning:'Uma componente importante aparece a cada duas vezes a rotação. Isso pode estar relacionado à posição relativa dos eixos ou ao acoplamento.',checks:['Alinhamento do acoplamento e dos eixos','Desgaste e posicionamento dos mancais','Nivelamento da base e tensão das correias'],confirm:'Compare medições axiais e radiais e verifique o alinhamento com instrumento adequado.'},
    FOLGA:{icon:'tool',meaning:'Vários múltiplos da rotação aparecem juntos no sinal. Isso pode indicar componentes com movimento relativo ou fixação insuficiente.',checks:['Parafusos de fixação e base da máquina','Folgas em acoplamentos e chavetas','Mancais, alojamentos e apoios'],confirm:'Inspecione fixações e folgas e compare a vibração em diferentes pontos da estrutura.'},
    ELETRICO:{icon:'electric',meaning:'O sinal tem uma componente em 120 Hz, que pode se relacionar ao dobro de uma rede de 60 Hz. Harmônicos mecânicos também podem cair nessa frequência.',checks:['Conexões e condições elétricas do motor','Frequência da rede e harmônicos da rotação','Relação da vibração com carga e alimentação'],confirm:'Compare com corrente elétrica e condições de operação antes de atribuir a origem à parte elétrica.'},
    RESOLUCAO:{icon:'info',meaning:'O registro é curto em relação à rotação. Picos próximos se misturam, então não é possível separar os harmônicos com segurança.',checks:['Aumentar a duração da medição','Conferir a taxa de amostragem e a rotação informada'],confirm:'Faça um ensaio mais longo mantendo a mesma condição de operação.'},
    SEM_INDICIO:{icon:'check',meaning:'As regras analisadas não encontraram um padrão conclusivo neste ensaio. Isso não garante que a máquina esteja sem defeitos.',checks:['Comparar os indicadores com medições anteriores','Conferir ruídos, aquecimento, montagem e lubrificação','Avaliar envelope e frequências de rolamento quando aplicável'],confirm:'Mantenha o acompanhamento do mesmo ponto, carga e rotação.'}
  };
  function announce(message) { $('announcement').textContent=message; $('announcement').hidden=false; }
  function fail(message) { $('error').textContent=message; $('error').hidden=false; $('error').scrollIntoView({block:'center',behavior:'smooth'}); }
  function controls() {
    $('analyze-button').disabled=inspecting||analyzing;
    $('analyze-button').textContent=analyzing?'Analisando…':inspecting?'Lendo arquivo…':'Analisar sinal ↗';
    form.querySelectorAll('input,select,button[data-example]').forEach(el=>el.disabled=analyzing);
  }
  try {const stored=JSON.parse(localStorage.getItem(storageKey)||'[]'); if(!Array.isArray(stored)||stored.length>200)throw new Error(); history=stored.map(validateHistoryEntry);}
  catch(_) {announce('O histórico não pôde ser carregado. Seus arquivos não foram enviados. Você pode importar um histórico válido.');}
  function saveHistory() {
    try {localStorage.setItem(storageKey,JSON.stringify(history));storageWorks=true;}
    catch(_) {storageWorks=false;announce('O navegador não permitiu salvar o histórico. Exporte os resultados antes de fechar esta página.');}
    $('history-count').textContent=String(history.length);
  }
  $('history-count').textContent=String(history.length);
  function summary(r) {return validateHistoryEntry({id:r.id,created_at:r.created_at,filename:r.filename,machine:r.machine||'',rpm:r.rotation.rpm,velocity:r.metrics.velocity_rms_mm_s,kurtosis:r.metrics.kurtosis,band_min:r.velocity_band_hz[0],band_max:r.velocity_band_hz[1],version:r.version});}
  async function responseJson(response) {
    let value;
    try {value=await response.json();} catch(_) {throw new Error(response.status===413?'O arquivo excede o limite de upload. Use até 4 MB.':'O servidor não retornou uma resposta válida. Tente novamente em instantes.');}
    if(!response.ok)throw new Error(value.error||'Não foi possível concluir a análise.');
    return value;
  }
  function fillColumns(id, columns, selected, noneLabel) {
    const select=$(id); select.replaceChildren();
    if(noneLabel) {const option=node('option',noneLabel);option.value='__none__';select.append(option);}
    else {const option=node('option','Selecione a coluna');option.value='';select.append(option);}
    for(const col of columns) {const option=node('option',col);option.value=col;select.append(option);}
    select.value=selected||(noneLabel?'__none__':'');
  }
  async function selectFile(file) {
    const ticket=++selectionTicket;
    selectedFile=null; $('error').hidden=true; $('column-fields').hidden=true;
    $('file-name').textContent=file?file.name:'Selecionar arquivo CSV';
    if(!file) return;
    if(!file.name.toLowerCase().endsWith('.csv')||file.size>4*1024*1024) {inspecting=false;controls();fail('Selecione um CSV com até 4 MB.');return;}
    inspecting=true;controls();
    try {
      const data=new FormData();data.set('arquivo',file,file.name);
      const info=await responseJson(await fetch('/api/inspect',{method:'POST',body:data}));
      if(ticket!==selectionTicket)return;
      selectedFile=file;
      $('file-info').textContent=`${number(info.samples,0)} amostras · ${info.columns.length} colunas · ${number(file.size/1024,1)} KB`;
      fillColumns('signal-column',info.columns,info.signal_column);
      fillColumns('time-column',info.columns,info.time_column,'Sem coluna de tempo');
      fillColumns('tach-column',info.columns,info.tach_column,'Sem tacômetro');
      $('column-fields').hidden=false;
    } catch(error) {if(ticket===selectionTicket)fail(error.message);}
    finally {if(ticket===selectionTicket){inspecting=false;controls();}}
  }
  $('arquivo').addEventListener('change',()=>selectFile($('arquivo').files[0]));
  document.querySelectorAll('[data-example]').forEach(button=>button.addEventListener('click',async()=>{
    if(analyzing)return;
    try {
      const kind=button.dataset.example;
      const response=await fetch(`/api/examples/${kind}`);
      if(!response.ok)throw new Error('Não foi possível carregar o exemplo.');
      $('arquivo').value='';
      await selectFile(new File([await response.blob()],`sintetico_${kind}.csv`,{type:'text/csv'}));
      if(selectedFile){$('machine').value='Exemplo sintético';$('rpm-manual').value='1800';$('sampling-frequency').value='';announce('Exemplo sintético selecionado. Clique em Analisar sinal para explorar.');}
    }catch(error){fail(error.message);}
  }));
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(inspecting||analyzing)return;
    if(!selectedFile){fail('Selecione um CSV válido ou um exemplo sintético.');return;}
    if(!$('signal-column').value){fail('Selecione a coluna de aceleração.');return;}
    const data=new FormData(form);data.set('arquivo',selectedFile,selectedFile.name);
    analyzing=true;controls();$('error').hidden=true;$('busy').hidden=false;$('results').hidden=true;$('export-result').hidden=true;currentResult=null;
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),90000);
    try {
      const result=await responseJson(await fetch('/api/analyze',{method:'POST',body:data,signal:controller.signal}));
      currentResult=result;
      renderResult(result);
      history=[summary(result),...history].slice(0,200);saveHistory();
      if(storageWorks)announce('Análise concluída. Resumo salvo somente neste navegador. Exporte para preservar seus resultados.');
      $('workspace').focus({preventScroll:true});$('workspace').scrollIntoView({block:'start',behavior:'smooth'});
    }catch(error){fail(error.name==='AbortError'?'A análise excedeu o tempo de espera. Tente um ensaio menor.':error.message);}
    finally {clearTimeout(timeout);analyzing=false;$('busy').hidden=true;controls();}
  });
  const plotConfig={responsive:true,displaylogo:false,toImageButtonOptions:{format:'png',scale:2},modeBarButtonsToRemove:['lasso2d','select2d']};
  function plot(id,traces,xTitle,yTitle,extra={}) {
    if(typeof Plotly==='undefined') {announce('Os gráficos não carregaram. Os indicadores e a exportação continuam disponíveis; recarregue para tentar novamente.');return;}
    Plotly.newPlot(id,traces,{margin:{t:15,r:20,b:55,l:65},font:{family:'Segoe UI, sans-serif',size:11,color:'#667c88'},paper_bgcolor:'#fff',plot_bgcolor:'#fff',xaxis:{title:{text:xTitle},gridcolor:'#edf1f3',zeroline:false},yaxis:{title:{text:yTitle},gridcolor:'#edf1f3',zeroline:false},hovermode:'closest',legend:{orientation:'h',y:1.14},...extra},plotConfig);
  }
  function line(data,name,color='#147b80') {return {x:data.x,y:data.y,type:'scatter',mode:'lines',name,line:{color,width:1.5}};}
  function renderResult(r) {
    $('empty-state').hidden=true;$('results').hidden=false;$('export-result').hidden=false;
    $('result-subtitle').textContent=`${r.filename}${r.machine?' · '+r.machine:''}`;
    $('workspace-title').textContent='Resultado da análise';
    const findings=r.diagnostics.filter(d=>!['SEM_INDICIO','RESOLUCAO','indeterminado'].includes(d.tipo)).length;
    const overview=node('div',null,'overview-message');const overviewIcon=node('div',null,'overview-icon');overviewIcon.append(icon(findings?'tool':'info'));
    const overviewText=node('div');overviewText.append(node('strong',findings?`${findings} ${findings===1?'padrão merece':'padrões merecem'} sua atenção`:'Confira a interpretação do ensaio'),node('p','Leia os possíveis problemas abaixo e use as verificações sugeridas para orientar a inspeção.'));
    overview.append(overviewIcon,overviewText);
    const rotationSummary=node('div',null,'overview-rotation');rotationSummary.append(node('span','Rotação utilizada'),node('strong',number(r.rotation.rpm,1)+' RPM'),node('small',r.rotation.method==='Estimativa espectral'?'RPM estimado · confirme a rotação':r.rotation.method));
    $('result-overview').replaceChildren(overview,rotationSummary);
    const info=r.measurement;
    $('measurement-strip').replaceChildren();
    for(const [label,value]of [['Amostras',number(info.samples,0)],['Duração',number(info.duration_s,3)+' s'],['Amostragem',number(info.fs,3)+' Hz'],['Resolução',number(info.resolution_hz,3)+' Hz'],['Nyquist',number(info.nyquist_hz,2)+' Hz']]) {
      const el=node('div');el.append(node('span',label+' '),node('strong',value));$('measurement-strip').append(el);
    }
    $('warnings').replaceChildren(...r.warnings.map(w=>node('p',w)));$('warnings').hidden=!r.warnings.length;
    $('metrics').replaceChildren();
    for(const [label,value,unit,description] of [
      ['Velocidade RMS',r.metrics.velocity_rms_mm_s,'mm/s',`Banda ${number(r.velocity_band_hz[0])}–${number(r.velocity_band_hz[1])} Hz`],
      ['Aceleração RMS',r.metrics.rms,'m/s²','Sinal sem offset, sem janela'],
      ['Curtose',r.metrics.kurtosis,'','Pearson · referência gaussiana = 3'],
      ['Fator de crista',r.metrics.crest_factor,'','Pico absoluto / RMS']]) {
      const el=node('div',null,'metric');const strong=node('strong',number(value));strong.append(node('em',unit));el.append(node('span',label),strong,node('small',description));$('metrics').append(el);
    }
    $('rotation-info').replaceChildren(node('div',number(r.rotation.rpm,1)+' RPM','rotation-value'),node('p',r.rotation.method+' · '+r.rotation.confidence),node('p','Amostragem: '+info.fs_source));
    $('tsa-info').textContent=r.tsa==='Não aplicada'?'Original e sinal sem offset; TSA não aplicada.':r.tsa;
    const peakTable=node('table');const header=node('tr');header.append(node('th','Frequência (Hz)'),node('th','Amplitude (m/s²)'));peakTable.append(header);
    for(const p of r.peaks.slice(0,6)){const row=node('tr');row.append(node('td',number(p.hz,2)),node('td',number(p.amplitude,5)));peakTable.append(row);}
    $('peaks-table').replaceChildren(peakTable);
    $('diagnostics').replaceChildren();
    const order={FOLGA:0,DESALINHAMENTO:1,DESBALANCEAMENTO:2,ELETRICO:3};
    for(const d of [...r.diagnostics].sort((a,b)=>(order[a.tipo]??9)-(order[b.tipo]??9))){
      const content=explanations[d.tipo]||{icon:'info',meaning:d.descricao_quantitativa,checks:[d.sugestao],confirm:'Confira os parâmetros do ensaio antes de interpretar os gráficos.'};
      const el=node('article',null,'diagnosis-card'+(['SEM_INDICIO','RESOLUCAO','indeterminado'].includes(d.tipo)?' diagnosis-neutral':''));
      const head=node('div',null,'diagnosis-head');const symbol=node('span',null,'diagnosis-icon');symbol.append(icon(content.icon));
      const title=node('div');title.append(node('h3',d.titulo),node('span',['SEM_INDICIO','RESOLUCAO','indeterminado'].includes(d.tipo)?'Orientação para análise':'Indício espectral · confirmar na inspeção','diagnosis-caption'));head.append(symbol,title);
      const evidence=node('div',null,'diagnosis-evidence');evidence.append(node('strong','Evidência encontrada'),node('p',d.descricao_quantitativa));
      const meaning=node('div',null,'diagnosis-meaning');meaning.append(node('h4','O que isso pode significar'),node('p',content.meaning));
      const checks=node('div',null,'diagnosis-checks');checks.append(node('h4','O que verificar'));const list=node('ul');content.checks.forEach(c=>list.append(node('li',c)));checks.append(list);
      const confirm=node('div',null,'diagnosis-confirm');confirm.append(icon('check'),node('p',content.confirm));
      el.append(head,evidence,meaning,checks,confirm);$('diagnostics').append(el);
    }
    $('severity-info').textContent=r.severity.description;
    $('velocity-info').textContent=`Integração espectral entre ${number(r.velocity_band_hz[0])} e ${number(r.velocity_band_hz[1])} Hz. Assimetria: ${number(r.metrics.skewness,4)}. Fase de 1X: ${number(r.metrics.phase_1x_deg,2)}°. Fase relativa ao início do registro, sem referência mecânica absoluta.`;
    $('bearing-info').replaceChildren(node('h3','Frequências de referência'));
    const frequencies={...r.bearing_frequencies};if(r.gear_mesh_hz)frequencies.GMF=r.gear_mesh_hz;
    if(!Object.keys(frequencies).length)$('bearing-info').append(node('p','Informe geometria de rolamento ou número de dentes para calcular frequências de referência. O envelope pode ser explorado sem esses parâmetros.'));
    for(const [key,val]of Object.entries(frequencies))$('bearing-info').append(node('p',`${key}: ${number(val,2)} Hz${val>=info.nyquist_hz?' · fora de Nyquist':''}`));
    selectPanel('indicators');
  }
  function drawPanel(name) {
    if(!currentResult)return;
    const r=currentResult,fr=r.rotation.rpm/60;
    const shapes=fr?[1,2,3,4,5].filter(h=>h*fr<r.measurement.nyquist_hz).map(h=>({type:'line',x0:fr*h,x1:fr*h,y0:0,y1:1,yref:'paper',line:{color:'#b8d5d4',width:1,dash:'dot'}})):[];
    if(name==='spectrum')plot('spectrum-chart',[line(r.plots.spectrum,'FFT')],'Frequência (Hz)','Amplitude de pico (m/s²)',{shapes});
    if(name==='wave')plot('wave-chart',[line(r.plots.raw,'Original','#a6b6c0'),line(r.plots.processed,r.tsa==='Não aplicada'?'Sem offset':'TSA')],'Tempo (s)','Aceleração (m/s²)');
    if(name==='bearing') {
      const marks=Object.entries(r.bearing_frequencies).filter(([,v])=>v<r.measurement.nyquist_hz);
      plot('envelope-chart',[line(r.plots.envelope,'Envelope','#bb5b2c')],'Frequência (Hz)','Amplitude do envelope (m/s²)',{shapes:marks.map(([,v])=>({type:'line',x0:v,x1:v,y0:0,y1:1,yref:'paper',line:{color:'#b8cfd7',width:1,dash:'dot'}})),annotations:marks.map(([key,v],i)=>({x:v,y:1-i*.08,yref:'paper',text:key,showarrow:false,font:{size:10}}))});
    }
  }
  function selectPanel(name) {
    document.querySelectorAll('[data-panel]').forEach(b=>{const active=b.dataset.panel===name;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;$('panel-'+b.dataset.panel).hidden=!active;});drawPanel(name);
  }
  const tabs=[...document.querySelectorAll('[data-panel]')];
  tabs.forEach((b,i)=>{b.addEventListener('click',()=>selectPanel(b.dataset.panel));b.addEventListener('keydown',event=>{let next;if(event.key==='ArrowRight')next=(i+1)%tabs.length;if(event.key==='ArrowLeft')next=(i+tabs.length-1)%tabs.length;if(event.key==='Home')next=0;if(event.key==='End')next=tabs.length-1;if(next!==undefined){event.preventDefault();tabs[next].focus();selectPanel(tabs[next].dataset.panel);}});});
  function historyView() {
    $('analysis-view').hidden=true;$('history-view').hidden=false;$('nav-analysis').classList.remove('active');$('nav-history').classList.add('active');
    const filter=$('machine-filter');const previous=filter.value;filter.replaceChildren(node('option','Todos os equipamentos'));filter.firstChild.value='';
    for(const machine of [...new Set(history.map(r=>r.machine||'Sem identificação'))].sort()){const option=node('option',machine);option.value=machine;filter.append(option);}
    if([...filter.options].some(o=>o.value===previous))filter.value=previous;
    renderHistory();
  }
  function renderHistory() {
    const selected=$('machine-filter').value;
    const rows=history.filter(r=>!selected||(r.machine||'Sem identificação')===selected);
    $('history-body').replaceChildren();$('history-empty').hidden=rows.length>0;
    for(const r of rows){const tr=node('tr');for(const value of [new Date(r.created_at).toLocaleString('pt-BR'),r.machine||'Sem identificação',r.filename,number(r.rpm,1),number(r.velocity,4),`${number(r.band_min)}–${number(r.band_max)}`,number(r.kurtosis,3)])tr.append(node('td',value));$('history-body').append(tr);}
    $('history-chart').hidden=!selected||rows.length<2;
    if(selected&&rows.length>=2){const groups=new Map();for(const r of rows){const band=`${r.band_min}–${r.band_max} Hz`;if(!groups.has(band))groups.set(band,[]);groups.get(band).push(r);}const traces=[...groups].map(([band,group])=>{group.sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at));return {x:group.map(r=>r.created_at),y:group.map(r=>r.velocity),name:band,mode:'lines+markers',type:'scatter'};});plot('history-chart',traces,'Data e hora','Velocidade RMS (mm/s)');}
  }
  $('nav-history').addEventListener('click',historyView);
  $('nav-analysis').addEventListener('click',()=>{$('analysis-view').hidden=false;$('history-view').hidden=true;$('nav-analysis').classList.add('active');$('nav-history').classList.remove('active');const active=tabs.find(b=>b.getAttribute('aria-selected')==='true');if(active)drawPanel(active.dataset.panel);});
  $('machine-filter').addEventListener('change',renderHistory);
  function download(value,name) {const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('export-result').addEventListener('click',()=>{if(currentResult)download(currentResult,'vibracoes-analise.json');});
  $('export-history').addEventListener('click',()=>download({schema:'vibra-history-v2',entries:history},'vibracoes-historico.json'));
  $('import-history').addEventListener('click',()=>$('import-file').click());
  $('import-file').addEventListener('change',async()=>{const file=$('import-file').files[0];if(!file)return;try{if(file.size>2*1024*1024)throw new Error('O histórico deve ter até 2 MB.');const data=JSON.parse(await file.text());if(data.schema!=='vibra-history-v2'||!Array.isArray(data.entries)||data.entries.length>200)throw new Error('Formato de histórico inválido. Importe o JSON exportado pelo Vibrações.');const entries=data.entries.map(validateHistoryEntry);const merged=new Map([...history,...entries].map(r=>[r.id,r]));history=[...merged.values()].sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at)).slice(0,200);saveHistory();historyView();announce('Histórico importado neste navegador.');}catch(error){announce('Importação recusada: '+error.message);}finally{$('import-file').value='';}});
  $('clear-history').addEventListener('click',()=>{if(!history.length)return;if(!confirm('Limpar os resumos salvos neste navegador? Exporte antes para preservá-los.'))return;history=[];saveHistory();historyView();announce('Histórico deste navegador limpo.');});
}
if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded',startApplication);
