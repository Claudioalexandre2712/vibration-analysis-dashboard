

import logging
import sys
import warnings

import numpy as np
import pandas as pd
from scipy import signal

from utils import safe_read_csv

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

# Emojis seguros para terminal
def emoji_seguro(emoji, fallback):
    """Retorna emoji somente quando o terminal suporta o encoding atual."""
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    try:
        emoji.encode(encoding)
        return emoji
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        return fallback

# === EMOJIS GLOBAIS ===
EMOJI_DESBALANCEAMENTO = emoji_seguro('🔴', '[!]')     # Vermelho para desbalanceamento
EMOJI_DESALINHAMENTO = emoji_seguro('🔧', '[A]')       # Ferramenta para desalinhamento
EMOJI_FOLGA = emoji_seguro('⚙️', '[F]')                # Engrenagem para folga
EMOJI_EIXO = emoji_seguro('📏', '[E]')                 # Régua para eixo empenado
EMOJI_PISTA_EXTERNA = emoji_seguro('🔴', '[BE]')       # Vermelho para BPFO
EMOJI_PISTA_INTERNA = emoji_seguro('🟠', '[BI]')       # Laranja para BPFI
EMOJI_ELEMENTO_ROLANTE = emoji_seguro('🟡', '[BS]')    # Amarelo para BSF
EMOJI_GAIOLA = emoji_seguro('🟣', '[FT]')              # Roxo para FTF
EMOJI_ELETRICO = emoji_seguro('⚡', '[EL]')            # Raio para falhas elétricas
EMOJI_LUBRIFICACAO = emoji_seguro('🛢️', '[LU]')        # Óleo para lubrificação
EMOJI_ROLAMENTO = emoji_seguro('⚪', '[RO]')            # Círculo branco para rolamento
EMOJI_RESSONANCIA = emoji_seguro('🌊', '[RS]')          # Onda para ressonância
EMOJI_ENGRENAGEM = emoji_seguro('⚙️', '[EN]')           # Engrenagem
EMOJI_NORMAL = emoji_seguro('✅', '[OK]')               # Check verde para normal
EMOJI_ERRO = emoji_seguro('❌', '[!]')                  # X vermelho para erros

def detectar_rpm_hibrido(dados, fs):
    """
    Detecção híbrida de RPM usando FFT e autocorrelação
    """
    # FFT para análise de frequência
    n = len(dados)
    freqs = np.fft.fftfreq(n, 1/fs)
    fft_data = np.fft.fft(dados)
    magnitudes = np.abs(fft_data)
    
    # Considerar apenas frequências positivas e relevantes (0.1 Hz a fs/4)
    mask = (freqs > 0.1) & (freqs < fs/4)
    freqs_pos = freqs[mask]
    mags_pos = magnitudes[mask]
    
    # Verificar se há dados suficientes
    if len(mags_pos) == 0:
        return {"Rotação Calculada (RPM)": 0, "Frequência Fundamental (Hz)": 0, "Justificativa": "Nenhuma frequência válida encontrada"}
    
    # Encontrar picos principais
    peaks, properties = signal.find_peaks(mags_pos, height=np.max(mags_pos)*0.1, distance=int(fs/100))
    
    if len(peaks) == 0:
        return {"Rotação Calculada (RPM)": 0, "Frequência Fundamental (Hz)": 0, "Justificativa": "Nenhum pico detectado"}
    
    # Ordenar picos por magnitude
    peak_freqs = freqs_pos[peaks]
    peak_mags = mags_pos[peaks]
    sorted_indices = np.argsort(peak_mags)[::-1]  # Ordem decrescente de magnitude
    
    # Tentar encontrar a frequência fundamental mais baixa que explica os picos
    # Primeiro, teste se picos principais são submúltiplos uns dos outros
    for i, idx in enumerate(sorted_indices[:5]):  # Considerar os 5 picos mais altos
        freq_candidata = peak_freqs[idx]
        
        # Verificar se esta frequência pode ser um submúltiplo da fundamental
        for divisor in [1, 2, 3, 4, 5]:  # Testar se é 1X, 2X, 3X, 4X, 5X
            freq_fundamental_candidata = freq_candidata / divisor
            if freq_fundamental_candidata < 5:  # Muito baixo
                continue
                
            # Verificar quantos dos picos principais são harmônicos desta fundamental
            harmonicos_encontrados = 0
            for j, idx2 in enumerate(sorted_indices[:8]):  # Verificar top 8 picos
                freq_pico = peak_freqs[idx2]
                # Verificar se este pico é harmônico da fundamental candidata
                for h in range(1, 11):  # 1º ao 10º harmônico
                    freq_harm_esperada = freq_fundamental_candidata * h
                    if (abs(freq_pico - freq_harm_esperada) < 2.0 and  # Tolerância de 2Hz
                        mags_pos[idx2] > np.max(mags_pos) * 0.03):  # Pelo menos 3% do pico máximo
                        harmonicos_encontrados += 1
                        break
            
            # Se encontrou harmônicos suficientes, use esta fundamental
            if harmonicos_encontrados >= 2:
                rpm_candidato = freq_fundamental_candidata * 60
                
                # Classificar confiança
                if harmonicos_encontrados >= 5:
                    confianca = "Confiança Muito Alta"
                elif harmonicos_encontrados >= 3:
                    confianca = "Confiança Alta"
                elif harmonicos_encontrados >= 2:
                    confianca = "Confiança Boa"
                else:
                    confianca = "Confiança Baixa"
                
                justificativa = f"{confianca} ({harmonicos_encontrados} harmônicos)"
                
                return {
                    "Rotação Calculada (RPM)": int(rpm_candidato),
                    "Frequência Fundamental (Hz)": freq_fundamental_candidata,
                    "Justificativa": justificativa
                }
    
    # Fallback para método antigo se não encontrou estrutura harmônica
    if len(mags_pos) == 0:
        return {"Rotação Calculada (RPM)": 1800, "Frequência Fundamental (Hz)": 30.0, "Justificativa": "Fallback - sem dados válidos"}
    
    freq_dominante = freqs_pos[np.argmax(mags_pos)]
    return {
        "Rotação Calculada (RPM)": int(freq_dominante * 60),
        "Frequência Fundamental (Hz)": freq_dominante,
        "Justificativa": f"Pico dominante em {freq_dominante:.1f} Hz (verificar)"
    }
    
    # Fallback: usar o pico mais alto
    if len(mags_pos) == 0:
        return {"Rotação Calculada (RPM)": 1800, "Frequência Fundamental (Hz)": 30.0, "Justificativa": "Fallback final - sem dados"}
    
    freq_dominante = freqs_pos[np.argmax(mags_pos)]
    return {
        "Rotação Calculada (RPM)": int(freq_dominante * 60),
        "Frequência Fundamental (Hz)": freq_dominante,
        "Justificativa": "Baseado no pico dominante - baixa confiança"
    }

