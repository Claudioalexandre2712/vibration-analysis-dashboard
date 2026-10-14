import io
import numpy as np
import pytest
from utils import safe_read_csv
from analise_vibracoes import calcular_fft, aplicar_janela, diagnosticar_por_scores
from app import create_app
from analysis_service import analyze_measurement


def test_csv_extra_fields_cannot_become_implicit_index():
    text='tempo,aceleracao\n'+'\n'.join(f'{i/1000},{i/500},{np.sin(i)}' for i in range(100))
    with pytest.raises(ValueError):
        safe_read_csv(io.StringIO(text))


def test_whitespace_duplicate_headers_return_400():
    data=('acel, acel \n'+'\n'.join(f'{np.sin(i)},{np.cos(i)}' for i in range(100))).encode()
    response=create_app({'TESTING':True}).test_client().post('/api/inspect',data={'arquivo':(io.BytesIO(data),'test.csv')})
    assert response.status_code == 400


def test_short_sine_does_not_fabricate_unresolved_harmonics():
    x=np.sin(2*np.pi*120*np.arange(50)/2000)
    w,g=aplicar_janela(x)
    f,a,_=calcular_fft(w,2000,g)
    diagnoses=diagnosticar_por_scores(f,a,20)
    assert not any(d['tipo'] in ('DESBALANCEAMENTO','DESALINHAMENTO','FOLGA') for d in diagnoses)


def test_manual_rpm_is_also_tsa_reference_when_tachometer_disagrees():
    t=np.arange(10000)/1000
    x=np.sin(2*np.pi*25*t)
    tac=(np.sin(2*np.pi*10*t)>0).astype(float)
    m={'signal':x,'time':t,'fs':1000,'warnings':[],'fs_source':'Informada','tachometer':tac}
    r=analyze_measurement(m,rpm=1500,tsa=True)
    assert r['rotation']['rpm'] == 1500
    assert np.std(r['plots']['processed']['y']) > .5
