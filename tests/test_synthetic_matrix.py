import io
import pytest
from app import create_app
from synthetic_cases import cases,evaluate


@pytest.mark.parametrize('case',cases(),ids=lambda c:c['name'])
def test_synthetic_csv_upload_contract(case):
    response=create_app({'TESTING':True}).test_client().post('/api/analyze',data={
        **case['fields'],'arquivo':(io.BytesIO(case['raw']),case['name']+'.csv')})
    assert not (errors:=evaluate(case,response.status_code,response.json)), '\n'.join(errors)
