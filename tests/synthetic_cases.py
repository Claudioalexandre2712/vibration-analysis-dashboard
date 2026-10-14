"""Sinais sintéticos com verdade conhecida, sem dados de máquinas reais."""
import numpy as np
import pandas as pd


def cases():
    result=[]
    def add(name,x,fs=4000,fields=None,expected=('SEM_INDICIO',),**checks):
        t=np.arange(len(x))/fs
        frame=pd.DataFrame({'tempo_s':t,'aceleracao':x})
        result.append({'name':name,'raw':frame.to_csv(index=False,float_format='%.12g').encode(),
                       'fields':{'rpm_manual':'3000','unit':'m/s2','health_reference':'orientative',**(fields or {})},
                       'status':200,'expected':list(expected),'checks':checks})
    t=np.arange(8000)/4000
    wave=lambda f,a: a*np.sin(2*np.pi*f*t)
    add('01_baixa_amplitude',wave(50,.003),rms=.003/np.sqrt(2))
    add('02_desbalanceamento_1x',wave(50,.2),expected=('DESBALANCEAMENTO',),amplitude_1x=.2,peak_hz=50,rms=.2/np.sqrt(2))
    add('03_desalinhamento_2x',wave(50,.02)+wave(100,.2),expected=('DESALINHAMENTO',),peak_hz=100)
    add('04_folga_3x_4x_5x',wave(50,.02)+wave(150,.12)+wave(200,.1)+wave(250,.08),expected=('FOLGA',),peak_hz=150)
    add('05_excitacao_120hz',wave(50,.005)+wave(120,.2),expected=('ELETRICO',),peak_hz=120)
    add('06_multiplos_indicios',wave(50,.2)+wave(100,.16)+wave(150,.14)+wave(200,.12)+wave(250,.1)+wave(120,.1),expected=('DESBALANCEAMENTO','DESALINHAMENTO','FOLGA','ELETRICO'))
    add('07_pico_nao_harmonico',wave(50,.003)+wave(73,.3),peak_hz=73,note='Pico não harmônico não confirma ressonância; requer varredura de rotação/ensaio modal.')
    high_fs=12800; high_t=np.arange(25600)/high_fs
    modulated=.3*(1+.6*np.cos(2*np.pi*160*high_t))*np.cos(2*np.pi*3000*high_t)
    add('08_rolamento_modulacao_bpfo',modulated,fs=high_fs,fields={'n':'8','d':'10','p':'50','theta':'0'},envelope_hz=160,bpfo=160,note='Modulação conhecida; referência BPFO calculada. Não exige diagnóstico automático confirmado de rolamento.')
    add('09_engrenamento_gmf',wave(1000,.3)+wave(950,.1)+wave(1050,.1),fields={'num_dentes':'20'},peak_hz=1000,gmf=1000,note='GMF e bandas laterais conhecidas, sem confirmação de desgaste.')
    add('10_alta_frequencia_atrito',.3*np.sin(2*np.pi*5600*high_t)+.2*np.sin(2*np.pi*5900*high_t),fs=high_fs,peak_hz=5600,note='Energia em alta frequência; não permite concluir deficiência de lubrificação.')
    add('11_unidade_g',wave(50,.2)/9.80665,fields={'unit':'g'},expected=('DESBALANCEAMENTO',),amplitude_1x=.2)
    add('12_unidade_mm_s2',wave(50,200),fields={'unit':'mm/s2'},expected=('DESBALANCEAMENTO',),amplitude_1x=.2)
    add('13_tsa_com_ruido_nao_sincrono',wave(50,.2)+wave(73,.08),fields={'tsa':'on'},expected=('DESBALANCEAMENTO',),tsa_rejection_hz=73)
    add('14_tacometro',wave(50,.2),fields={'rpm_manual':'','tach_column':'tacometro'},expected=('DESBALANCEAMENTO',),rotation_method='Tacômetro')
    frame=pd.DataFrame({'tempo_s':t,'aceleracao':wave(50,.2),'tacometro':((np.arange(len(t))%80)<8).astype(int)})
    result[-1]['raw']=frame.to_csv(index=False,float_format='%.12g').encode()
    add('15_sinal_constante_sensor',np.ones(8000)*5,note='Sinal constante deve ser recusado; não comprova condição Normal.')
    result[-1].update(status=400,expected=[])
    add('16_ensaio_curto',np.sin(2*np.pi*20*np.arange(50)/1000)*.2,fs=1000,fields={'rpm_manual':'1200'},expected=('RESOLUCAO',))
    add('17_1x_entre_bins',.2*np.cos(2*np.pi*25.25*t+.4),fields={'rpm_manual':'1515'},expected=('DESBALANCEAMENTO',),amplitude_1x=.2,phase_deg=np.rad2deg(.4))
    add('18_decimal_virgula',wave(50,.2),expected=('DESBALANCEAMENTO',),amplitude_1x=.2)
    result[-1]['raw']=pd.DataFrame({'tempo_s':t,'aceleracao':wave(50,.2)}).to_csv(index=False,sep=';',decimal=',').encode()
    add('19_sem_tempo_taxa_informada',wave(50,.2),fields={'time_column':'__none__','sampling_frequency':'4000'},expected=('DESBALANCEAMENTO',))
    result[-1]['raw']=pd.DataFrame({'aceleracao':wave(50,.2)}).to_csv(index=False).encode()
    for name,raw,fields in [
        ('20_sem_tempo_sem_taxa',result[-1]['raw'],{'time_column':'__none__'}),
        ('21_nan',b'tempo_s,aceleracao\n'+b''.join(f'{i/1000},{"NaN" if i==10 else 1}\n'.encode() for i in range(100)),{}),
        ('22_tempo_duplicado',b'tempo_s,aceleracao\n'+b''.join(f'{(i if i!=10 else 9)/1000},1\n'.encode() for i in range(100)),{}),
        ('23_amostras_insuficientes',b'tempo_s,aceleracao\n'+b''.join(f'{i/1000},1\n'.encode() for i in range(30)),{}),
        ('24_geometria_invalida',result[1]['raw'],{'n':'8','d':'60','p':'50','theta':'0'}),
    ]:
        result.append({'name':name,'raw':raw,'fields':{'rpm_manual':'3000',**fields},'status':400,'expected':[],'checks':{}})
    add('25_rpm_estimado_harmonicos',wave(30,.2)+wave(60,.1),fields={'rpm_manual':''},expected=('DESBALANCEAMENTO','DESALINHAMENTO'),rpm=1800,rotation_method='Estimativa espectral')
    return result


