from pathlib import Path
import numpy as np
import pytest
from csv_io import load_measurement
from analysis_service import analyze_measurement

FILES = sorted((Path(__file__).parent/'fixtures').glob('*.csv'))


@pytest.mark.parametrize('file',FILES,ids=lambda file:file.name)
def test_original_samples_produce_finite_consistent_results(file):
    m=load_measurement(file.read_bytes())
    r=analyze_measurement(m,rpm=3000)
    assert r['measurement']['samples']==2000
    assert r['measurement']['fs']==pytest.approx(999.5)
    assert r['rotation']['rpm']==3000
    assert all(np.isfinite(v) for v in r['metrics'].values() if v is not None)
    assert r['metrics']['velocity_rms_mm_s']>0
    assert len(r['plots']['spectrum']['x'])==len(r['plots']['spectrum']['y'])
