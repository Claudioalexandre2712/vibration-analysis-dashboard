"""Contrato de ensaio: colunas, unidades, tempo e amostragem consistentes."""
import unicodedata
import numpy as np
import pandas as pd
from utils import safe_read_csv, validate_sampling_frequency

MAX_SAMPLES = 200_000


def normalize(name):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(name).lower()) if not unicodedata.combining(c))


def inspect_csv(data):
    df = safe_read_csv(data, nrows=MAX_SAMPLES+1)
    if not 50 <= len(df) <= MAX_SAMPLES or len(df.columns) > 32:
        raise ValueError('Use entre 50 e 200.000 amostras e até 32 colunas.')
    names = {c:normalize(c) for c in df.columns}
    def find(tokens):
        return next((c for c,n in names.items() if any(t in n for t in tokens)), None)
    time = find(['tempo','time'])
    acceleration = find(['vibr','acel','accel','sinal'])
    tach = find(['tac','tach','trigger'])
    metadata = find(['frequencia','frequency','sampling','sample_rate'])
    if time is None and all(str(c).startswith('coluna_') for c in df.columns) and len(df.columns) >= 2:
        time = df.columns[0]
    if acceleration is None:
        candidates = [c for c in df.columns if c not in [time,tach,metadata]]
        if len(candidates) == 1:
            acceleration = candidates[0]
    return df, {'columns':list(df.columns),'samples':len(df),'time_column':time,'signal_column':acceleration,'tach_column':tach,'fs_column':metadata}


def load_measurement(data, fs=None, signal_column=None, time_column=None, tach_column=None, unit='m/s2'):
    df, info = inspect_csv(data)
    warnings = []
    def choose(value, default):
        if value == '__none__':
            return None
        if value and value not in df:
            raise ValueError('Coluna selecionada não existe no arquivo.')
        return value or default
    col = choose(signal_column, info['signal_column'])
    time_col = choose(time_column, info['time_column'])
    tac_col = choose(tach_column, info['tach_column'])
    if col is None:
        raise ValueError('Selecione a coluna de aceleração para evitar uma escolha ambígua.')
    if col in [time_col,tac_col] or (time_col is not None and time_col == tac_col):
        raise ValueError('Tempo, aceleração e tacômetro precisam ser colunas distintas.')
    def numeric(c):
        values = pd.to_numeric(df[c],errors='coerce').to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f'Coluna {c} contém valores vazios, não numéricos ou infinitos.')
        return values
    x = numeric(col)
    factors = {'m/s2':1.,'g':9.80665,'mm/s2':.001}
    if unit not in factors:
        raise ValueError('Unidade de aceleração inválida.')
    x = x*factors[unit]
    if not np.isfinite(x).all() or np.max(np.abs(x)) > 1e9:
        raise ValueError('Amplitude fora da faixa de processamento. Confira unidade e coluna.')
    if np.std(x) < 1e-12:
        raise ValueError('Sinal constante; não há vibração variável para analisar.')
    t, inferred = None, None
    if time_col:
        t = numeric(time_col)
        dt = np.diff(t)
        if np.any(dt <= 0):
            raise ValueError('Tempo precisa aumentar sem repetições e estar em segundos.')
        median = np.median(dt)
        if np.max(np.abs(dt-median))/median > .01:
            raise ValueError('Tempo irregular: variação superior a 1%. Reamostre o ensaio antes de analisar.')
        inferred = float(1/median)
    metadata = None
    if info['fs_column'] and info['fs_column'] not in [col,time_col,tac_col]:
        fs_values = numeric(info['fs_column'])
        if np.ptp(fs_values) > max(1e-8,abs(fs_values[0])*.001):
            raise ValueError('Metadado de frequência de amostragem não é constante.')
        metadata = float(fs_values[0])
    sources = [(label,float(value)) for label,value in [('Informada',fs),('Tempo do arquivo',inferred),('Metadado do arquivo',metadata)] if value is not None]
    if not sources:
        raise ValueError('Informe a frequência de amostragem em Hz ou selecione a coluna de tempo em segundos.')
    for label,value in sources:
        valid,error = validate_sampling_frequency(value,min_fs=1)
        if not valid:
            raise ValueError(error)
    chosen = sources[0][1]
    if any(abs(value-chosen)/chosen > .01 for _,value in sources):
        raise ValueError('Conflito de frequência de amostragem entre valor informado, tempo e metadado. Confira o ensaio.')
    if any(abs(value-chosen)/chosen > .0001 for _,value in sources):
        warnings.append('Pequena diferença entre tempo e metadado de amostragem; confira a aquisição.')
    if t is None:
        t = np.arange(len(x))/chosen
    return {'signal':x,'time':t-t[0],'fs':chosen,'fs_source':sources[0][0], 'warnings':warnings,
            'columns':info['columns'],'signal_column':col,'time_column':time_col,'tachometer':numeric(tac_col) if tac_col else None}
