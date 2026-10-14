import io
import numpy as np
import pytest
from analise_vibracoes import (
    calcular_metricas, calcular_fft, aceleracao_para_velocidade,
    detectar_rpm_hibrido, media_sincrona_por_volta,
)
from utils import safe_read_csv, validate_sampling_frequency


def test_semicolon_decimal_csv():
    df = safe_read_csv(io.StringIO('tempo;aceleracao\n0,0;1,2\n0,1;2,3\n'))
    assert df.shape == (2, 2)
    assert float(df.iloc[0, 1]) == pytest.approx(1.2)


def test_headerless_csv_keeps_first_sample():
    df = safe_read_csv(io.StringIO('0,1\n1,2\n2,3\n'))
    assert len(df) == 3
    assert df.iloc[0, 1] == 1


@pytest.mark.parametrize('fs', [np.nan, np.inf, -1, 0])
def test_invalid_fs(fs):
    assert not validate_sampling_frequency(fs)[0]


def test_sine_metrics_are_measured():
    t = np.arange(2000)/1000
    result = calcular_metricas(np.sin(2*np.pi*50*t))
    assert result['rms'] == pytest.approx(1/np.sqrt(2), rel=1e-4)
    assert result['kurtosis'] == pytest.approx(1.5, rel=1e-3)
    assert abs(result['skewness']) < 1e-6


def test_impulse_kurtosis():
    x = np.zeros(1000)
    x[500] = 1
    assert calcular_metricas(x)['kurtosis'] > 100


def test_velocity_uses_frequency_and_fs():
    t = np.arange(4000)/1000
    a = np.sin(2*np.pi*50*t)
    v = aceleracao_para_velocidade(a, 1000)
    assert np.sqrt(np.mean(v*v)) == pytest.approx(1/(2*np.pi*50*np.sqrt(2)), rel=.02)


def test_fft_dc_not_doubled_and_includes_nyquist():
    f, a, _ = calcular_fft(np.ones(1000)*2, 1000)
    assert a[0] == pytest.approx(2)
    assert f[-1] == pytest.approx(500)


def test_rpm_low_fs_does_not_crash():
    t = np.arange(1000)/50
    r = detectar_rpm_hibrido(np.sin(2*np.pi*5*t), 50)
    assert r['Rotação Calculada (RPM)'] == pytest.approx(300, abs=3)


def test_rpm_recovers_fundamental_when_second_harmonic_dominates():
    t = np.arange(4000)/1000
    x = .2*np.sin(2*np.pi*25*t) + np.sin(2*np.pi*50*t) + .15*np.sin(2*np.pi*75*t)
    r = detectar_rpm_hibrido(x, 1000)
    assert r['Rotação Calculada (RPM)'] == pytest.approx(1500, abs=10)


def test_tsa_averages_revolutions():
    rng = np.random.default_rng(10)
    t = np.arange(10000)/1000
    base = np.sin(2*np.pi*25*t)
    noisy = base + .8*rng.normal(size=len(t))
    result = media_sincrona_por_volta(noisy, None, 1000, 1500)
    assert result.shape == noisy.shape
    assert np.std(result-base) < np.std(noisy-base)*.3
