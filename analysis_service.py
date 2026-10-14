"""Um único ensaio alimenta métricas, gráficos e indícios espectrais."""
from datetime import datetime, timezone
import uuid
import numpy as np
from scipy.signal import find_peaks
from analise_vibracoes import (
    remover_offset, aplicar_janela, calcular_fft, calcular_metricas, detectar_rpm_hibrido,
    aceleracao_para_velocidade, media_sincrona_por_volta, envelope_rolamento,
    diagnosticar_por_scores, bearing_frequencies,
)

VERSION = '2.2.1'


def _plot(x,y,limit=2000,peaks=False):
    if len(x) <= limit:
        idx = np.arange(len(x))
    else:
        edges = np.linspace(0,len(x),limit//2+1,dtype=int)
        idx = []
        for a,b in zip(edges[:-1],edges[1:]):
            if peaks:
                idx.append(a+int(np.argmax(y[a:b])))
            else:
                idx.extend([a+int(np.argmin(y[a:b])),a+int(np.argmax(y[a:b]))])
        idx = np.unique(idx)
    return {'x':np.asarray(x)[idx].tolist(),'y':np.asarray(y)[idx].tolist()}


def analyze_measurement(m,rpm=None,bearing=None,teeth=0,tsa=False,velocity_min=10.,velocity_max=1000.,health_reference=False):
    fs = float(m['fs'])
    x = remover_offset(m['signal'])
    warnings = list(m['warnings'])
    if not np.isfinite([velocity_min,velocity_max]).all() or not 0 < velocity_min < velocity_max or velocity_min >= fs/2:
        raise ValueError('Banda de velocidade inválida: mínimo >0 e abaixo de Nyquist; máximo maior que mínimo.')
    upper = min(velocity_max,fs/2)
    if upper < velocity_max*(1-1e-9):
        warnings.append(f'Banda de velocidade limitada por Nyquist a {upper:g} Hz.')
    if rpm is not None:
        if not np.isfinite(rpm) or rpm <= 0 or rpm/60 >= fs/2:
            raise ValueError('RPM precisa ser positivo e sua frequência estar abaixo de Nyquist.')
        rotation = {'rpm':float(rpm),'method':'Manual','confidence':'Informada pelo usuário'}
    elif m.get('tachometer') is not None:
        reference = m['tachometer']
        if np.ptp(reference) <= 1e-12:
            raise ValueError('Tacômetro constante; selecione outra coluna ou desative o tacômetro.')
        edges = np.where(np.diff((reference > (reference.min()+reference.max())/2).astype(int)) == 1)[0]+1
        if len(edges) < 3:
            raise ValueError('Tacômetro precisa de pelo menos três pulsos (um por volta).')
        periods = np.diff(edges)/fs
        if np.std(periods)/np.mean(periods) > .1:
            warnings.append('Rotação varia mais de 10% no tacômetro; interpretar espectro com cautela.')
        rotation = {'rpm':float(60/np.median(periods)),'method':'Tacômetro','confidence':'Um pulso por volta'}
    else:
        estimate = detectar_rpm_hibrido(x,fs)
        rotation = {'rpm':float(estimate['Rotação Calculada (RPM)']),'method':'Estimativa espectral','confidence':estimate['Justificativa']}
        warnings.append('RPM estimado pelo espectro pode representar um harmônico ou outra fonte. Confirme com uma medição de rotação.')
    processed = x
    tsa_status = 'Não aplicada'
    if tsa:
        if rotation['method'] == 'Estimativa espectral':
            raise ValueError('Para aplicar TSA, informe RPM estável ou selecione tacômetro de um pulso por volta.')
        reference = m.get('tachometer') if rotation['method'] == 'Tacômetro' else None
        processed = media_sincrona_por_volta(x,reference,fs,rotation['rpm'])
        if m.get('tachometer') is not None and reference is None:
            warnings.append('RPM manual prevalece sobre o tacômetro na média síncrona.')
        tsa_status = 'Média síncrona por volta; referência assume um pulso por volta ou RPM estável'
    # Métricas e diagnóstico usam o ensaio sem DC, não janela nem média TSA.
    windowed,gain = aplicar_janela(x)
    f,a,phase = calcular_fft(windowed,fs,gain)
    metrics = calcular_metricas(x)
    if not np.any((f >= velocity_min) & (f <= upper) & (f < fs/2)):
        raise ValueError('Banda de velocidade sem frequências disponíveis; aumente o tempo do ensaio para melhorar a resolução ou ajuste a banda.')
    velocity = aceleracao_para_velocidade(x,fs,velocity_min,upper)
    metrics['velocity_rms_mm_s'] = float(np.sqrt(np.mean(velocity**2))*1000)
    fr = rotation['rpm']/60
    resolved = fr >= 4*fs/len(x)
    metrics['amplitude_1x'] = None
    metrics['phase_1x_deg'] = None
    if fr and resolved:
        # Fit the exact reference frequency, with an independent constant term.
        angle = 2*np.pi*fr*np.arange(len(x))/fs
        design = np.column_stack((np.cos(angle),np.sin(angle),np.ones(len(x))))
        cosine,sine,_ = np.linalg.lstsq(design,x,rcond=None)[0]
        metrics['amplitude_1x'] = float(np.hypot(cosine,sine))
        metrics['phase_1x_deg'] = float(np.rad2deg(np.arctan2(-sine,cosine)))
    if fr and not resolved:
        warnings.append('Ensaio curto demais para medir 1X de forma resolvida; amplitude e fase de 1X indisponíveis.')
    diag = diagnosticar_por_scores(f,a,fr)
    bfreq = bearing_frequencies(rotation['rpm'],bearing) if bearing and fr else {}
    if bearing and not fr:
        raise ValueError('Informe rotação para calcular frequências de rolamento.')
    if not np.isfinite(teeth) or teeth < 0 or teeth != int(teeth) or teeth > 10000:
        raise ValueError('Número de dentes deve ser inteiro de 0 a 10.000.')
    gmf = fr*teeth if teeth and fr else None
    ef,ea = envelope_rolamento(x,fs)
    for name,value in {**bfreq,**({'GMF':gmf} if gmf else {})}.items():
        if value >= fs/2:
            warnings.append(f'{name} ({value:.1f} Hz) fora da faixa de Nyquist; não é observável neste ensaio.')
    if len(x)/fs < 1:
        warnings.append('Ensaio menor que 1 segundo; a resolução espectral pode ser insuficiente.')
    raw_f,raw_a,_ = calcular_fft(m['signal'],fs)
    processed_window,processed_gain = aplicar_janela(processed)
    processed_f,processed_a,_ = calcular_fft(processed_window,fs,processed_gain)
    window_samples = min(len(x),max(2,int(round(fs*.1))))
    # Prefix/suffix sums per block avoid subtracting large, almost equal totals.
    padding = (-len(x)) % window_samples
    blocks = np.pad(x*x,(0,padding)).reshape(-1,window_samples)
    prefix = np.cumsum(blocks,axis=1).ravel()
    suffix = np.cumsum(blocks[:,::-1],axis=1)[:,::-1].ravel()
    starts = np.arange(len(x)-window_samples+1)
    ends = starts+window_samples-1
    totals = np.where(starts % window_samples == 0,prefix[ends],suffix[starts]+prefix[ends])
    rolling = np.sqrt(totals/window_samples)
    def peak_list(freq,amp):
        indexes=find_peaks(amp,prominence=max(float(amp.max())*.02,1e-12))[0]
        return [{'hz':float(freq[i]),'amplitude':float(amp[i])} for i in sorted(indexes,key=lambda i:amp[i],reverse=True)[:12]]
    bands=[]
    def band(kind,label,start,end,center,description):
        clipped_start,clipped_end=max(0.,start),min(fs/2,end)
        if clipped_start<clipped_end:
            bands.append({'kind':kind,'label':label,'start_hz':clipped_start,'end_hz':clipped_end,'center_hz':center,
                          'truncated':bool(end>fs/2),'description':description})
    if fr:
        band('unbalance','Desbalanceamento · 1X',.9*fr,1.1*fr,fr,'Componente síncrona de rotação; confirmar com fase e inspeção.')
        band('misalignment','Desalinhamento · 2X–3X',1.8*fr,3.2*fr,2.5*fr,'Harmônicos de rotação que podem se relacionar ao alinhamento.')
        band('looseness','Folga mecânica · 3X–10X',3*fr,10*fr,6*fr,'Múltiplos harmônicos; confirmar fixações e folgas.')
        if gmf:
            band('gear','Engrenamento · GMF',gmf-fr*.1,gmf+fr*.1,gmf,'Frequência calculada pelo número de dentes e rotação.')
        for key,value in bfreq.items():
            band('bearing',f'Rolamento · {key}',value-fr*.05,value+fr*.05,value,'Referência geométrica; investigar no envelope.')
    # Broad teaching regions; not computed bearing fault frequencies or diagnoses.
    regions=[]
    for kind,label,start,end,description in [
        ('unbalance','Desbalanceamento',.8*fr,1.2*fr,'Investigue a componente 1X e confirme com fase e inspeção do rotor.'),
        ('misalignment','Desalinhamento',1.8*fr,3.2*fr,'Observe 2X e 3X; compare direções axial e radial e confira o acoplamento.'),
        ('looseness','Folga Mecânica',3*fr,10*fr,'Procure vários harmônicos juntos e inspecione fixações, mancais e base.'),
        ('bearing','Rolamentos',10*fr,100*fr,'Região ampla para investigação. Defeitos específicos exigem envelope e frequências calculadas pela geometria.'),
        ('lubrication','Lubrificação',100*fr,None,'Alta frequência: investigar atrito e impactos. Um pico nesta região não confirma falha de lubrificação.')
    ]:
        stop=min(end,fs/2) if end is not None else fs/2
        regions.append({'kind':kind,'label':label,'start_hz':start,'end_hz':end,
                        'observable':bool(fr and start<stop),'observed_end_hz':stop if start<stop else None,
                        'description':description})
    severity={'label':'Sem classificação','level':'unclassified','description':'Selecione um critério de referência para comparar o RMS de velocidade. A condição real depende da máquina, montagem e operação.'}
    if health_reference:
        limits=[2.8,7.1,18.]
        level=int(np.searchsorted(limits,metrics['velocity_rms_mm_s'],side='right'))
        severity={'label':['Normal','Leve','Moderado','Severo'][level],'level':['normal','mild','moderate','severe'][level],
                  'thresholds_mm_s':limits,'description':'Comparação orientativa com limites de 2,8 / 7,1 / 18 mm/s; não é classificação normativa. Confirme se esses limites e a banda são adequados à máquina.'}
    return {'id':str(uuid.uuid4()),'version':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),
            'measurement':{'samples':len(x),'fs':fs,'fs_source':m['fs_source'],'duration_s':len(x)/fs,'resolution_hz':fs/len(x),'nyquist_hz':fs/2,'signal_column':m.get('signal_column'),'unit':'m/s²'},
            'rotation':rotation,'metrics':metrics,'diagnostics':diag,'warnings':warnings,'tsa':tsa_status,
            'bearing_frequencies':bfreq,'gear_mesh_hz':gmf,'velocity_band_hz':[velocity_min,upper],
            'severity':severity,'spectral_regions':regions,'analysis_bands':bands,'rolling_window_samples':window_samples,
            'plots':{'raw':_plot(m['time'],m['signal']),'processed':_plot(m['time'],processed),'spectrum':_plot(f,a,peaks=True),
                     'raw_spectrum':_plot(raw_f,raw_a,peaks=True),'processed_spectrum':_plot(processed_f,processed_a,peaks=True),
                     'rolling_rms':_plot(m['time'][window_samples-1:],rolling),'envelope':_plot(ef,ea,peaks=True)},
            'processed_peaks':peak_list(processed_f,processed_a),'peaks':peak_list(f,a)}
