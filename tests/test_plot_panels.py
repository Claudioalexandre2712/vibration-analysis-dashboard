import numpy as np
import pytest
from analysis_service import analyze_measurement


def measurement(x, fs=1000):
    return {'signal':x,'time':np.arange(len(x))/fs,'fs':fs,'warnings':[],'fs_source':'Informada','tachometer':None}


def test_raw_and_processed_fft_are_distinct_real_signals():
    t=np.arange(2000)/1000
    r=analyze_measurement(measurement(5+np.sin(2*np.pi*50*t)),rpm=3000)
    assert r['plots']['raw_spectrum']['y'][0]==pytest.approx(5)
    assert r['plots']['processed_spectrum']['y'][0]<1e-10
    assert r['plots']['raw']['y'][0]==pytest.approx(5)
    assert r['plots']['processed']['y'][0]==pytest.approx(0,abs=1e-10)


def test_processed_fft_and_peak_markers_use_tsa_output():
    t=np.arange(4000)/1000
    x=np.sin(2*np.pi*50*t)+.5*np.sin(2*np.pi*73*t)
    r=analyze_measurement(measurement(x),rpm=3000,tsa=True)
    raw=r['plots']['raw_spectrum'];processed=r['plots']['processed_spectrum']
    at=lambda data,f: data['y'][int(np.argmin(abs(np.array(data['x'])-f)))]
    assert at(raw,73)>.45
    assert at(processed,73)<.05
    assert any(abs(p['hz']-50)<1 for p in r['processed_peaks'])


def test_rolling_rms_has_time_axis_and_measured_values():
    t=np.arange(2000)/1000
    x=np.sin(2*np.pi*50*t)*np.where(t<1,1,2)
    r=analyze_measurement(measurement(x),rpm=3000)
    curve=r['plots']['rolling_rms']
    assert curve['x'][0]==pytest.approx(.099)
    assert curve['x'][-1]==pytest.approx(1.999)
    assert curve['y'][0]==pytest.approx(1/np.sqrt(2))
    assert curve['y'][-1]==pytest.approx(np.sqrt(2))


def test_frequency_bands_clipped_to_nyquist_and_not_invented():
    t=np.arange(2000)/1000
    r=analyze_measurement(measurement(np.sin(2*np.pi*50*t)),rpm=3000)
    assert r['analysis_bands']
    assert all(0<=b['start_hz']<b['end_hz']<=500 for b in r['analysis_bands'])
    assert not any(b['kind'] in ('gear','bearing') for b in r['analysis_bands'])


def test_health_classification_requires_explicit_reference():
    t=np.arange(2000)/1000
    m=measurement(.1*np.sin(2*np.pi*50*t))
    assert analyze_measurement(m,rpm=3000)['severity']['level']=='unclassified'
    assert analyze_measurement(m,rpm=3000,health_reference=True)['severity']['label']=='Normal'
    assert 'orientativa' in analyze_measurement(m,rpm=3000,health_reference=True)['severity']['description']


def test_rolling_rms_recovers_after_extreme_impact():
    t=np.arange(10000)/1000
    x=np.sin(2*np.pi*50*t); x[:2]=[1e8,-1e8]
    r=analyze_measurement(measurement(x),rpm=3000)
    assert r['plots']['rolling_rms']['y'][-1]==pytest.approx(1/np.sqrt(2),rel=1e-6)


def test_polar_evaluates_exact_rotation_frequency():
    t=np.arange(2000)/1000
    r=analyze_measurement(measurement(np.cos(2*np.pi*25.25*t)),rpm=1515)
    assert r['metrics']['amplitude_1x']==pytest.approx(1,abs=1e-8)
    assert r['metrics']['phase_1x_deg']==pytest.approx(0,abs=1e-8)


def test_velocity_band_without_resolved_bins_is_rejected():
    x=np.sin(2*np.pi*50*np.arange(50)/1000)
    with pytest.raises(ValueError,match='resolução'):
        analyze_measurement(measurement(x),rpm=3000,velocity_min=10,velocity_max=15,health_reference=True)


def test_didactic_regions_follow_rotation_and_keep_unmeasured_regions_explicit():
    t=np.arange(2000)/1000
    r=analyze_measurement(measurement(np.sin(2*np.pi*50*t)),rpm=3000)
    regions=r['spectral_regions']
    assert [(b['start_hz'],b['end_hz']) for b in regions[:3]]==[(40,60),(90,160),(150,500)]
    assert regions[3]['label']=='Rolamentos' and regions[3]['end_hz']==5000
    assert regions[4]['label']=='Lubrificação' and regions[4]['end_hz'] is None
    assert not regions[3]['observable'] and not regions[4]['observable']
    high=analyze_measurement(measurement(np.sin(2*np.pi*50*np.arange(4000)/4000),fs=4000),rpm=1800)
    assert high['spectral_regions'][0]['start_hz']==24
    assert high['spectral_regions'][3]['observable']
    assert high['spectral_regions'][3]['observed_end_hz']==2000