def calcular_scores_independentes(f, A, freq_rot):
    """
    Calcula scores independentes para cada tipo de falha
    Retorna um dicionário com scores de 0-100 para cada falha
    """
    scores = {}
    
    # Encontrar índices das frequências principais
    freq_1x_idx = np.argmin(np.abs(f - freq_rot))
    freq_2x_idx = np.argmin(np.abs(f - 2*freq_rot))
    freq_3x_idx = np.argmin(np.abs(f - 3*freq_rot))
    freq_4x_idx = np.argmin(np.abs(f - 4*freq_rot))
    freq_5x_idx = np.argmin(np.abs(f - 5*freq_rot))
    
    # Amplitudes principais
    amp_1x = A[freq_1x_idx] if freq_1x_idx < len(A) else 0
    amp_2x = A[freq_2x_idx] if freq_2x_idx < len(A) else 0
    amp_3x = A[freq_3x_idx] if freq_3x_idx < len(A) else 0
    amp_4x = A[freq_4x_idx] if freq_4x_idx < len(A) else 0
    amp_5x = A[freq_5x_idx] if freq_5x_idx < len(A) else 0
    
    # === SCORE DESBALANCEAMENTO ===
    # Baseado principalmente na amplitude 1X
    score_desbal = 0
    if amp_1x > 0.01:
        score_desbal += min(80 * (amp_1x / 0.2), 80)  # 0-80 pontos pela amplitude 1X
    
    # Penalizar se 2X for muito alto (indica desalinhamento)
    ratio_2x_1x = amp_2x / amp_1x if amp_1x > 0.001 else 0
    if ratio_2x_1x > 0.8:
        score_desbal *= 0.5  # Reduz score se 2X for alto
    if ratio_2x_1x > 2.0:
        score_desbal *= 0.2  # Reduz ainda mais se 2X for dominante
    
    scores['DESBALANCEAMENTO'] = min(score_desbal, 100)
    
    # === SCORE DESALINHAMENTO ===
    # Baseado na amplitude 2X e ratio 2X/1X
    score_desalin = 0
    if amp_2x > 0.005:
        score_desalin += min(60 * (amp_2x / 0.15), 60)  # 0-60 pontos pela amplitude 2X
    
    if ratio_2x_1x > 0.3:  
        score_desalin += min(70 * (ratio_2x_1x / 3.0), 70)  # 0-70 pontos pelo ratio
    
    # Bonus se 2X for claramente dominante
    if ratio_2x_1x > 2.0:
        score_desalin += 20
    
    scores['DESALINHAMENTO'] = min(score_desalin, 100)
    
    # === SCORE FOLGA ===
    # Baseado em múltiplos harmônicos (3X, 4X, 5X)
    score_folga = 0
    harmonicos_altos = 0
    
    for amp_harm in [amp_3x, amp_4x, amp_5x]:
        if amp_harm > 0.01:  # Threshold para harmônicos
            score_folga += min(40 * (amp_harm / 0.1), 40)  # 0-40 pontos por harmônico
            harmonicos_altos += 1
    
    # Verificar se harmônicos são dominantes sobre 1X e 2X
    harmonicos_total = amp_3x + amp_4x + amp_5x
    base_total = amp_1x + amp_2x
    
    if harmonicos_total > base_total and harmonicos_altos >= 2:
        score_folga += 30  # Bonus se harmônicos dominam
    
    # Bonus por múltiplos harmônicos
    if harmonicos_altos >= 2:
        score_folga += 20
    if harmonicos_altos >= 3:
        score_folga += 20
    
    scores['FOLGA'] = min(score_folga, 100)
    
    # === SCORE EIXO EMPENADO ===
    # Baseado na combinação específica de 1X + 2X
    score_eixo = 0
    if amp_1x > 0.05 and amp_2x > 0.02 and 0.3 < ratio_2x_1x < 3.0:
        score_eixo = min(70 * ((amp_1x + amp_2x) / 0.4), 100)
    
    scores['EIXO_EMPENADO'] = score_eixo
    
    # === SCORE ROLAMENTO ===
    # Baseado em picos não-harmônicos em frequências altas
    score_rolamento = 0
    
    # Verificar compatibilidade de tamanhos dos arrays
    if len(f) != len(A):
        logger.warning('Incompatibilidade de tamanhos: f=%s, A=%s', len(f), len(A))
        # Ajustar para o menor tamanho
        min_len = min(len(f), len(A))
        f_safe = f[:min_len]
        A_safe = A[:min_len]
    else:
        f_safe = f
        A_safe = A
    
    # Procurar picos significativos em frequências não-harmônicas > 2.5*freq_rot
    freq_min = freq_rot * 2.5
    freq_max = freq_rot * 10
    
    mask_rolamento = (f_safe >= freq_min) & (f_safe <= freq_max)
    if np.any(mask_rolamento):
        amps_rol = A_safe[mask_rolamento]
        freqs_rol = f_safe[mask_rolamento]
        
        # Encontrar o maior pico não-harmônico
        max_amp_nao_harm = 0
        for i, freq_test in enumerate(freqs_rol):
            is_harmonic = False
            for h in range(1, 11):
                if abs(freq_test - h * freq_rot) < 2:  # ±2Hz tolerância
                    is_harmonic = True
                    break
            
            if not is_harmonic and amps_rol[i] > max_amp_nao_harm:
                max_amp_nao_harm = amps_rol[i]
        
        if max_amp_nao_harm > 0.01:
            score_rolamento = min(80 * (max_amp_nao_harm / 0.05), 100)
    
    scores['ROLAMENTO'] = score_rolamento
    
    # === SCORE RESSONÂNCIA ===
    # Detecção de ressonância baseada em padrões específicos
    score_ressonancia = 0
    
    # Encontrar threshold dinâmico
    if len(A) == 0:
        return {'NORMAL': 0, 'DESBALANCEAMENTO': 0, 'DESALINHAMENTO': 0, 'FOLGA': 0, 'ROLAMENTO': 0, 'RESSONANCIA': 0, 'ELETRICO': 0, 'LUBRIFICACAO': 0}
    
    max_amp_geral = np.max(A) if len(A) > 0 else 1.0
    threshold_dinamico = max(0.01, max_amp_geral * 0.08)  # 8% da amplitude máxima
    
    # CASO ESPECIAL: Ressonância pode coincidir com harmônicos mas ter características distintas
    # Verificar padrão típico de ressonância: 1X alto + pico secundário significativo
    
    # Primeiro, detectar se há um padrão de ressonância estrutural
    # Características: 1X dominante + pico secundário alto em frequência "suspeita"
    
    candidatos_ressonancia = []
    
    # Verificar frequências típicas de ressonância (mesmo que sejam harmônicos)
    frequencias_suspeitas = [120, 150, 180, 200, 240, 300]
    
    for freq_sus in frequencias_suspeitas:
        if freq_sus <= f[-1]:
            idx_sus = np.argmin(np.abs(f - freq_sus))
            amp_sus = A[idx_sus]
            
            # Verificar se a amplitude é significativa
            if amp_sus > threshold_dinamico:
                # Calcular ratio com 1X
                ratio_com_1x = amp_sus / amp_1x if amp_1x > 0.001 else 0
                
                # Critérios para ressonância:
                # 1. Amplitude secundária significativa (>5% da máxima)
                # 2. Ratio com 1X entre 0.3 e 2.0 (não muito baixo, não muito alto)
                if amp_sus > max_amp_geral * 0.05 and 0.3 <= ratio_com_1x <= 2.0:
                    candidatos_ressonancia.append((freq_sus, amp_sus, ratio_com_1x))
    
    # Busca adicional por picos não-harmônicos genuínos
    picos_nao_harmonicos = []
    for i, freq_test in enumerate(f):
        if A[i] > threshold_dinamico and freq_test > 80:
            # Verificar se é genuinamente não-harmônico (tolerância mais restrita)
            is_harmonic = False
            for h in range(1, 8):  # Verificar até 8º harmônico
                if abs(freq_test - h * freq_rot) < 1.5:  # ±1.5Hz tolerância restrita
                    is_harmonic = True
                    break
            
            if not is_harmonic:
                ratio_com_1x = A[i] / amp_1x if amp_1x > 0.001 else 0
                picos_nao_harmonicos.append((freq_test, A[i], ratio_com_1x))
    
    # Calcular score baseado nos candidatos
    todos_candidatos = candidatos_ressonancia + picos_nao_harmonicos
    
    if todos_candidatos:
        # Ordenar por amplitude
        todos_candidatos.sort(key=lambda x: x[1], reverse=True)
        freq_principal, amp_principal, ratio_principal = todos_candidatos[0]
        
        # Score base proporcional à amplitude e ratio
        score_base = min(50 * (amp_principal / max_amp_geral), 50)
        score_ressonancia += score_base
        
        # Bonus baseado no ratio com 1X
        if 0.5 <= ratio_principal <= 1.5:  # Ratio ideal para ressonância
            score_ressonancia += 30
        elif 0.3 <= ratio_principal <= 2.0:  # Ratio aceitável
            score_ressonancia += 15
        
        # Bonus especial para 150Hz (frequência muito comum de ressonância)
        if 148 <= freq_principal <= 152:
            score_ressonancia += 35
        
        # Bonus para outras frequências típicas de ressonância
        for freq_tipica in [120, 180, 200, 240, 300]:
            if abs(freq_principal - freq_tipica) <= 3:
                score_ressonancia += 20
                break
        
        # Bonus se múltiplos candidatos (indica sistema com múltiplas ressonâncias)
        if len(todos_candidatos) >= 2:
            score_ressonancia += 15
        
        # Ajuste final: ressonância tem padrão específico
        # Se 1X é muito dominante comparado ao secundário, pode não ser ressonância clássica
        if amp_1x > amp_principal * 3:
            score_ressonancia *= 0.6  # Reduzir um pouco
    
    scores['RESSONANCIA'] = min(score_ressonancia, 100)
    
    # === SCORE ENGRENAGEM ===
    # Simplificado - baseado em padrões complexos de harmônicos
    score_engrenagem = 0
    
    # Verificar se há energia significativa em múltiplos harmônicos
    harmonicos_energia = amp_1x + amp_2x + amp_3x + amp_4x + amp_5x
    energia_total = np.sum(A)
    
    if energia_total > 0:
        ratio_harmonicos = harmonicos_energia / energia_total
        if ratio_harmonicos > 0.7:  # 70% da energia em harmônicos baixos
            score_engrenagem = min(60 * (harmonicos_energia / 0.5), 100)
    
    scores['ENGRENAGEM'] = score_engrenagem
    
    # === SCORE FALHAS ELÉTRICAS ===
    # Baseado em pico em 2x frequência da rede (120Hz no Brasil) e bandas laterais
    score_eletrico = 0
    freq_rede = 60  # 60Hz no Brasil
    freq_2x_rede = 120  # 2x frequência da rede
    
    # Procurar pico em 120Hz
    idx_120hz = np.argmin(np.abs(f - freq_2x_rede))
    if idx_120hz < len(A):
        amp_120hz = A[idx_120hz]
        if amp_120hz > 0.02:  # Threshold para detecção
            score_eletrico += min(60 * (amp_120hz / 0.08), 60)
    
    # Procurar bandas laterais em torno de 1X RPM (±120Hz)
    freq_banda_inferior = freq_rot - freq_2x_rede
    freq_banda_superior = freq_rot + freq_2x_rede
    
    if freq_banda_inferior > 0:
        idx_banda_inf = np.argmin(np.abs(f - freq_banda_inferior))
        if idx_banda_inf < len(A) and A[idx_banda_inf] > 0.01:
            score_eletrico += 20
    
    if freq_banda_superior < f[-1]:
        idx_banda_sup = np.argmin(np.abs(f - freq_banda_superior))
        if idx_banda_sup < len(A) and A[idx_banda_sup] > 0.01:
            score_eletrico += 20
    
    scores['ELETRICO'] = min(score_eletrico, 100)
    
    # === SCORE PROBLEMAS DE LUBRIFICAÇÃO ===
    # Baseado no aumento do "chão de ruído" em alta frequência
    score_lubrificacao = 0
    
    # Analisar energia em alta frequência (>5x freq_rot)
    freq_alta = freq_rot * 5
    mask_alta_freq = f > freq_alta
    
    if np.any(mask_alta_freq):
        # Calcular energia média em alta frequência
        energia_alta_freq = np.mean(A[mask_alta_freq]**2)
        
        # Calcular energia média em baixa frequência (1x-3x)
        freq_baixa_max = freq_rot * 3
        mask_baixa_freq = (f > freq_rot * 0.5) & (f < freq_baixa_max)
        energia_baixa_freq = np.mean(A[mask_baixa_freq]**2) if np.any(mask_baixa_freq) else 0.001
        
        # Ratio de energia alta/baixa frequência
        ratio_energia = energia_alta_freq / energia_baixa_freq if energia_baixa_freq > 0 else 0
        
        # Score baseado no ratio e na energia absoluta
        if ratio_energia > 0.1:  # Threshold para detecção
            score_lubrificacao += min(70 * (ratio_energia / 2.0), 70)
        
        # Bonus se energia alta for absolutamente significativa
        if energia_alta_freq > 0.001:
            score_lubrificacao += min(30 * (energia_alta_freq / 0.005), 30)
    
    scores['LUBRIFICACAO'] = min(score_lubrificacao, 100)
    
    return scores, {
        'amp_1x': amp_1x, 'amp_2x': amp_2x, 'amp_3x': amp_3x, 
        'amp_4x': amp_4x, 'amp_5x': amp_5x, 'ratio_2x_1x': ratio_2x_1x,
        'amp_120hz': A[idx_120hz] if idx_120hz < len(A) else 0
    }

