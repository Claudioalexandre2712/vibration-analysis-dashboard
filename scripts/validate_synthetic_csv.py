"""Gera CSVs e verifica uploads locais/públicos sem autenticação ou dados pessoais."""
import argparse
import io
import json
from pathlib import Path
import sys
import time
from urllib import request,error
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from synthetic_cases import cases,evaluate
from app import create_app


def multipart(raw,name,fields):
    boundary='vibracoes-test-'+uuid.uuid4().hex
    parts=[]
    for key,value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="arquivo"; filename="{name}.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode(),raw,f'\r\n--{boundary}--\r\n'.encode()])
    return b''.join(parts),'multipart/form-data; boundary='+boundary


def run(target,output):
    output.mkdir(parents=True,exist_ok=True)
    suite=cases();report=[]
    local=create_app({'TESTING':True}).test_client()
    manifest=[]
    for case in suite:
        (output/(case['name']+'.csv')).write_bytes(case['raw'])
        manifest.append({k:v for k,v in case.items() if k!='raw'})
        begin=time.monotonic()
        if target=='local':
            inspect=local.post('/api/inspect',data={'arquivo':(io.BytesIO(case['raw']),case['name']+'.csv')})
            response=local.post('/api/analyze',data={**case['fields'],'arquivo':(io.BytesIO(case['raw']),case['name']+'.csv')})
            status,data,inspect_status=response.status_code,response.json,inspect.status_code
        else:
            def post(endpoint,fields):
                body,content_type=multipart(case['raw'],case['name'],fields)
                req=request.Request(target.rstrip('/')+endpoint,data=body,headers={'Content-Type':content_type},method='POST')
                try:
                    with request.urlopen(req,timeout=90) as response:return response.status,json.load(response)
                except error.HTTPError as exc:return exc.code,json.load(exc)
            inspect_status,_=post('/api/inspect',{})
            status,data=post('/api/analyze',case['fields'])
        errors=evaluate(case,status,data)
        if case['status']==200 and inspect_status!=200:errors.append(f'Inspeção HTTP {inspect_status}')
        entry={'case':case['name'],'ok':not errors,'http':status,'inspect_http':inspect_status,
               'seconds':round(time.monotonic()-begin,3),'errors':errors,'version':data.get('version'),
               'expected':case['expected'],'diagnostics':data.get('diagnostics'),
               'metrics':data.get('metrics'),'rotation':data.get('rotation'),'warnings':data.get('warnings'),
               'bearing_frequencies':data.get('bearing_frequencies'),'error':data.get('error')}
        report.append(entry)
    label='local' if target=='local' else 'publico'
    (output/'manifesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/f'resultados-{label}.json').write_text(json.dumps({'target':target,'cases':report},ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Validação de CSVs sintéticos','',f'Alvo: {target}',f'Aprovados: {sum(r["ok"] for r in report)}/{len(report)}','',
           'Sinais sintéticos verificam cálculos e regras específicas. Não certificam diagnóstico de máquinas reais.',
           'Rolamentos, GMF, alta frequência e pico não harmônico são casos de referência/investigação, sem causa confirmada.',
           'Parâmetros de cada arquivo: manifesto.json. Tempo em segundos; aceleração em m/s² exceto arquivos11(g) e12(mm/s²).',
           'Importante: preencher os parâmetros do manifesto ao reproduzir; RPM, unidade, TSA e geometria alteram o resultado.','',
           '| CSV | HTTP | Resultado | Indícios exibidos / erro |','|---|---:|---|---|']
    for r in report:
        diag='; '.join(d['titulo'] for d in (r['diagnostics'] or [])) or r['error'] or '—'
        lines.append(f'| {r["case"]}.csv | {r["http"]} | {"PASSOU" if r["ok"] else "FALHOU: "+"; ".join(r["errors"])} | {diag} |')
    (output/f'RELATORIO-{label}.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with zipfile.ZipFile(output.parent/'testes-csv-vibracoes.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.iterdir()):
            if path.is_file():archive.write(path,path.name)
    print(json.dumps({'target':target,'passed':sum(r['ok'] for r in report),'total':len(report),
                      'failures':[{'case':r['case'],'errors':r['errors']} for r in report if not r['ok']]},ensure_ascii=False))
    return all(r['ok'] for r in report)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--target',default='local',choices=['local','https://vibration-analysis-dashboard.vercel.app'])
    parser.add_argument('--output',type=Path,default=ROOT.parent/'documentacao'/'testes-csv')
    args=parser.parse_args()
    raise SystemExit(0 if run(args.target,args.output) else 1)
