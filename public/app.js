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
  const amplitude_1x=value.amplitude_1x==null?null:num('amplitude_1x');
  const severity=value.severity??'unclassified';
  if(!['normal','mild','moderate','severe','unclassified'].includes(severity))throw new Error('Condição inválida no histórico.');
  const diagnostics=value.diagnostics??[];
  if(!Array.isArray(diagnostics)||diagnostics.length>20||diagnostics.some(d=>typeof d!=='string'||d.length>160))throw new Error('Diagnóstico inválido no histórico.');
  return {amplitude_1x,severity,diagnostics:[...diagnostics],id:text('id',80),created_at,filename:text('filename',200),machine:text('machine',120),
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
  function summary(r) {return validateHistoryEntry({id:r.id,created_at:r.created_at,filename:r.filename,machine:r.machine||'',rpm:r.rotation.rpm,velocity:r.metrics.velocity_rms_mm_s,kurtosis:r.metrics.kurtosis,band_min:r.velocity_band_hz[0],band_max:r.velocity_band_hz[1],version:r.version,amplitude_1x:r.metrics.amplitude_1x,severity:r.severity.level,diagnostics:r.diagnostics.map(d=>d.titulo)});}
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
    const reference=(label,value,description,kind)=>{const card=node('div',null,'reference-item');const symbol=node('span',null,'reference-icon');symbol.append(icon(kind));const content=node('div');content.append(node('span',label),node('strong',value),node('small',description));card.append(symbol,content);return card;};
    $('result-overview').replaceChildren(
      reference('Rotação utilizada',number(r.rotation.rpm,1)+' RPM',r.rotation.method==='Estimativa espectral'?'Estimativa espectral · confirme a rotação':r.rotation.method,'rotor'),
      reference('Taxa de amostragem',number(r.measurement.fs,3)+' Hz',r.measurement.fs_source,'signal')
    );
    $('spectrum-harmonics').disabled=!(r.rotation.rpm>0);
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
    const hasTsa=r.tsa!=='Não aplicada';
    $('processed-wave-title').textContent=hasTsa?'Forma de Onda Processada (TSA)':'Forma de Onda Processada (sem offset)';
    $('processed-fft-title').textContent=hasTsa?'FFT Processada (TSA)':'FFT Processada (sem offset)';
    $('tsa-info').textContent=hasTsa?'Sinal após a média síncrona por volta. Reduz componentes não síncronas com a referência informada.':'Sinal com média removida. A TSA não foi aplicada; marque a opção e informe RPM estável ou tacômetro para executá-la.';
    $('defect-processing-note').textContent=hasTsa?'Este gráfico usa a FFT após TSA. O diagnóstico geral e as métricas globais usam o sinal sem offset antes da TSA.':'Este gráfico usa o sinal sem offset com janela Hann. A TSA não foi aplicada neste ensaio.';
    $('rolling-info').textContent=`RMS medido em janelas de ${r.rolling_window_samples} amostras (${number(1000*r.rolling_window_samples/info.fs,1)} ms), no sinal sem offset. Mostra a variação do nível de vibração ao longo do tempo.`;
    const peakTable=node('table');const header=node('tr');header.append(node('th','Frequência (Hz)'),node('th','Amplitude (m/s²)'));peakTable.append(header);
    for(const p of r.processed_peaks.slice(0,6)){const row=node('tr');row.append(node('td',number(p.hz,2)),node('td',number(p.amplitude,5)));peakTable.append(row);}
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
    $('health-card').className='health-card health-'+r.severity.level;
    $('health-label').textContent=r.severity.label;
    $('health-rms').textContent=number(r.metrics.velocity_rms_mm_s,3)+' mm/s';
    const healthMessages={normal:'RMS abaixo do primeiro limite de referência.',mild:'RMS na faixa de atenção da referência.',moderate:'RMS elevado em relação aos limites de referência.',severe:'RMS acima do maior limite de referência.',unclassified:'Compare este valor com a linha de base do equipamento.'};
    $('health-caption').textContent=healthMessages[r.severity.level]||healthMessages.unclassified;
    $('polar-caption').textContent=r.metrics.amplitude_1x==null?'1X indisponível: confira RPM e resolução do ensaio.':`1X · Amplitude: ${number(r.metrics.amplitude_1x,4)} m/s² · Fase: ${number(r.metrics.phase_1x_deg,1)}°`;
    $('velocity-info').textContent=`Velocidade integrada entre ${number(r.velocity_band_hz[0])} e ${number(r.velocity_band_hz[1])} Hz. A fase de 1X é relativa ao início do registro e não equivale a uma referência mecânica absoluta.`;
    $('metrics-table').replaceChildren();
    const metricRows=[
      ['Nível médio de vibração (RMS)',number(r.metrics.rms,5)+' m/s²','Nível global de aceleração do sinal sem offset. Compare com a mesma condição de operação.'],
      ['Velocidade RMS',number(r.metrics.velocity_rms_mm_s,4)+' mm/s','Velocidade calculada por integração na banda declarada. Usada para a comparação orientativa de saúde.'],
      ['Pico de aceleração',number(r.metrics.peak,5)+' m/s²','Maior amplitude absoluta do sinal sem offset. Ajuda a identificar eventos intensos.'],
      ['Fator de crista',number(r.metrics.crest_factor,3),'Relação entre pico e RMS. Valores elevados podem indicar impactos ou eventos transitórios.'],
      ['Índice de achatamento (Curtose)',number(r.metrics.kurtosis,3),'Curtose de Pearson calculada no ensaio. Uma distribuição gaussiana tem referência 3; impactos podem elevar o valor.'],
      ['Índice de assimetria (Skewness)',number(r.metrics.skewness,4),'Descreve a assimetria da distribuição de amplitudes. Próximo de zero indica distribuição mais simétrica.']
    ];
    for(const row of metricRows){const tr=node('tr');row.forEach(value=>tr.append(node('td',value)));$('metrics-table').append(tr);}
    $('bands-title').textContent='Faixas de Análise para '+number(r.rotation.rpm,0)+' RPM';
    $('bands-table').replaceChildren();$('zone-legend').replaceChildren();$('region-references').replaceChildren();
    for(const band of r.analysis_bands){
      const tr=node('tr',null,'band-row band-'+band.kind);
      for(const value of [band.label,number(band.center_hz,2)+' Hz',number(band.start_hz,2)+'–'+number(band.end_hz,2)+' Hz',band.description+(band.truncated?' Faixa limitada por Nyquist.':'')])tr.append(node('td',value));
      $('bands-table').append(tr);

    }
    for(const region of r.spectral_regions||r.analysis_bands){
      const item=node('article',null,'zone-item band-'+region.kind);
      const head=node('div',null,'zone-heading');head.append(icon(({unbalance:'rotor',misalignment:'align',looseness:'tool',bearing:'rotor',lubrication:'signal'})[region.kind]||'signal'),node('strong',region.label));
      item.append(head,node('span',r.rotation.rpm>0?number(region.start_hz,1)+(region.end_hz==null?'+':'–'+number(region.end_hz,1))+' Hz':'Informe RPM para calcular a faixa','zone-range'),node('p',region.description));
      if(region.observable===false)item.append(node('small',r.rotation.rpm>0?'Fora da faixa medida':'Referência de rotação indisponível','zone-unavailable'));
      else if(region.observed_end_hz!=null&&(region.end_hz==null||region.observed_end_hz<region.end_hz))item.append(node('small','Medido somente até '+number(region.observed_end_hz,1)+' Hz','zone-unavailable'));
      $('zone-legend').append(item);
    }
    for(const band of r.analysis_bands.filter(b=>['gear','bearing'].includes(b.kind)))$('region-references').append(node('p',band.label+': '+number(band.center_hz,2)+' Hz · referência calculada, marcada no gráfico.'));
    if(!r.gear_mesh_hz){const tr=node('tr');['Engrenagens (GMF)','Não calculada','Informe número de dentes','A faixa depende da engrenagem real; não é presumida.'].forEach(v=>tr.append(node('td',v)));$('bands-table').append(tr);}
    else if(r.gear_mesh_hz>=info.nyquist_hz){const tr=node('tr');['Engrenagens (GMF)',number(r.gear_mesh_hz,1)+' Hz','Fora de Nyquist','A aquisição atual não observa esta referência.'].forEach(v=>tr.append(node('td',v)));$('bands-table').append(tr);}
    if(!Object.keys(r.bearing_frequencies).length){const tr=node('tr');['Rolamentos','Não calculadas','Informe geometria','BPFO, BPFI, BSF e FTF dependem do rolamento e da rotação.'].forEach(v=>tr.append(node('td',v)));$('bands-table').append(tr);}
    $('bearing-info').replaceChildren(node('h3','Frequências de referência'));
    const frequencies={...r.bearing_frequencies};if(r.gear_mesh_hz)frequencies.GMF=r.gear_mesh_hz;
    if(!Object.keys(frequencies).length)$('bearing-info').append(node('p','Informe geometria de rolamento ou número de dentes para calcular frequências de referência. O envelope pode ser explorado sem esses parâmetros.'));
    for(const [key,val]of Object.entries(frequencies))$('bearing-info').append(node('p',`${key}: ${number(val,2)} Hz${val>=info.nyquist_hz?' · fora de Nyquist':''}`));
    selectPanel('indicators');
  }
  const bandColors={unbalance:'rgba(208,65,78,.16)',misalignment:'rgba(44,129,195,.16)',looseness:'rgba(222,161,48,.20)',gear:'rgba(49,153,109,.16)',bearing:'rgba(121,93,172,.16)',lubrication:'rgba(30,145,150,.16)'};
  function drawSpectrum(id,data,peaks,r,withBands=true) {
    const fr=r.rotation.rpm/60,nyquist=r.measurement.nyquist_hz;
    const regions=r.spectral_regions||r.analysis_bands;
    const shapes=withBands?regions.filter(b=>b.observable!==false&&b.start_hz<nyquist).map(b=>({type:'rect',x0:b.start_hz,x1:Math.min(b.end_hz??nyquist,nyquist),xref:'x',y0:0,y1:1,yref:'paper',fillcolor:bandColors[b.kind],line:{width:0},layer:'below'})):[];
    const annotations=[];
    for(let h=1;h<=10;h++)if(fr&&h*fr<nyquist){
      const color=h===1?'#c54050':h<=3?'#337ab5':'#987018';
      shapes.push({type:'line',x0:h*fr,x1:h*fr,y0:0,y1:1,yref:'paper',line:{color,width:1,dash:'dot'}});
      annotations.push({x:h*fr,y:.98-((h-1)%4)*.08,yref:'paper',text:h+'X',showarrow:false,font:{color,size:10},bgcolor:'#fff',bordercolor:color,borderpad:2});
    }
    for(const band of r.analysis_bands.filter(b=>['gear','bearing'].includes(b.kind)&&b.center_hz<nyquist)){
      shapes.push({type:'line',x0:band.center_hz,x1:band.center_hz,y0:0,y1:1,yref:'paper',line:{color:'#76529e',width:1.5,dash:'dash'}});
    }
    const peakLabel=p=>{const harmonic=Math.round(p.hz/fr);return fr&&harmonic>=1&&harmonic<=10&&Math.abs(p.hz-harmonic*fr)<=Math.min(fr*.08,r.measurement.resolution_hz*1.5)?harmonic+'X · '+number(p.hz,2)+' Hz':number(p.hz,2)+' Hz';};
    peaks.slice(0,6).forEach((p,i)=>annotations.push({x:p.hz,y:p.amplitude,text:'Pico '+peakLabel(p),showarrow:true,arrowhead:2,ax:i%2?35:-30,ay:-35-(i%3)*20,font:{size:10,color:'#8c461e'},bgcolor:'#fff',borderpad:3}));
    plot(id,[line(data,'FFT Processada','#204f79'),{x:peaks.map(p=>p.hz),y:peaks.map(p=>p.amplitude),text:peaks.map(peakLabel),hovertemplate:'%{text}<br>Amplitude: %{y:.5f} m/s²<extra>Pico medido</extra>',type:'scatter',mode:'markers',name:'Picos detectados',marker:{color:'#bb5b2c',size:8,symbol:'diamond'}}],'Frequência (Hz)','Amplitude de pico (m/s²)',{shapes,annotations,xaxis:{title:{text:'Frequência (Hz)'},range:[0,nyquist],gridcolor:'#e5ebef',zeroline:false},showlegend:true,legend:{orientation:'h',x:0,y:1.12,font:{size:10}}});
  }
  $('spectrum-full').addEventListener('click',()=>{if(currentResult&&typeof Plotly!=='undefined')Plotly.relayout('spectrum-chart',{'xaxis.range':[0,currentResult.measurement.nyquist_hz]});});
  $('spectrum-harmonics').addEventListener('click',()=>{if(currentResult&&currentResult.rotation.rpm>0&&typeof Plotly!=='undefined')Plotly.relayout('spectrum-chart',{'xaxis.range':[0,Math.min(currentResult.measurement.nyquist_hz,currentResult.rotation.rpm/60*11)]});});
  function drawPanel(name) {
    if(!currentResult)return;
    const r=currentResult;
    if(name==='spectrum')drawSpectrum('spectrum-chart',r.plots.processed_spectrum,r.processed_peaks,r);
    if(name==='wave') {
      plot('raw-wave-chart',[line(r.plots.raw,'Sinal bruto','#204f79')],'Tempo (s)','Aceleração (m/s²)');
      plot('raw-fft-chart',[line(r.plots.raw_spectrum,'FFT bruta','#c86421')],'Frequência (Hz)','Amplitude de pico (m/s²)');
      plot('processed-wave-chart',[line(r.plots.processed,r.tsa==='Não aplicada'?'Sem offset':'TSA','#078a7f')],'Tempo (s)','Aceleração (m/s²)');
      drawSpectrum('processed-fft-chart',r.plots.processed_spectrum,r.processed_peaks,r);
      plot('rms-chart',[line(r.plots.rolling_rms,'RMS móvel','#6151cf')],'Tempo (s)','RMS de aceleração (m/s²)');
    }
    if(name==='bearing') {
      const marks=Object.entries(r.bearing_frequencies).filter(([,v])=>v<r.measurement.nyquist_hz);
      plot('envelope-chart',[line(r.plots.envelope,'Envelope','#078a7f')],'Frequência (Hz)','Amplitude do envelope (m/s²)',{shapes:marks.map(([,v])=>({type:'line',x0:v,x1:v,y0:0,y1:1,yref:'paper',line:{color:'#926ca5',width:1,dash:'dot'}})),annotations:marks.map(([key,v],i)=>({x:v,y:1-i*.08,yref:'paper',text:key,showarrow:false,font:{size:10},bgcolor:'#fff'}))});
    }
    if(name==='health') {
      if(typeof Plotly==='undefined')return;
      if(r.metrics.amplitude_1x==null){Plotly.purge('polar-chart');$('polar-chart').hidden=true;return;}
      $('polar-chart').hidden=false;
      Plotly.newPlot('polar-chart',[{type:'scatterpolar',r:[r.metrics.amplitude_1x],theta:[r.metrics.phase_1x_deg],mode:'markers',name:'1X',marker:{size:13,color:'#245594'}}],{margin:{l:32,r:32,t:25,b:25},showlegend:false,paper_bgcolor:'#fff',font:{family:'Segoe UI',size:9,color:'#526b7b'},polar:{radialaxis:{range:[0,Math.max(r.metrics.amplitude_1x*1.6,.001)],tickformat:'.3g',nticks:5},angularaxis:{rotation:0,direction:'counterclockwise'}}},{responsive:true,displayModeBar:false});
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
    const rows=history.filter(r=>!selected||(r.machine||'Sem identificação')===selected).sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at));
    const labels={normal:'Normal',mild:'Leve',moderate:'Moderado',severe:'Severo',unclassified:'Sem classificação'};
    $('history-body').replaceChildren();$('history-empty').hidden=rows.length>0;
    $('history-summary').replaceChildren();
    for(const [label,count,kind] of [['Análises realizadas',rows.length,'total'],...Object.entries(labels).map(([key,label])=>[label,rows.filter(r=>r.severity===key).length,key])]){
      const item=node('div',null,'history-stat history-stat-'+kind);item.append(node('strong',String(count)),node('span',label));$('history-summary').append(item);
    }
    for(const r of rows){
      const tr=node('tr');
      for(const value of [new Date(r.created_at).toLocaleString('pt-BR'),r.machine||'Sem identificação',r.filename,number(r.velocity,4)])tr.append(node('td',value));
      const state=node('td');state.append(node('span',labels[r.severity]||labels.unclassified,'state-badge state-'+r.severity));tr.append(state);
      for(const value of [number(r.kurtosis,3),r.amplitude_1x==null?'Não registrado':number(r.amplitude_1x,4),number(r.rpm,1),`${number(r.band_min)}–${number(r.band_max)}`,r.diagnostics.length?r.diagnostics.join('; '):'Não registrado'])tr.append(node('td',value));
      $('history-body').append(tr);
    }
    $('history-trends').hidden=!rows.length;
    if(!rows.length)return;
    const groups=new Map();
    for(const r of rows){const key=r.machine?`${r.machine} · ${r.band_min.toFixed(6)}–${r.band_max.toFixed(6)} Hz`:`Sem identificação · ${r.id}`;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
    const traces=field=>[...groups].map(([key,group])=>{const ordered=[...group].sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at));return {x:ordered.map(r=>r.created_at),y:ordered.map(r=>r[field]??null),name:`${group[0].machine||'Sem identificação'} · ${number(group[0].band_min,2)}–${number(group[0].band_max,2)} Hz`,showlegend:Boolean(group[0].machine),text:ordered.map(r=>r.filename),hovertemplate:'%{x}<br>%{y}<br>%{text}<extra>%{fullData.name}</extra>',mode:group[0].machine?'lines+markers':'markers',type:'scatter',connectgaps:false,marker:{size:6},line:{width:1.8}};});
    const references=(values,unit)=>({shapes:values.map((v,i)=>({type:'line',xref:'paper',x0:0,x1:1,y0:v,y1:v,line:{color:['#c18d2e','#c85e41','#ad3548'][i],dash:'dash',width:1}})),annotations:values.map((v,i)=>({xref:'paper',x:1,y:v,text:number(v,1)+' '+unit,showarrow:false,xanchor:'right',yanchor:'bottom',font:{size:10,color:['#996d1d','#ad492d','#ad3548'][i]},bgcolor:'#fff'}))});
    const hasReference=rows.every(r=>r.severity!=='unclassified');
    $('history-velocity-reference').textContent=hasReference?'Referências: 2,8 / 7,1 / 18 mm/s':'Referências ocultas: há registros sem critério de saúde selecionado';
    plot('history-chart',traces('velocity'),'Data / hora','Velocidade RMS (mm/s)',hasReference?references([2.8,7.1,18],'mm/s'):{});
    plot('history-kurtosis-chart',traces('kurtosis'),'Data / hora','Curtose (Pearson)',references([3],'gaussiana'));
    plot('history-amplitude-chart',traces('amplitude_1x'),'Data / hora','Amplitude 1X (m/s²)');
    plot('history-rpm-chart',traces('rpm'),'Data / hora','RPM');
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
