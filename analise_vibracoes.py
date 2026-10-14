"""Processamento numérico de vibrações. Indícios não são probabilidades."""
import numpy as np
from scipy import signal, stats
from utils import validate_sampling_frequency


def _array(dados):
    x = np.asarray(dados, dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError('Sinal precisa ser unidimensional, finito e conter amostras.')
    return x


def _fs(fs):
    valid, error = validate_sampling_frequency(fs)
    if not valid:
        raise ValueError(error)
    return float(fs)


def remover_offset(dados):
    x = _array(dados)
    return x - np.mean(x)


def aplicar_janela(dados, tipo='hanning'):
    x = _array(dados)
    window = signal.windows.hann(len(x), sym=False) if tipo in ('hann','hanning') else np.ones(len(x))
    return x*window, 1/np.mean(window)


def calcular_fft(dados, fs, fator_correcao=1.):
    x, fs = _array(dados), _fs(fs)
    spectrum = np.fft.rfft(x)
    a = np.abs(spectrum)*float(fator_correcao)/len(x)
    a[1:-1 if len(x)%2 == 0 else None] *= 2
    return np.fft.rfftfreq(len(x), 1/fs), a, np.angle(spectrum)


def calcular_metricas(dados):
    x = _array(dados)
    rms = float(np.sqrt(np.mean(x*x)))
    peak = float(np.max(np.abs(x)))
    constant = np.std(x) <= np.finfo(float).eps
    return {'rms':rms, 'peak':peak, 'crest_factor':peak/rms if rms else 0.,
            'kurtosis':float(stats.kurtosis(x,fisher=False,bias=True)) if not constant else 0.,
            'skewness':float(stats.skew(x,bias=True)) if not constant else 0.}


def filtro_passabanda(dados, fs, freq_min, freq_max):
    x, fs = _array(dados), _fs(fs)
    if not 0 < freq_min < freq_max < fs/2:
        raise ValueError('Banda inválida: use 0 < mínimo < máximo < Nyquist.')
    sos = signal.butter(4,[freq_min,freq_max],btype='band',fs=fs,output='sos')
    if len(x) < 32:
        raise ValueError('Amostras insuficientes para filtrar.')
    return signal.sosfiltfilt(sos,x)


def aceleracao_para_velocidade(aceleracao, fs, freq_min=10., freq_max=1000.):
    x, fs = remover_offset(aceleracao), _fs(fs)
    f = np.fft.rfftfreq(len(x),1/fs)
    spectrum = np.fft.rfft(x)
    velocity = np.zeros_like(spectrum)
    mask = (f >= freq_min) & (f <= min(freq_max,fs/2)) & (f > 0)
    velocity[mask] = spectrum[mask]/(2j*np.pi*f[mask])
    if len(x)%2 == 0:
        velocity[-1] = 0
    return np.fft.irfft(velocity,n=len(x))


def detectar_picos_fft(f,A,altura_min=.01):
    return signal.find_peaks(np.asarray(A),height=altura_min,distance=2)[0]


def detectar_rpm_hibrido(dados,fs):
    x = remover_offset(dados)
    windowed,gain = aplicar_janela(x)
    f,a,_ = calcular_fft(windowed,fs,gain)
    df = f[1]-f[0]
    mask = (f >= max(1.,2*df)) & (f < min(float(fs)/4,1000.))
    empty = {'Rotação Calculada (RPM)':0.,'Frequência Fundamental (Hz)':0.,'Justificativa':'Sem componente periódica suficiente','confidence':'Indeterminada'}
    if not np.any(mask) or np.max(a[mask]) < 1e-10:
        return empty
    peaks = signal.find_peaks(a,height=np.max(a[mask])*.08,prominence=np.max(a[mask])*.03,distance=2)[0]
    peaks = peaks[mask[peaks]]
    if not len(peaks):
        return empty
    peaks = peaks[np.argsort(a[peaks])[-12:]]
    total = float(np.sum(a[peaks]**2))
    candidates = []
    for idx in peaks:
        fundamental = f[idx]
        harmonic = np.rint(f[peaks]/fundamental)
        matched = (harmonic >= 1) & (harmonic <= 10) & (np.abs(f[peaks]-harmonic*fundamental) <= max(1.5*df,fundamental*.015))
        explained = float(np.sum(a[peaks][matched]**2))/total
        candidates.append((explained,int(np.sum(matched)),float(a[idx]),float(fundamental)))
    best = max(candidates,key=lambda c:(round(c[0],6),c[1],c[2]))
    _,matches,_,fundamental = best
    confidence = 'Harmônicos consistentes' if matches >= 2 else 'Pico dominante; confirmar RPM'
    return {'Rotação Calculada (RPM)':fundamental*60,'Frequência Fundamental (Hz)':fundamental,
            'Justificativa':confidence,'confidence':'Estimada' if matches >= 2 else 'Baixa'}


def media_sincrona_por_volta(dados,tac,fs,rpm):
    x,fs = _array(dados),_fs(fs)
    if not np.isfinite(rpm) or rpm <= 0 or fs*60/rpm < 4:
        raise ValueError('RPM inválido ou poucas amostras por volta para TSA.')
    if tac is not None:
        reference = _array(tac)
        if len(reference) != len(x) or np.ptp(reference) <= 1e-12:
            raise ValueError('Tacômetro inválido.')
        high = reference > (np.min(reference)+np.max(reference))/2
        edges = np.where(np.diff(high.astype(int)) == 1)[0]+1
        if len(edges) < 3:
            raise ValueError('Tacômetro precisa de pelo menos três pulsos.')
        phase = np.interp(np.arange(len(x)),edges,np.arange(len(edges)))
        valid = (np.arange(len(x)) >= edges[0]) & (np.arange(len(x)) < edges[-1])
        revolutions = len(edges)-1
    else:
        phase = np.arange(len(x))*rpm/(60*fs)
        revolutions = int(phase[-1])
        valid = phase < revolutions
    if revolutions < 3:
        raise ValueError('TSA precisa de pelo menos três voltas completas.')
    bins = max(4,min(4096,int(round(fs*60/rpm))))
    indexes = np.floor((phase%1)*bins+1e-8).astype(int)%bins
    sums = np.bincount(indexes[valid],weights=x[valid],minlength=bins)
    counts = np.bincount(indexes[valid],minlength=bins)
    known = np.where(counts > 0)[0]
    average = np.interp(np.arange(bins),known,sums[known]/counts[known],period=bins)
    return np.interp((phase%1)*bins,np.arange(bins),average,period=bins)


def envelope_rolamento(dados,fs):
    x,fs = remover_offset(dados),_fs(fs)
    if len(x) >= 50:
        x = filtro_passabanda(x,fs,fs*.1,fs*.45)
    envelope = remover_offset(np.abs(signal.hilbert(x)))
    windowed,gain = aplicar_janela(envelope)
    f,a,_ = calcular_fft(windowed,fs,gain)
    return f,a


def bearing_frequencies(rpm,params):
    n,d,p,theta = [float(params[key]) for key in ('n','d','p','theta')]
    if not all(np.isfinite([n,d,p,theta])) or not (2 <= n <= 100 and n == int(n) and 0 < d < p and 0 <= theta <= 90):
        raise ValueError('Geometria inválida: n inteiro ≥2, 0 < d < p e ângulo de 0 a 90°.')
    fr = float(rpm)/60
    ratio = d/p*np.cos(np.deg2rad(theta))
    return {'BPFO':n/2*fr*(1-ratio),'BPFI':n/2*fr*(1+ratio),'BSF':p/(2*d)*fr*(1-ratio**2),'FTF':fr/2*(1-ratio)}


def diagnosticar_por_scores(f,A,freq_rot,threshold_minimo=15):
    f,a = np.asarray(f),np.asarray(A)
    if len(f) != len(a) or not len(f) or not np.isfinite(a).all():
        raise ValueError('Espectro inválido.')
    if freq_rot <= 0:
        return [{'titulo':'Rotação não determinada','descricao_quantitativa':'Informe o RPM medido para interpretar os harmônicos.','sugestao':'Use tacômetro ou referência de operação.','tipo':'indeterminado'}]
    resolution = f[1]-f[0]
    if freq_rot < 4*resolution:
        return [{'tipo':'RESOLUCAO','titulo':'Resolução insuficiente para separar harmônicos',
                 'descricao_quantitativa':f'Resolução {resolution:.3f} Hz para rotação de {freq_rot:.3f} Hz.',
                 'sugestao':'Use um ensaio mais longo antes de interpretar componentes de rotação.'}]
    def amplitude(freq):
        if freq > f[-1] or freq <= 0:
            return 0.
        mask = np.abs(f-freq) <= min(freq_rot*.2, max(resolution*1.5,freq*.015))
        return float(np.max(a[mask])) if np.any(mask) else 0.
    harmonics = [amplitude(freq_rot*i) for i in range(1,6)]
    maxamp = float(np.max(a[1:])) if len(a)>1 else 0.
    output = []
    def add(kind,title,text,suggestion):
        output.append({'tipo':kind,'titulo':title,'descricao_quantitativa':text,'sugestao':suggestion})
    if harmonics[0] > .01 and harmonics[0] >= .5*maxamp:
        add('DESBALANCEAMENTO','Possível desbalanceamento',f'Amplitude 1X: {harmonics[0]:.4f} m/s² em {freq_rot:.2f} Hz.','Verificar balanceamento do rotor, acúmulo de sujeira, corrosão e desgaste irregular.')
    if harmonics[1] > .01 and harmonics[1] >= .3*maxamp:
        add('DESALINHAMENTO','Possível desalinhamento',f'Amplitude 2X: {harmonics[1]:.4f} m/s² em {freq_rot*2:.2f} Hz.','Verificar alinhamento do acoplamento, mancais, tensão de correias e nivelamento da base.')
    if sum(v > max(.01,maxamp*.15) for v in harmonics[2:]) >= 2:
        add('FOLGA','Possível folga mecânica',f'Harmônicos: 3X = {harmonics[2]:.4f}, 4X = {harmonics[3]:.4f}, 5X = {harmonics[4]:.4f} m/s².','Verificar parafusos de fixação, acoplamentos, mancais, folgas em chavetas e base da máquina.')
    electric = amplitude(120)
    if electric > .02 and electric >= .25*maxamp:
        add('ELETRICO','Possível excitação elétrica',f'Amplitude em 120 Hz: {electric:.4f} m/s².','Comparar com rede de 60 Hz, condições elétricas e harmônicos mecânicos antes de concluir a causa.')
    if not output:
        add('SEM_INDICIO','Sem padrão conclusivo nas regras analisadas','A ausência de indícios não comprova condição normal.','Compare com linha de base e medições complementares.')
    return output


def analisar_vibracoes_completo(arquivo_csv,fs=None,params_rolamento=None):
    from csv_io import load_measurement
    from analysis_service import analyze_measurement
    if isinstance(arquivo_csv,(str,bytes)):
        if isinstance(arquivo_csv,str):
            with open(arquivo_csv,'rb') as handle:
                arquivo_csv = handle.read()
        m = load_measurement(arquivo_csv,fs=fs)
    else:
        if fs is None:
            raise ValueError('Informe a frequência de amostragem.')
        x = _array(arquivo_csv)
        m = {'signal':x,'time':np.arange(len(x))/_fs(fs),'fs':float(fs),'warnings':[],'columns':[],'fs_source':'Informada','tachometer':None}
    return analyze_measurement(m,bearing=params_rolamento)['diagnostics']


def analisar_vibracoes(arquivo_csv,fs=None,params_rolamento=None):
    return analisar_vibracoes_completo(arquivo_csv,fs,params_rolamento)


def diagnostico_rotacao_automatica(dados,fs):
    return analisar_vibracoes(dados,fs),detectar_rpm_hibrido(dados,fs)


def diagnostico_automatico(dados,fs,rpm_teorico=None):
    from analysis_service import analyze_measurement
    x = _array(dados)
    return analyze_measurement({'signal':x,'time':np.arange(len(x))/fs,'fs':fs,'warnings':[],'fs_source':'Informada','tachometer':None},rpm=rpm_teorico)['diagnostics']


def classificar_severidade(valor,thresholds):
    return ['Normal','Leve','Moderado','Severo','Crítico'][int(np.searchsorted(thresholds,valor,side='right'))]
