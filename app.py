from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
import sys
import logging
import threading
import webbrowser
from logging.handlers import RotatingFileHandler
from datetime import datetime
import numpy as np
import pandas as pd
from pathlib import Path
import tempfile
import socket
import flask.cli

from analise_vibracoes import (
    remover_offset, aplicar_janela, filtro_passabanda, media_sincrona_por_volta,
    calcular_metricas, envelope_rolamento, aceleracao_para_velocidade,
    detectar_picos_fft, diagnostico_rotacao_automatica, calcular_fft
)
from config import get_config, ensure_directories

def resource_path(relative_path):
    """Resolve caminho de assets: funciona em dev e no bundle PyInstaller."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)

from utils import (
    sanitize_filename, validate_csv_file, validate_sampling_frequency,
    safe_float, safe_int, get_csv_info
)

from utils import safe_read_csv

config = get_config()
ensure_directories()

app = Flask(
    __name__,
    template_folder=resource_path('templates'),
    static_folder=resource_path('static')
)
app.config.from_object(config)


def get_local_ip():
    """Obtém o IP local da máquina na rede."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except Exception:
        return '127.0.0.1'


def setup_logging():
    """Configura logging em arquivo, sem poluir o terminal."""
    log_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s (%(funcName)s:%(lineno)d): %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(getattr(logging, config.LOG_LEVEL))

    root_logger.setLevel(getattr(logging, config.LOG_LEVEL))
    root_logger.addHandler(file_handler)

    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers.clear()
    werkzeug_logger.propagate = False
    werkzeug_logger.setLevel(logging.ERROR)

    app.logger.handlers.clear()
    app.logger.propagate = True
    app.logger.setLevel(getattr(logging, config.LOG_LEVEL))

setup_logging()

def init_db():
    """Inicializa o banco de dados se não existir"""
    app.logger.info(f'Inicializando banco de dados: {config.DATABASE_PATH}')
    conn = sqlite3.connect(config.DATABASE_PATH)
    cursor = conn.cursor()
    
    # Verifica se a tabela existe e tem a estrutura correta
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='analises_historico'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        # Verifica se as colunas estão corretas
        cursor.execute("PRAGMA table_info(analises_historico)")
        columns = [row[1] for row in cursor.fetchall()]
        required_columns = ['data_hora', 'arquivo_nome', 'rpm', 'rms_velocidade', 'curtose', 'amplitude_1x', 'severidade', 'diagnostico']
        
        if not all(col in columns for col in required_columns):
            # Apaga a tabela antiga e recria
            cursor.execute('DROP TABLE IF EXISTS analises_historico')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analises_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT NOT NULL,
            arquivo_nome TEXT,
            rpm REAL,
            rms_velocidade REAL,
            curtose REAL,
            amplitude_1x REAL,
            severidade TEXT,
            diagnostico TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_data_hora 
        ON analises_historico(data_hora DESC)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_severidade 
        ON analises_historico(severidade)
    ''')
    
    conn.commit()
    conn.close()
    app.logger.info('Banco de dados inicializado com sucesso')

def salvar_no_historico(arquivo_nome, rpm, rms_vel, kurt, amp_1x, severidade, diagnostico):
    """Salva os resultados da análise no histórico"""
    try:
        app.logger.debug(f'Salvando análise no histórico: {arquivo_nome}')
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        
        data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if diagnostico and isinstance(diagnostico, list):
            diag_partes = []
            for item in diagnostico:
                if isinstance(item, dict) and 'titulo' in item:
                    titulo = item['titulo']
                    # Extrair informações mais relevantes
                    if 'frequencia' in item:
                        diag_partes.append(f"{titulo} ({item['frequencia']:.1f} Hz)")
                    else:
                        diag_partes.append(titulo)
            diag_texto = '; '.join(diag_partes) if diag_partes else 'Análise completa'
        else:
            diag_texto = str(diagnostico) if diagnostico else 'Sem diagnóstico específico'
        
        # Limitar o tamanho do diagnóstico
        if len(diag_texto) > 200:
            diag_texto = diag_texto[:197] + "..."
        
        cursor.execute('''
            INSERT INTO analises_historico 
            (data_hora, arquivo_nome, rpm, rms_velocidade, curtose, amplitude_1x, severidade, diagnostico)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data_hora, arquivo_nome, rpm, rms_vel, kurt, amp_1x, severidade, diag_texto))
        
        conn.commit()
        conn.close()
        app.logger.info(f'Análise salva: {arquivo_nome} | Severidade: {severidade} | RPM: {rpm:.0f}')
    except Exception as e:
        app.logger.error(f'Erro ao salvar no histórico: {e}', exc_info=True)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/tendencias', methods=['GET'])