def diagnosticar_por_scores(f, A, freq_rot, threshold_minimo=15):
    """
    Diagnóstica baseado em scores independentes
    """
    scores, amps = calcular_scores_independentes(f, A, freq_rot)
    diagnosticos = []
    
    # Aplicar threshold mínimo e ordenar por score
    diagnosticos_candidatos = []
    for tipo, score in scores.items():
        if score >= threshold_minimo:
            diagnosticos_candidatos.append((tipo, score))
    
    # Ordenar por score (maior primeiro)
    diagnosticos_candidatos.sort(key=lambda x: x[1], reverse=True)
    
    # Gerar diagnósticos
    for tipo, score in diagnosticos_candidatos:
        if tipo == 'DESBALANCEAMENTO':
            amp_1x = amps['amp_1x']
            if amp_1x > 0.7:
                severidade = "CRÍTICO"
            elif amp_1x > 0.3:
                severidade = "Severo"
            elif amp_1x > 0.1:
                severidade = "Moderado"
            else:
                severidade = "Leve"
            
            diagnosticos.append({
                'titulo': f'{EMOJI_DESBALANCEAMENTO} Desbalanceamento {severidade}',
                'descricao_quantitativa': f'Amplitude 1X: {amp_1x:.3f} m/s² em {freq_rot:.2f} Hz (Score: {score:.0f})',
                'icone': EMOJI_DESBALANCEAMENTO,
                'score': score,
                'sugestao': 'Verificar: balanceamento do rotor, acúmulo de sujeira, corrosão, desgaste irregular'
            })
            
        elif tipo == 'DESALINHAMENTO':
            amp_2x = amps['amp_2x']
            ratio = amps['ratio_2x_1x']
            
            if ratio > 3.0:
                tipo_align = "Angular Severo"
            elif ratio > 1.5:
                tipo_align = "Angular"
            elif ratio > 0.8:
                tipo_align = "Combinado (Angular + Paralelo)"
            else:
                tipo_align = "Paralelo"
                
            if amp_2x > 0.3:
                severidade = "Crítico"
            elif amp_2x > 0.15:
                severidade = "Severo"
            elif amp_2x > 0.05:
                severidade = "Moderado"
            else:
                severidade = "Leve"
            
            diagnosticos.append({
                'titulo': f'{EMOJI_DESALINHAMENTO} Desalinhamento {tipo_align} - {severidade}',
                'descricao_quantitativa': f'2X: {amp_2x:.3f} m/s² ({2*freq_rot:.1f} Hz), Ratio: {ratio:.1f} (Score: {score:.0f})',
                'icone': EMOJI_DESALINHAMENTO,
                'score': score,
                'sugestao': 'Verificar: alinhamento do acoplamento, desgaste de mancais, tensão de correias, nivelamento da base'
            })
            
        elif tipo == 'FOLGA':
            amp_3x, amp_4x, amp_5x = amps['amp_3x'], amps['amp_4x'], amps['amp_5x']
            dominante = max(amp_3x, amp_4x, amp_5x)
            
            if dominante > 0.8:
                severidade = "Crítica"
            elif dominante > 0.3:
                severidade = "Severa"
            elif dominante > 0.1:
                severidade = "Moderada"
            else:
                severidade = "Leve"
            
            diagnosticos.append({
                'titulo': f'{EMOJI_FOLGA} Folga Mecânica {severidade}',
                'descricao_quantitativa': f'Harmônicos: 3X={amp_3x:.3f}, 4X={amp_4x:.3f}, 5X={amp_5x:.3f} (Score: {score:.0f})',
                'icone': EMOJI_FOLGA,
                'score': score,
                'sugestao': 'Verificar: parafusos de fixação, acoplamentos, mancais, folgas em chavetas, base da máquina'
            })
            
        elif tipo == 'EIXO_EMPENADO':
            diagnosticos.append({
                'titulo': f'{EMOJI_EIXO} Eixo Empenado/Flexionado',
                'descricao_quantitativa': f'Padrão 1X+2X: 1X={amps["amp_1x"]:.3f}, 2X={amps["amp_2x"]:.3f} (Score: {score:.0f})',
                'icone': EMOJI_EIXO,
                'score': score,
                'sugestao': 'Verificar: curvatura do eixo, deflexão, mau manuseio durante manutenção, sobrecarga'
            })
            
        elif tipo == 'ROLAMENTO':
            diagnosticos.append({
                'titulo': f'{EMOJI_ROLAMENTO} Problema de Rolamento Detectado',
                'descricao_quantitativa': f'Picos não-harmônicos em altas frequências (Score: {score:.0f})',
                'icone': EMOJI_ROLAMENTO,
                'score': score,
                'sugestao': 'Verificar: lubrificação inadequada, contaminação, fadiga, desgaste, falha de gaiola ou elementos'
            })
            
        elif tipo == 'RESSONANCIA':
            diagnosticos.append({
                'titulo': f'{EMOJI_RESSONANCIA} Possível Ressonância Estrutural',
                'descricao_quantitativa': f'Pico não-harmônico significativo (Score: {score:.0f})',
                'icone': EMOJI_RESSONANCIA,
                'score': score,
                'sugestao': 'Verificar: frequência natural da estrutura, reforço da base, mudança de velocidade operacional'
            })
            
        elif tipo == 'ENGRENAGEM':
            diagnosticos.append({
                'titulo': f'{EMOJI_ENGRENAGEM} Possível Problema em Engrenagens',
                'descricao_quantitativa': f'Padrão harmônico complexo (Score: {score:.0f})',
                'icone': EMOJI_ENGRENAGEM,
                'score': score,
                'sugestao': 'Verificar: desgaste dos dentes, alinhamento, lubrificação, folga entre engrenagens, fadiga'
            })
            
        elif tipo == 'ELETRICO':
            amp_120hz = amps.get('amp_120hz', 0)
            
            if amp_120hz > 0.15:
                severidade = "Crítica"
            elif amp_120hz > 0.08:
                severidade = "Severa"
            elif amp_120hz > 0.04:
                severidade = "Moderada"
            else:
                severidade = "Leve"
            
            diagnosticos.append({
                'titulo': f'{EMOJI_ELETRICO} Falha Elétrica {severidade} (Motor AC)',
                'descricao_quantitativa': f'Pico em 120Hz: {amp_120hz:.3f} m/s², possível problema em barras do rotor ou estator (Score: {score:.0f})',
                'icone': EMOJI_ELETRICO,
                'score': score,
                'sugestao': 'Verificar: barras do rotor quebradas, problemas no estator, conexões elétricas'
            })
            
        elif tipo == 'LUBRIFICACAO':
            # Determinar severidade baseado no score
            if score > 80:
                severidade = "Crítico"
                condicao = "Lubrificação insuficiente ou contaminada"
            elif score > 60:
                severidade = "Severo"
                condicao = "Lubrificação inadequada"
            elif score > 40:
                severidade = "Moderado"
                condicao = "Possível problema de lubrificação"
            else:
                severidade = "Leve"
                condicao = "Lubrificação requer atenção"
            
            diagnosticos.append({
                'titulo': f'{EMOJI_LUBRIFICACAO} Problema de Lubrificação - {severidade}',
                'descricao_quantitativa': f'{condicao}. Aumento do ruído em alta frequência (Score: {score:.0f})',
                'icone': EMOJI_LUBRIFICACAO,
                'score': score,
                'sugestao': 'Verificar: nível de óleo, qualidade do lubrificante, contaminação, intervalos de troca'
            })
    
    # Se nenhum diagnóstico, máquina normal
    if not diagnosticos:
        diagnosticos.append({
            'titulo': f'{EMOJI_NORMAL} Máquina em condição normal',
            'descricao_quantitativa': 'Sem problemas significativos detectados.',
            'icone': EMOJI_NORMAL,
            'score': 0,
            'sugestao': 'Manter rotina de manutenção preventiva e monitoramento periódico'
        })
    
    return diagnosticos

