"""Um único ensaio alimenta métricas, gráficos e indícios espectrais."""
from datetime import datetime, timezone
import uuid
import numpy as np
from analise_vibracoes import (
    remover_offset, aplicar_janela, calcular_fft, calcular_metricas, detectar_rpm_hibrido,
    aceleracao_para_velocidade, media_sincrona_por_volta, envelope_rolamento,
    diagnosticar_por_scores, bearing_frequencies,
)

VERSION = '2.0.0'


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


def analyze_measurement(m,rpm=None,bearing=None,teeth=0,tsa=False,velocity_min=10.,velocity_max=1000.):
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
    velocity = aceleracao_para_velocidade(x,fs,velocity_min,upper)
    metrics['velocity_rms_mm_s'] = float(np.sqrt(np.mean(velocity**2))*1000)
    fr = rotation['rpm']/60
    idx = int(np.argmin(abs(f-fr))) if fr else 0
    resolved = fr >= 4*fs/len(x)
    metrics['amplitude_1x'] = float(a[idx]) if fr and resolved else None
    metrics['phase_1x_deg'] = float(np.rad2deg(phase[idx])) if fr and resolved else None
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
    return {'id':str(uuid.uuid4()),'version':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),
            'measurement':{'samples':len(x),'fs':fs,'fs_source':m['fs_source'],'duration_s':len(x)/fs,'resolution_hz':fs/len(x),'nyquist_hz':fs/2,'signal_column':m.get('signal_column'),'unit':'m/s²'},
            'rotation':rotation,'metrics':metrics,'diagnostics':diag,'warnings':warnings,'tsa':tsa_status,
            'bearing_frequencies':bfreq,'gear_mesh_hz':gmf,'velocity_band_hz':[velocity_min,upper],
            'severity':{'label':'Comparar com linha de base','description':'A classificação de condição depende da máquina, montagem e critério de avaliação. Não há classificação normativa automática.'},
            'plots':{'raw':_plot(m['time'],m['signal']),'processed':_plot(m['time'],processed),'spectrum':_plot(f,a,peaks=True),'envelope':_plot(ef,ea,peaks=True)},
            'peaks':[{'hz':float(f[i]),'amplitude':float(a[i])} for i in sorted(__import__('scipy').signal.find_peaks(a,prominence=max(float(a.max())*.02,1e-12))[0],key=lambda i:a[i],reverse=True)[:12]]}
