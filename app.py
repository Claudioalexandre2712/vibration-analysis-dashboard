"""Aplicação pública sem banco global e sem escrita no diretório do bundle."""
import io
from pathlib import Path
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException
from utils import sanitize_filename
from csv_io import inspect_csv, load_measurement
from analysis_service import analyze_measurement, VERSION

MAX_FILE = 4*1024*1024
BASE = Path(__file__).resolve().parent


def create_app(test_config=None):
    application = Flask(__name__,static_folder='public',static_url_path='',template_folder='templates')
    application.config.update(MAX_CONTENT_LENGTH=MAX_FILE+64*1024,MAX_FORM_MEMORY_SIZE=128*1024,MAX_FORM_PARTS=30,DEBUG=False)
    if test_config:
        application.config.update(test_config)

    @application.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['X-Frame-Options']='DENY'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        return response

    @application.get('/')
    @application.get('/tendencias')
    def index():
        return render_template('index.html',version=VERSION)

    @application.get('/api/health')
    def health():
        return jsonify(status='ok',version=VERSION)

    def read_file():
        upload = request.files.get('arquivo')
        if not upload or not upload.filename:
            raise ValueError('Selecione um arquivo CSV.')
        if not upload.filename.lower().endswith('.csv'):
            raise ValueError('Envie um arquivo com extensão .csv.')
        data=upload.read(MAX_FILE+1)
        if len(data)>MAX_FILE:
            from werkzeug.exceptions import RequestEntityTooLarge
            raise RequestEntityTooLarge()
        return data,sanitize_filename(upload.filename)

    def number(key,default=None):
        raw = request.form.get(key,'').strip()
        if not raw:
            return default
        try:
            value=float(raw.replace(',','.'))
            if not np.isfinite(value):
                raise ValueError()
            return value
        except ValueError:
            raise ValueError(f'Valor numérico inválido: {key}.') from None

    @application.post('/api/inspect')
    def inspect():
        data,name=read_file()
        _,info=inspect_csv(data)
        return jsonify(**info,filename=name)

    @application.post('/api/analyze')
    @application.post('/upload')
    def analyze():
        data,name=read_file()
        m=load_measurement(data,fs=number('sampling_frequency'),signal_column=request.form.get('signal_column'),time_column=request.form.get('time_column'),tach_column=request.form.get('tach_column'),unit=request.form.get('unit','m/s2'))
        geometry={k:number(k) for k in ['n','d','p','theta']}
        if any(v is not None for v in geometry.values()):
            if not all(v is not None for v in geometry.values()):
                raise ValueError('Preencha todos os quatro parâmetros de rolamento ou deixe todos vazios.')
        else:
            geometry=None
        result=analyze_measurement(m,rpm=number('rpm_manual'),bearing=geometry,teeth=number('num_dentes',0),tsa=request.form.get('tsa')=='on',velocity_min=number('velocity_min',10),velocity_max=number('velocity_max',1000))
        result['filename']=name
        result['machine']=request.form.get('machine','').strip()[:120]
        return jsonify(result)

    @application.get('/api/examples/<kind>')
    def examples(kind):
        if kind not in ['normal','harmonicos','impactos']:
            return jsonify(error='Exemplo não encontrado.'),404
        rng=np.random.default_rng(42)
        fs=2000
        t=np.arange(8000)/fs
        x=.01*np.sin(2*np.pi*30*t)+.001*rng.standard_normal(len(t))
        if kind=='harmonicos':
            x+=.3*np.sin(2*np.pi*30*t)+.2*np.sin(2*np.pi*60*t)+.1*np.sin(2*np.pi*90*t)
        if kind=='impactos':
            x+=.03*rng.standard_normal(len(t))
            for start in range(0,len(t),180):
                n=min(100,len(t)-start)
                k=np.arange(n)/fs
                x[start:start+n]+=.5*np.exp(-80*k)*np.sin(2*np.pi*600*k)
        raw=pd.DataFrame({'tempo_s':t,'aceleracao_m_s2':x}).to_csv(index=False).encode()
        return send_file(io.BytesIO(raw),mimetype='text/csv',download_name=f'sintetico_{kind}.csv',as_attachment=True)

    @application.errorhandler(ValueError)
    def bad_input(exc):
        return jsonify(error=str(exc)),400

    @application.errorhandler(HTTPException)
    def http_error(exc):
        if exc.code==413:
            return jsonify(error='Arquivo grande demais. O limite desta versão é 4 MB.'),413
        if request.path.startswith('/api/'):
            return jsonify(error=exc.description),exc.code
        return exc

    @application.errorhandler(Exception)
    def internal_error(exc):
        application.logger.error('Falha interna no processamento: %s',type(exc).__name__)
        return jsonify(error='Não foi possível concluir o processamento. Confira os dados e tente novamente.'),500

    return application


app=create_app()

if __name__=='__main__':
    app.run(host='127.0.0.1',port=5000,debug=False)
