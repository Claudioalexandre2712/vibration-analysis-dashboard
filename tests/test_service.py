import io
import numpy as np
import pandas as pd
import pytest
from csv_io import load_measurement
from analysis_service import analyze_measurement
from app import create_app


def csv_signal(fs=1000, freq=50):
    t = np.arange(4000)/fs
    return pd.DataFrame({'tempo': t, 'aceleracao': np.sin(2*np.pi*freq*t)}).to_csv(index=False).encode()


def test_sampling_inferred_and_manual_rpm_honored():
    m = load_measurement(csv_signal())
    assert m['fs'] == pytest.approx(1000)
    r = analyze_measurement(m, rpm=3000)
    assert r['rotation']['rpm'] == 3000
    assert r['rotation']['method'] == 'Manual'
    assert r['metrics']['kurtosis'] == pytest.approx(1.5, rel=.01)
    assert r['metrics']['velocity_rms_mm_s'] == pytest.approx(1000/(2*np.pi*50*np.sqrt(2)), rel=.03)
    assert r['bearing_frequencies'] == {}


def test_sampling_conflict_rejected():
    with pytest.raises(ValueError, match='amostragem'):
        load_measurement(csv_signal(), fs=500)


def test_missing_sampling_not_invented():
    data = pd.DataFrame({'aceleracao': np.sin(np.arange(100))}).to_csv(index=False).encode()
    with pytest.raises(ValueError, match='amostragem'):
        load_measurement(data)


@pytest.mark.parametrize('bad', [np.nan, np.inf])
def test_invalid_signal_rejected(bad):
    df = pd.read_csv(io.BytesIO(csv_signal()))
    df.loc[5, 'aceleracao'] = bad
    with pytest.raises(ValueError):
        load_measurement(df.to_csv(index=False).encode())


def test_bearing_geometry_changes_frequencies():
    r = analyze_measurement(load_measurement(csv_signal()), rpm=3000, bearing={'n':8, 'd':8, 'p':40, 'theta':0}, teeth=20)
    assert r['bearing_frequencies']['BPFO'] == pytest.approx(160)
    assert r['bearing_frequencies']['BPFI'] == pytest.approx(240)
    assert r['gear_mesh_hz'] == pytest.approx(1000)
    assert any('Nyquist' in w for w in r['warnings'])


@pytest.fixture
def client():
    return create_app({'TESTING': True}).test_client()


def test_home_and_assets_exist(client):
    assert client.get('/').status_code == 200
    assert client.get('/app.js').status_code == 200
    assert client.get('/app.css').status_code == 200
    assert client.get('/api/health').json['status'] == 'ok'


def test_real_upload(client):
    response = client.post('/api/analyze', data={'arquivo':(io.BytesIO(csv_signal()), 'ensaio.csv'), 'rpm_manual':'3000'})
    assert response.status_code == 200
    r = response.json
    assert r['rotation']['rpm'] == 3000
    assert len(r['plots']['spectrum']['x']) <= 2000
    assert r['filename'] == 'ensaio.csv'


def test_upload_errors_do_not_return_fake_results(client):
    response = client.post('/api/analyze', data={'arquivo':(io.BytesIO(b'no-data'), 'bad.csv')})
    assert response.status_code == 400
    assert 'error' in response.json
    assert 'plots' not in response.json


def test_size_limit_and_no_shared_history(client):
    response = client.post('/api/analyze', data={'arquivo':(io.BytesIO(b'x'*(4*1024*1024+1)), 'large.csv')})
    assert response.status_code == 413
    assert client.post('/limpar_historico').status_code in (404, 405)


def test_examples_are_explicitly_synthetic(client):
    r = client.get('/api/examples/normal')
    assert r.status_code == 200
    assert r.mimetype == 'text/csv'