def _extrair_coluna_vibracao(df):
    """Seleciona a melhor coluna de vibração/aceleração de forma robusta."""
    colunas = [str(col).lower() for col in df.columns]

    for i, nome in enumerate(colunas):
        if any(chave in nome for chave in ['vibr', 'acel', 'accel', 'acceler', 'sinal']):
            serie = pd.to_numeric(df.iloc[:, i], errors='coerce').dropna()
            if len(serie) > 0:
                return serie.to_numpy()

    for idx_prioritario in [1, 0]:
        if idx_prioritario < df.shape[1]:
            serie = pd.to_numeric(df.iloc[:, idx_prioritario], errors='coerce').dropna()
            if len(serie) > 0:
                return serie.to_numpy()

    raise ValueError('Nenhuma coluna numérica válida de vibração foi encontrada no CSV.')


def analisar_vibracoes_completo(arquivo_csv, fs=1000, params_rolamento=None):
    """
    Análise completa de vibrações usando o novo sistema de scores
    """
    try:
        # Carregar dados
        if isinstance(arquivo_csv, str):
            df = safe_read_csv(arquivo_csv)
            dados = _extrair_coluna_vibracao(df)
        else:
            dados = np.asarray(arquivo_csv, dtype=float)

        logger.info('Dados carregados: %s amostras, fs=%s Hz', len(dados), fs)
        
        # Detectar RPM
        rpm_info = detectar_rpm_hibrido(dados, fs)
        freq_rot = rpm_info["Frequência Fundamental (Hz)"]
        logger.info('RPM detectado: %s', rpm_info)
        
        if freq_rot <= 0:
            return [{
                'titulo': f'{EMOJI_ERRO} Erro na detecção de RPM',
                'descricao_quantitativa': 'Não foi possível detectar a frequência de rotação.',
                'icone': EMOJI_ERRO
            }]
        
        # Análise espectral
        n = len(dados)
        f = np.fft.fftfreq(n, 1/fs)[:n//2]
        fft_data = np.fft.fft(dados)
        A = 2.0/n * np.abs(fft_data[:n//2])
        
        # Diagnóstico por scores
        diagnosticos = diagnosticar_por_scores(f, A, freq_rot)
        
        return diagnosticos
        
    except Exception as e:
        return [{
            'titulo': f'{EMOJI_ERRO} Erro na análise: {str(e)}',
            'descricao_quantitativa': 'Erro durante o processamento dos dados.',
            'icone': EMOJI_ERRO
        }]

# Função principal compatível com o sistema existente
def analisar_vibracoes(arquivo_csv, fs=1000, params_rolamento=None):
    """Função principal compatível com o sistema existente"""
    return analisar_vibracoes_completo(arquivo_csv, fs, params_rolamento)

# === FUNÇÕES DE COMPATIBILIDADE PARA O APP FLASK ===

def ler_dados_csv(arquivo_csv):
    """Lê dados CSV - função de compatibilidade"""
    df = pd.read_csv(arquivo_csv)
    return df.iloc[:, 0].values  # Primeira coluna

def remover_offset(dados):
    """Remove offset DC dos dados"""
    return dados - np.mean(dados)

def aplicar_janela(dados, tipo='hanning'):
    """Aplica janela aos dados e retorna fator de correção"""
    if tipo == 'hanning':
        janela = np.hanning(len(dados))
        # Fator de correção para janela Hanning
        fator_correcao = 1.0 / np.mean(janela)
    else:
        janela = np.ones(len(dados))
        fator_correcao = 1.0
    
    return dados * janela, fator_correcao

def filtro_passabanda(dados, fs, freq_min, freq_max):
    """Filtro passa-banda simples"""
    from scipy import signal
    sos = signal.butter(4, [freq_min, freq_max], btype='band', fs=fs, output='sos')
    return signal.sosfilt(sos, dados)

def media_sincrona_por_volta(dados, tac, fs, rpm):
    """Média síncrona por volta"""
    # Simplificado - retorna dados originais
    # O parâmetro tac (tacômetro) é aceito mas não usado na versão simplificada
    return dados

def calcular_metricas(dados):
    """Calcula métricas estatísticas"""
    if len(dados) == 0:
        return {'rms': 0.0, 'peak': 0.0, 'kurtosis': 3.0, 'crest_factor': 1.0}
    
    rms_val = np.sqrt(np.mean(dados**2))
    peak_val = np.max(np.abs(dados))
    
    return {
        'rms': rms_val,
        'peak': peak_val,
        'kurtosis': 3.0,  # Simplificado
        'crest_factor': peak_val / rms_val if rms_val > 0 else 1.0
    }

def diagnostico_automatico(dados, fs, rpm_teorico=None):
    """Diagnóstico automático - função de compatibilidade"""
    return analisar_vibracoes(dados, fs)

def envelope_rolamento(dados, fs):
    """Envelope para análise de rolamentos"""
    from scipy import signal
    analytic_signal = signal.hilbert(dados)
    envelope = np.abs(analytic_signal)
    f_env = np.fft.fftfreq(len(envelope), 1/fs)[:len(envelope)//2]
    A_env = 2.0/len(envelope) * np.abs(np.fft.fft(envelope))[:len(envelope)//2]
    return f_env, A_env

def aceleracao_para_velocidade(aceleracao, fs):
    """Converte aceleração para velocidade por integração"""
    # Integração simples no domínio do tempo
    # Para dados de vibração, a velocidade RMS é aproximadamente aceleração RMS / (2*pi*freq)
    # Usando frequência dominante estimada ou valor típico
    freq_dominante = 30  # Hz - frequência típica para máquinas rotativas
    velocidade = aceleracao / (2 * np.pi * freq_dominante)
    return velocidade

def detectar_picos_fft(f, A, altura_min=0.01):
    """Detecta picos na FFT"""
    from scipy import signal
    peaks, _ = signal.find_peaks(A, height=altura_min, distance=5)
    return peaks

def diagnostico_rotacao_automatica(dados, fs):
    """Diagnóstico com detecção automática de rotação"""
    rpm_info = detectar_rpm_hibrido(dados, fs)
    return analisar_vibracoes(dados, fs), rpm_info

def calcular_fft(dados, fs, fator_correcao=1.0):
    """Calcula FFT dos dados com correção de janela"""
    n = len(dados)
    f = np.fft.fftfreq(n, 1/fs)[:n//2]
    fft_data = np.fft.fft(dados)
    A = 2.0/n * np.abs(fft_data[:n//2]) * fator_correcao
    fase = np.angle(fft_data[:n//2])
    return f, A, fase

def classificar_severidade(valor, thresholds):
    """Classifica severidade baseado em thresholds"""
    if valor < thresholds[0]:
        return "Normal"
    elif valor < thresholds[1]:
        return "Leve"
    elif valor < thresholds[2]:
        return "Moderado"
    elif valor < thresholds[3]:
        return "Severo"
    else:
        return "Crítico"

if __name__ == "__main__":
    # Teste rápido
    import os
    arquivos_teste = [
        "001_normal.csv",
        "005_desalin_leve.csv", 
        "008_folga_leve.csv",
        "013_rolamento_leve.csv"
    ]
    
    for arquivo in arquivos_teste:
        if os.path.exists(arquivo):
            print(f"\n=== TESTE: {arquivo} ===")
            resultados = analisar_vibracoes(arquivo)
            for i, diag in enumerate(resultados, 1):
                print(f"{i}. {diag['titulo']}")
                print(f"   {diag['descricao_quantitativa']}")
        else:
            print(f"Arquivo {arquivo} não encontrado")