def tendencias():
    """Página de análise de tendências"""
    try:
        app.logger.debug('Acessando página de tendências')
        init_db()
        
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT data_hora, arquivo_nome, rpm, rms_velocidade, curtose, 
                   amplitude_1x, severidade, diagnostico
            FROM analises_historico 
            ORDER BY data_hora DESC
        ''')
        
        dados = cursor.fetchall()
        
        cursor.execute('SELECT COUNT(*) FROM analises_historico')
        total_analises = cursor.fetchone()[0]
        
        estatisticas = {
            'total_analises': total_analises,
            'rms_medio': 0,
            'curtose_media': 0,
            'rpm_medio': 0,
            'distribuicao_severidade': {}
        }
        
        historico = []
        dados_graficos = None
        
        if dados:
            for row in dados:
                historico.append({
                    'data_hora': row[0],
                    'arquivo_nome': row[1],
                    'rpm': row[2],
                    'rms_velocidade': row[3],
                    'curtose': row[4],
                    'amplitude_1x': row[5],
                    'severidade': row[6],
                    'diagnostico': row[7]
                })
            
            rms_values = [h['rms_velocidade'] for h in historico if h['rms_velocidade']]
            curtose_values = [h['curtose'] for h in historico if h['curtose']]
            rpm_values = [h['rpm'] for h in historico if h['rpm']]
            
            if rms_values:
                estatisticas['rms_medio'] = sum(rms_values) / len(rms_values)
            if curtose_values:
                estatisticas['curtose_media'] = sum(curtose_values) / len(curtose_values)
            if rpm_values:
                estatisticas['rpm_medio'] = sum(rpm_values) / len(rpm_values)
            
            # Calcular distribuição por severidade
            severidades = [h['severidade'] for h in historico if h['severidade']]
            for sev in severidades:
                if sev in estatisticas['distribuicao_severidade']:
                    estatisticas['distribuicao_severidade'][sev] += 1
                else:
                    estatisticas['distribuicao_severidade'][sev] = 1
            
            # Preparar dados para gráficos
            if len(historico) > 0:
                # Ordenar por data para gráficos de tendência
                historico_ordenado = sorted(historico, key=lambda x: x['data_hora'])
                timestamps = [h['data_hora'] for h in historico_ordenado]
                dados_graficos = {
                    'timestamps': timestamps,
                    'rms_velocidade': [float(h['rms_velocidade']) if h['rms_velocidade'] else 0 for h in historico_ordenado],
                    'curtose': [float(h['curtose']) if h['curtose'] else 0 for h in historico_ordenado],
                    'amplitude_1x': [float(h['amplitude_1x']) if h['amplitude_1x'] else 0 for h in historico_ordenado],
                    'rpm': [float(h['rpm']) if h['rpm'] else 0 for h in historico_ordenado]
                }
        
        conn.close()
        
        app.logger.info(f'Tendências carregadas: {len(historico)} análises no histórico')
        
        return render_template('tendencias.html', 
                             historico=historico, 
                             estatisticas=estatisticas,
                             dados_graficos=dados_graficos)
        
    except Exception as e:
        app.logger.error(f'Erro ao carregar tendências: {e}', exc_info=True)
        flash(f'Erro ao carregar tendências: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/limpar_historico', methods=['POST'])
def limpar_historico():
    """Limpa todo o histórico de análises"""
    try:
        app.logger.warning('AÇÃO: Limpeza do histórico solicitada')
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        
        # Contar registros antes de deletar
        cursor.execute('SELECT COUNT(*) FROM analises_historico')
        count = cursor.fetchone()[0]
        
        cursor.execute('DELETE FROM analises_historico')
        conn.commit()
        conn.close()
        
        app.logger.info(f'Histórico limpo: {count} registros removidos')
        flash('Histórico limpo com sucesso! 🗑️ Todos os dados foram removidos.', 'success')
    except Exception as e:
        app.logger.error(f'Erro ao limpar histórico: {e}', exc_info=True)
        flash(f'Erro ao limpar histórico: {str(e)}', 'danger')
    
    # Forçar recriação do banco após limpeza
    init_db()
    return redirect(url_for('tendencias'))

@app.route('/upload', methods=['POST'])
def upload():
    temp_path = None
    try:
        app.logger.info('Nova requisição de upload recebida')
        
        # Validar arquivo
        file = request.files.get('arquivo')
        if not file or not file.filename:
            app.logger.warning('Upload rejeitado: nenhum arquivo enviado')
            flash('Nenhum arquivo enviado. Por favor, selecione um arquivo CSV.', 'danger')
            return redirect(url_for('index'))
        
        # Sanitizar nome do arquivo
        try:
            arquivo_nome_original = file.filename
            arquivo_nome = sanitize_filename(arquivo_nome_original)
            app.logger.info(f'Arquivo recebido: "{arquivo_nome_original}" → "{arquivo_nome}"')
        except ValueError as e:
            app.logger.error(f'Nome de arquivo inválido: {e}')
            flash(f'Nome de arquivo inválido: {str(e)}', 'danger')
            return redirect(url_for('index'))
        
        # Validar extensão
        if not arquivo_nome.lower().endswith('.csv'):
            app.logger.warning(f'Upload rejeitado: extensão inválida ({arquivo_nome})')
            flash('Apenas arquivos CSV (.csv) são permitidos.', 'danger')
            return redirect(url_for('index'))
        
        # Salvar temporariamente com nome seguro
        temp_dir = Path(config.TEMP_FOLDER)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        with tempfile.NamedTemporaryFile(
            mode='wb', 
            delete=False, 
            suffix='.csv',
            dir=temp_dir,
            prefix='upload_'
        ) as temp_file:
            # Garantir que o ponteiro do stream volte ao início antes de salvar
            try:
                if hasattr(file, 'stream'):
                    file.stream.seek(0)
                elif hasattr(file, 'seek'):
                    file.seek(0)
            except Exception:
                # Não falhar se o seek não for suportado
                app.logger.debug('Não foi possível dar seek no stream do arquivo (não suportado).')

            file.save(temp_file.name)
            temp_path = temp_file.name
            app.logger.debug(f'Arquivo salvo temporariamente: {temp_path}')
        
        # Validação robusta do CSV
        is_valid, error_msg = validate_csv_file(
            temp_path, 
            min_rows=config.MIN_DATA_POINTS,
            max_size_mb=config.MAX_CONTENT_LENGTH // (1024 * 1024)
        )
        
        if not is_valid:
            app.logger.warning(f'Validação CSV falhou: {error_msg}')
            flash(f'❌ Arquivo inválido: {error_msg}', 'danger')
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            return redirect(url_for('index'))
        
        csv_info = get_csv_info(temp_path)
        app.logger.info(
            f'CSV válido: {csv_info["rows"]} linhas, '
            f'{csv_info["columns"]} colunas, {csv_info["size_formatted"]}'
        )
        
       
        from analise_vibracoes import analisar_vibracoes_completo
        
        fs_fornecida = safe_float(request.form.get('sampling_frequency'), 0)
        
        if fs_fornecida > 0:
            is_valid_fs, fs_error = validate_sampling_frequency(
                fs_fornecida,
                min_fs=0.1,
                max_fs=config.MAX_SAMPLING_FREQUENCY
            )
            if not is_valid_fs:
                app.logger.warning(f'Frequência inválida: {fs_error}')
                flash(f'❌ {fs_error}', 'danger')
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                return redirect(url_for('index'))
            fs_calculado = fs_fornecida
        else:
            fs_calculado = config.DEFAULT_SAMPLING_FREQUENCY
        
        app.logger.info(f'Frequência de amostragem: {fs_calculado} Hz')
        
        # Parâmetros do usuário
        rpm_manual = request.form.get('rpm_manual', '').strip()
        n = safe_int(request.form.get('n'), 8)
        d = safe_float(request.form.get('d'), 8.0)
        p = safe_float(request.form.get('p'), 40.0)
        theta = safe_float(request.form.get('theta'), 15.0)
        num_dentes = safe_int(request.form.get('num_dentes'), 0)
        
        app.logger.debug(
            f'Parâmetros: n={n}, d={d}, p={p}, theta={theta}, '
            f'num_dentes={num_dentes}'
        )
        
        # Iniciar processamento
        app.logger.info(f'Iniciando análise de vibrações: {arquivo_nome}')

        try:
            # Carrega e processa os dados reais
            # Log útil para diagnosticar uploads que geram arquivos vazios
            try:
                if not temp_path or not os.path.exists(temp_path):
                    raise ValueError('Arquivo temporário não encontrado antes da leitura')
                size_bytes = os.path.getsize(temp_path)
                app.logger.debug(f'Temp file path={temp_path} size={size_bytes} bytes')
                try:
                    with open(temp_path, 'rb') as _f:
                        head = _f.read(512)
                        app.logger.debug(f'First bytes (utf-8 replace): {head.decode("utf-8", "replace")[:200]!s}')
                except Exception as _e:
                    app.logger.debug(f'Não foi possível ler os primeiros bytes do arquivo: {_e}')

                df = safe_read_csv(temp_path)
            except ValueError as ve:
                raise ValueError(str(ve))
            except Exception as e:
                raise ValueError(f'Erro ao ler CSV: {e}')

            # Detecção inteligente de colunas baseada nos nomes
            colunas = [col.lower() for col in df.columns]
            app.logger.debug(f'Colunas detectadas: {df.columns.tolist()}')

            # Procurar por colunas específicas por nome
            col_tempo = None
            col_acel = None
            col_tac = None

            for i, col in enumerate(colunas):
                if 'tempo' in col or 'time' in col:
                    col_tempo = i
                elif 'vibracao' in col or 'aceleracao' in col or 'acceleration' in col or 'vibration' in col:
                    col_acel = i
                elif 'frequencia' in col or 'frequency' in col or 'tac' in col:
                    col_tac = i

            # Aplicar detecção inteligente ou fallback para posição
            if col_tempo is not None and col_acel is not None:
                app.logger.debug(f'Usando detecção por nome: tempo=col{col_tempo}, acel=col{col_acel}')
                tempo_raw = df.iloc[:, col_tempo].values
                acel_raw = df.iloc[:, col_acel].values
                tac = df.iloc[:, col_tac].values if col_tac is not None else None
            elif df.shape[1] >= 3:
                # Fallback tradicional para compatibilidade
                tempo_raw = df.iloc[:, 0].values
                acel_raw = df.iloc[:, 1].values
                tac = df.iloc[:, 2].values
                app.logger.debug('Usando fallback por posição: col0=tempo, col1=acel, col2=tac')
            elif df.shape[1] == 2:
                tempo_raw = df.iloc[:, 0].values
                acel_raw = df.iloc[:, 1].values
                tac = None
                app.logger.debug('Duas colunas: col0=tempo, col1=acel')
            else:
                # Apenas uma coluna - assumir que é aceleração
                acel_raw = df.iloc[:, 0].values
                tempo_raw = np.arange(len(acel_raw)) / fs_calculado
                tac = None
                app.logger.debug('Uma coluna: col0=acel, tempo calculado')

            # Validar dados antes do processamento
            app.logger.info(f'Dados carregados: {len(acel_raw)} pontos')
            app.logger.debug(f'Range aceleração: {np.min(acel_raw):.4f} a {np.max(acel_raw):.4f}')
            app.logger.debug(f'Std aceleração: {np.std(acel_raw):.4f}')

            # Verificar se há dados suficientes e válidos
            if len(acel_raw) < 50:
                raise ValueError(f"Dados insuficientes: apenas {len(acel_raw)} pontos (mínimo 50)")

            if np.std(acel_raw) < 1e-6:
                raise ValueError("Sinal muito uniforme - possível problema nos dados")

            if np.any(np.isnan(acel_raw)) or np.any(np.isinf(acel_raw)):
                raise ValueError("Dados contêm valores inválidos (NaN ou infinito)")

            # Processa o sinal
            acel_filt = remover_offset(acel_raw)
            acel_filt, fator_correcao = aplicar_janela(acel_filt, 'hanning')
            acel_filt = filtro_passabanda(acel_filt, fs_calculado, 0.1, fs_calculado/2-1)

            # FFT dos dados brutos
            f_fft_raw, A_fft_raw, fase_fft_raw = calcular_fft(acel_filt, fs_calculado, fator_correcao)

            # Detecção de RPM
            diag_temp, rot_info = diagnostico_rotacao_automatica(acel_filt, fs_calculado)
            # Acesso seguro ao RPM
            if isinstance(rot_info, dict):
                rpm = rot_info.get('RPM Detectado', rot_info.get('Rotação Calculada (RPM)', 1800))
            else:
                rpm = 1800  # Fallback seguro
            metodo_rpm = 'Automático'

            # Processamento avançado
            env_freq, env_A = envelope_rolamento(acel_filt, fs_calculado)
            acel_proc = media_sincrona_por_volta(acel_filt, tac, fs_calculado, rpm)
            f_fft_proc, A_fft_proc, fase_fft_proc = calcular_fft(acel_proc, fs_calculado, fator_correcao)

            # Métricas do sinal
            metricas = calcular_metricas(acel_proc)
            rms = metricas['rms']
            cf = metricas['crest_factor']
            kurt = metricas['kurtosis']
            skewn = 0.0  # Não implementado na versão simplificada

            # Velocidade e severidade
            vel = aceleracao_para_velocidade(acel_proc, fs_calculado)
            rms_vel = np.sqrt(np.mean(vel**2))
            rms_vel_mm_s = rms_vel * 1000
            # Classificação de severidade
            if rms_vel_mm_s < 2.8:
                severidade = 'Normal'
                cor_severidade = 'bg-success'
            elif rms_vel_mm_s < 7.1:
                severidade = 'Leve'
                cor_severidade = 'bg-warning'
            elif rms_vel_mm_s < 18.0:
                severidade = 'Moderado'
                cor_severidade = 'bg-danger'
            else:
                severidade = 'Severo'
                cor_severidade = 'bg-danger'

            # Picos da FFT
            try:
                fft_peaks_indices = detectar_picos_fft(f_fft_proc, A_fft_proc)
                if isinstance(fft_peaks_indices, np.ndarray) and len(fft_peaks_indices) > 0:
                    fft_peaks_x = f_fft_proc[fft_peaks_indices]
                    fft_peaks_y = A_fft_proc[fft_peaks_indices]
                else:
                    fft_peaks_x = [0]
                    fft_peaks_y = [0]
            except Exception:
                fft_peaks_x = [0]
                fft_peaks_y = [0]

            # RMS móvel
            janela = min(100, len(acel_proc)//10)
            s = pd.Series(acel_proc)
            rms_rolling = s.rolling(janela).apply(lambda x: np.sqrt(np.mean(x**2)), raw=True).fillna(rms).values

            # Amplitude 1X
            freq_rot = rpm / 60.0
            try:
                idx_1x = np.argmin(np.abs(f_fft_proc - freq_rot))
                amp_1x = A_fft_proc[idx_1x]
                fase_1x = float(fase_fft_proc[idx_1x])
            except Exception:
                amp_1x = np.max(A_fft_proc) if len(A_fft_proc) > 0 else 1.0
                fase_1x = 0.0

            # Diagnóstico completo
            diag = analisar_vibracoes_completo(
                temp_path,
                fs=fs_calculado,
                params_rolamento={'n': n, 'd': d, 'p': p, 'theta': theta, 'num_dentes': num_dentes}
            )

            # Dados gráficos com dados REAIS
            dados_graficos = {
                'tempo_raw': {'x': list(tempo_raw), 'y': list(acel_filt)},
                'fft_raw': {'x': list(f_fft_raw), 'y': list(A_fft_raw)},
                'tempo_proc': {'x': list(tempo_raw), 'y': list(acel_proc)},
                'fft_proc': {'x': list(f_fft_proc), 'y': list(A_fft_proc)},
                'envelope': {'x': list(env_freq), 'y': list(env_A)},
                'fft_peaks_x': list(fft_peaks_x),
                'fft_peaks_y': list(fft_peaks_y),
                'rms_x': list(range(len(rms_rolling))),
                'rms_y': list(rms_rolling),
                'polar_1x': {'amplitude': amp_1x, 'fase': fase_1x, 'label': '1X'},
                'rpm': rpm
            }
            
        except Exception as e:
            app.logger.error(f'Erro no processamento dos dados: {e}', exc_info=True)
            # Fallback mínimo
            diag = [{'titulo': '⚠️ Erro no processamento', 'descricao_quantitativa': f'Erro: {str(e)}', 'icone': '⚠️', 'score': 1}]
            rpm = 1800
            metodo_rpm = 'Erro'
            rms = cf = kurt = skewn = 0.0
            severidade = 'Desconhecido'
            cor_severidade = 'bg-warning'
            rms_vel_mm_s = 0.0
            amp_1x = 0.0
            
            # Dados mínimos realistas para evitar erro no template
            # Criar um sinal sintético básico para demonstração quando há erro
            t_demo = np.linspace(0, 1, 100)
            signal_demo = 0.1 * np.sin(2 * np.pi * 30 * t_demo) + 0.05 * np.random.randn(100)
            f_demo = np.linspace(0, fs_calculado/2, 50)
            A_demo = 0.05 * np.exp(-f_demo/100) + 0.01 * np.random.randn(50)
            
            dados_graficos = {
                'tempo_raw': {'x': list(t_demo), 'y': list(signal_demo)},
                'fft_raw': {'x': list(f_demo), 'y': list(np.abs(A_demo))},
                'tempo_proc': {'x': list(t_demo), 'y': list(signal_demo * 0.8)},
                'fft_proc': {'x': list(f_demo), 'y': list(np.abs(A_demo) * 0.8)},
                'envelope': {'x': list(f_demo), 'y': list(np.abs(A_demo) * 0.3)},
                'fft_peaks_x': [30, 60],
                'fft_peaks_y': [0.02, 0.01],
                'rms_x': list(range(10)),
                'rms_y': [0.1 + 0.02 * np.random.randn() for _ in range(10)],
                'polar_1x': {'amplitude': 0.05, 'fase': 45, 'label': '1X'},
                'rpm': rpm
            }
        
        # Salva no histórico
        salvar_no_historico(arquivo_nome, rpm, rms_vel_mm_s, kurt, amp_1x, severidade, diag)
        
        app.logger.debug(f'Dados preparados para template: gráficos={dados_graficos is not None}, diagnóstico={diag is not None}')
        app.logger.info(f'✅ Análise concluída com sucesso: {arquivo_nome}')
        
        # Remove arquivo temporário
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                app.logger.debug(f'Arquivo temporário removido: {temp_path}')
            except Exception as e:
                app.logger.warning(f'Não foi possível remover arquivo temporário: {e}')
        
        return render_template('index.html', 
                             dados_graficos=dados_graficos, 
                             rms=rms, cf=cf, kurt=kurt, skewn=skewn, 
                             diagnostico=diag, fs=fs_calculado, rpm=rpm,
                             metodo_rpm=metodo_rpm, num_dentes=num_dentes, 
                             severidade=severidade, cor_severidade=cor_severidade, 
                             rms_vel_mm_s=rms_vel_mm_s)
                
    except Exception as e:
        # Tratamento de erros robusto com logging detalhado
        app.logger.error(
            f'Erro crítico durante processamento do upload',
            exc_info=True,
            extra={
                'arquivo': locals().get('arquivo_nome', 'Desconhecido'),
                'temp_path': locals().get('temp_path'),
            }
        )
        
        # Limpar arquivo temporário em caso de erro
        temp_path_local = locals().get('temp_path')
        if temp_path_local and os.path.exists(temp_path_local):
            try:
                os.unlink(temp_path_local)
                app.logger.debug('Arquivo temporário removido após erro')
            except Exception as cleanup_error:
                app.logger.warning(f'Erro ao limpar arquivo temporário: {cleanup_error}')
        
        # Mensagem de erro amigável baseada no tipo de erro
        if "could not convert string to float" in str(e).lower():
            error_msg = "O arquivo contém dados não numéricos. Verifique se todas as colunas contêm apenas números."
        elif "list index out of range" in str(e).lower():
            error_msg = "Formato de arquivo inválido. Certifique-se de que o CSV tem pelo menos 2 colunas (tempo e aceleração)."
        elif "empty" in str(e).lower():
            error_msg = "O arquivo está vazio ou não contém dados válidos para análise."
        elif "memory" in str(e).lower():
            error_msg = "Arquivo muito grande para processamento. Tente com um arquivo menor (máximo 50MB)."
        else:
            error_msg = f"Erro durante processamento: {str(e)}"
        
        flash(f'❌ Erro: {error_msg}', 'danger')
        return redirect(url_for('index'))

if __name__ == '__main__':
    try:
        init_db()

        url = f'http://127.0.0.1:{config.PORT}'
        local_ip = get_local_ip()

        print(f'URL: {url}')
        if local_ip != '127.0.0.1':
            print(f'REDE: http://{local_ip}:{config.PORT}')

        flask.cli.show_server_banner = lambda *args, **kwargs: None

        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

        app.run(
            debug=config.DEBUG,
            host=config.HOST,
            port=config.PORT,
            use_reloader=False
        )
    except Exception as e:
        app.logger.critical(f'Falha ao iniciar aplicação: {e}', exc_info=True)
        raise