def evaluate(case,status,r):
    errors=[]
    def require(ok,message):
        if not ok: errors.append(message)
    require(status==case['status'],f"HTTP {status}, esperado {case['status']}")
    if case['status']!=200:
        require(bool(r.get('error')) and 'plots' not in r,'Erro não deve retornar gráficos/resultados fictícios')
        return errors
    if status!=200:return errors
    require(sorted(d['tipo'] for d in r['diagnostics'])==sorted(case['expected']),f"Indícios {[d['tipo'] for d in r['diagnostics']]}, esperados {case['expected']}")
    checks=case['checks'];m=r['metrics']
    for key in ('rms','amplitude_1x'):
        if key in checks:require(np.isclose(m[key],checks[key],rtol=.01,atol=1e-8),f'{key}: {m[key]}, esperado {checks[key]}')
    if 'phase_deg' in checks:require(abs((m['phase_1x_deg']-checks['phase_deg']+180)%360-180)<.1,'Fase 1X incorreta')
    for field in ('rpm','method'):
        key='rotation_method' if field=='method' else 'rpm'
        if key in checks:require(np.isclose(r['rotation'][field],checks[key],rtol=1e-6) if field=='rpm' else r['rotation'][field]==checks[key],f'Rotação {field} incorreta')
    if 'severity' in checks:require(r['severity']['level']==checks['severity'],'Sinal constante classificado como saudável')
    for key,result_key in [('bpfo','BPFO')]:
        if key in checks:require(np.isclose(r['bearing_frequencies'][result_key],checks[key]),'Frequência geométrica incorreta')
    if 'gmf' in checks:require(np.isclose(r['gear_mesh_hz'],checks['gmf']),'GMF incorreta')
    if 'peak_hz' in checks:require(any(abs(p['hz']-checks['peak_hz'])<=r['measurement']['resolution_hz']*1.1 for p in r['processed_peaks']),'Pico esperado ausente')
    if 'envelope_hz' in checks:
        curve=r['plots']['envelope'];a=np.array(curve['y']);f=np.array(curve['x']);mask=f>5
        require(abs(f[mask][np.argmax(a[mask])]-checks['envelope_hz'])<2,'Envelope sem pico na modulação conhecida')
    if 'tsa_rejection_hz' in checks:
        curve=r['plots']['processed_spectrum'];idx=np.argmin(abs(np.array(curve['x'])-checks['tsa_rejection_hz']))
        require(curve['y'][idx]<.01,'TSA não reduziu componente não síncrona')
    require(all(np.isfinite(v) for v in m.values() if v is not None),'Métrica não finita')
    for curve in r['plots'].values():require(len(curve['x'])==len(curve['y']) and len(curve['x'])<=2000,'Curva inconsistente')
    require(all(0<=b['start_hz']<b['end_hz']<=r['measurement']['nyquist_hz'] for b in r['analysis_bands']),'Faixa além de Nyquist')
    return errors
