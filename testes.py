#!/usr/bin/env python3
"""
Sistema de Testes Completo para Análise de Vibrações
Combina testes sintéticos e validação do sistema
Versão consolidada e otimizada
"""

import numpy as np
import pandas as pd
import os
import sys
from pathlib import Path
from analise_vibracoes import analisar_vibracoes

# === CONFIGURAÇÕES DE TESTE ===
RESULTADOS_ESPERADOS = {
    # Arquivos gerados pela bateria de testes (principais)
    "001_normal.csv": ["NORMAL"],
    "002_desbalanceamento.csv": ["DESBALANCEAMENTO"],
    "003_desalinhamento.csv": ["DESALINHAMENTO"],
    "004_folga_mecanica.csv": ["FOLGA"],
    "005_defeito_rolamento.csv": ["ROLAMENTO"],
    "006_ressonancia_150hz.csv": ["RESSONANCIA"],
    "007_falha_eletrica.csv": ["ELETRICO"],
    "008_problema_lubrificacao.csv": ["LUBRIFICACAO"],
    
    # Arquivos de teste adicionais (se existirem)
    "002_desbal_leve.csv": ["DESBALANCEAMENTO"],
    "003_desbal_moderado.csv": ["DESBALANCEAMENTO"],
    "004_desbal_severo.csv": ["DESBALANCEAMENTO"],
    "005_desalin_leve.csv": ["DESALINHAMENTO"],
    "006_desalin_moderado.csv": ["DESALINHAMENTO"],
    "007_desalin_severo.csv": ["DESALINHAMENTO"],
    "008_folga_leve.csv": ["FOLGA"],
    "009_folga_moderada.csv": ["FOLGA"],
    "010_folga_severa.csv": ["FOLGA"],
    "011_eixo_empenado_leve.csv": ["EIXO_EMPENADO"],
    "012_eixo_empenado_severo.csv": ["EIXO_EMPENADO"],
    "013_rolamento_leve.csv": ["ROLAMENTO"],
    "014_rolamento_moderado.csv": ["ROLAMENTO"],
    "015_rolamento_severo.csv": ["ROLAMENTO"],
    "016_engrenagem_leve.csv": ["ENGRENAGEM"],
    "017_engrenagem_severa.csv": ["ENGRENAGEM"],
    "018_ressonancia_150hz.csv": ["RESSONANCIA"],
    "019_ressonancia_300hz.csv": ["RESSONANCIA"],
    "020_desbal_desalin.csv": ["DESBALANCEAMENTO", "DESALINHAMENTO"],
    "021_desbal_folga.csv": ["DESBALANCEAMENTO", "FOLGA"],
    "022_desalin_folga.csv": ["DESALINHAMENTO", "FOLGA"],
    "023_desbal_rolamento.csv": ["DESBALANCEAMENTO", "ROLAMENTO"],
    "024_desalin_rolamento.csv": ["DESALINHAMENTO", "ROLAMENTO"],
    "025_folga_rolamento.csv": ["FOLGA", "ROLAMENTO"],
    "026_desbal_engrenagem.csv": ["DESBALANCEAMENTO", "ENGRENAGEM"],
    "027_desbal_desalin_folga.csv": ["DESBALANCEAMENTO", "DESALINHAMENTO", "FOLGA"],
    "028_desbal_desalin_rolamento.csv": ["DESBALANCEAMENTO", "DESALINHAMENTO", "ROLAMENTO"],
    "029_multiplos_defeitos.csv": ["DESBALANCEAMENTO", "DESALINHAMENTO", "FOLGA", "ROLAMENTO"],
    "030_ruido_alto.csv": ["DESBALANCEAMENTO", "DESALINHAMENTO", "FOLGA", "ROLAMENTO"],
    "031_ruido_muito_alto.csv": ["DESBALANCEAMENTO", "DESALINHAMENTO", "FOLGA", "ROLAMENTO"],
    "032_desbal_muito_leve.csv": ["DESBALANCEAMENTO", "NORMAL"],
    "033_desalin_muito_leve.csv": ["DESALINHAMENTO", "NORMAL"],
    "034_harmonicos_altos.csv": ["DESBALANCEAMENTO", "DESALINHAMENTO", "FOLGA"],
    "035_rpm_baixo.csv": ["DESBALANCEAMENTO", "NORMAL"],
    "036_rpm_alto.csv": ["DESBALANCEAMENTO", "NORMAL"]
}

def gerar_dados_sinteticos():
    """Gera dados sintéticos para diferentes tipos de falhas"""
    fs = 1000
    t = np.linspace(0, 2, 2000)  # 2 segundos
    freq_rot = 50  # 50 Hz = 3000 RPM
    
    dados_teste = {}
    
    # 1. Condição normal (apenas ruído baixo + 1X muito pequeno)
    normal = 0.001 * np.random.randn(len(t)) + 0.002 * np.sin(2*np.pi*freq_rot*t)
    dados_teste['NORMAL'] = normal
    
    # 2. Desbalanceamento (1X dominante)
    desbal = 0.2 * np.sin(2*np.pi*freq_rot*t) + 0.01 * np.random.randn(len(t))
    dados_teste['DESBALANCEAMENTO'] = desbal
    
    # 3. Desalinhamento (1X dominante + 2X significativo)
    desalin = 0.18 * np.sin(2*np.pi*freq_rot*t) + 0.15 * np.sin(2*np.pi*2*freq_rot*t) + 0.01 * np.random.randn(len(t))
    dados_teste['DESALINHAMENTO'] = desalin
    
    # 4. Folga (1X dominante + múltiplos harmônicos altos)
    folga = (0.15 * np.sin(2*np.pi*freq_rot*t) + 
             0.03 * np.sin(2*np.pi*2*freq_rot*t) + 
             0.08 * np.sin(2*np.pi*3*freq_rot*t) + 
             0.12 * np.sin(2*np.pi*4*freq_rot*t) + 
             0.10 * np.sin(2*np.pi*5*freq_rot*t) + 
             0.01 * np.random.randn(len(t)))
    dados_teste['FOLGA'] = folga
    
    # 5. Rolamento (1X baixo + pico não-harmônico alto)
    rolamento = (0.03 * np.sin(2*np.pi*freq_rot*t) + 
                0.08 * np.sin(2*np.pi*347*t) +  # Frequência não-harmônica
                0.01 * np.random.randn(len(t)))
    dados_teste['ROLAMENTO'] = rolamento
    
    # 6. Ressonância (1X dominante + pico não-harmônico em 150Hz)
    ressonancia = (0.18 * np.sin(2*np.pi*freq_rot*t) +   # 1X dominante
                  0.15 * np.sin(2*np.pi*150*t) +         # Ressonância em 150Hz
                  0.01 * np.random.randn(len(t)))
    dados_teste['RESSONANCIA'] = ressonancia
    
    # 7. Falha Elétrica (1X baixo + pico forte em 120Hz)
    eletrico = (0.05 * np.sin(2*np.pi*freq_rot*t) +      # 1X baixo
                0.10 * np.sin(2*np.pi*120*t) +           # Pico em 120Hz (2x freq da rede)
                0.01 * np.random.randn(len(t)))
    dados_teste['ELETRICO'] = eletrico
    
    # 8. Problema de Lubrificação (1X baixo + ruído alto em alta frequência)
    lubrificacao = 0.03 * np.sin(2*np.pi*freq_rot*t)  # 1X baixo
    # Adicionar ruído significativo em alta frequência para simular atrito
    ruido_alta_freq = np.zeros_like(t)
    for freq_alta in [250, 300, 350, 400, 450, 500]:
        ruido_alta_freq += 0.08 * np.random.randn(len(t)) * np.sin(2*np.pi*freq_alta*t)
    lubrificacao += ruido_alta_freq + 0.01 * np.random.randn(len(t))
    dados_teste['LUBRIFICACAO'] = lubrificacao
    
    return dados_teste, fs

def extrair_tipos_diagnosticos(diagnosticos):
    """Extrai os tipos de diagnósticos dos resultados"""
    tipos = []
    for diag in diagnosticos:
        titulo = diag['titulo']
        if 'normal' in titulo.lower():
            tipos.append('NORMAL')
        elif 'Desbalanceamento' in titulo:
            tipos.append('DESBALANCEAMENTO')
        elif 'Desalinhamento' in titulo:
            tipos.append('DESALINHAMENTO')
        elif 'Folga' in titulo:
            tipos.append('FOLGA')
        elif 'Eixo Empenado' in titulo:
            tipos.append('EIXO_EMPENADO')
        elif 'Rolamento' in titulo:
            tipos.append('ROLAMENTO')
        elif 'Ressonância' in titulo:
            tipos.append('RESSONANCIA') 
        elif 'Engrenagem' in titulo:
            tipos.append('ENGRENAGEM')
        else:
            tipos.append('OUTRO')
    
    return tipos

def validar_resultado(esperado, encontrado):
    """Valida se o resultado está correto (permite detecções adicionais)"""
    # Para casos que incluem NORMAL, aceitar tanto detecções quanto normal
    if 'NORMAL' in esperado:
        if len(encontrado) == 1 and encontrado[0] == 'NORMAL':
            return True
        # Ou se detectou os outros tipos esperados
        outros_esperados = [e for e in esperado if e != 'NORMAL']
        if outros_esperados and all(e in encontrado for e in outros_esperados):
            return True
        return False
    
    # Para outros casos, deve conter todos os tipos esperados
    return all(e in encontrado for e in esperado)

def testar_dados_sinteticos():
    """Testa o sistema com dados sintéticos"""
    print("TESTE COM DADOS SINTETICOS")
    print("="*60)
    
    dados_teste, fs = gerar_dados_sinteticos()
    
    acertos = 0
    total = 0
    
    for tipo_esperado, dados in dados_teste.items():
        print(f"\nTESTANDO: {tipo_esperado}")
        print("-" * 40)
        
        try:
            # Análise
            resultados = analisar_vibracoes(dados, fs)
            
            # Mostrar resultados
            tipos_detectados = []
            for i, diag in enumerate(resultados, 1):
                score_info = f" (Score: {diag.get('score', 0):.0f})" if 'score' in diag else ""
                print(f"{i}. {diag['titulo']}{score_info}")
                
                # Extrair tipo
                titulo = diag['titulo']
                if 'normal' in titulo.lower():
                    tipos_detectados.append('NORMAL')
                elif 'Desbalanceamento' in titulo:
                    tipos_detectados.append('DESBALANCEAMENTO')
                elif 'Desalinhamento' in titulo:
                    tipos_detectados.append('DESALINHAMENTO')
                elif 'Folga' in titulo:
                    tipos_detectados.append('FOLGA')
                elif 'Rolamento' in titulo:
                    tipos_detectados.append('ROLAMENTO')
                elif 'Ressonância' in titulo:
                    tipos_detectados.append('RESSONANCIA')
                elif 'Elétrica' in titulo:
                    tipos_detectados.append('ELETRICO')
                elif 'Lubrificação' in titulo:
                    tipos_detectados.append('LUBRIFICACAO')
                else:
                    tipos_detectados.append('OUTRO')
            
            # Validação
            print(f"Esperado: {tipo_esperado}")
            print(f"Detectado: {tipos_detectados}")
            
            if tipo_esperado in tipos_detectados:
                print("CORRETO")
                acertos += 1
            else:
                print("INCORRETO")
            
            total += 1
            
        except Exception as e:
            print(f"ERRO: {e}")
            total += 1
    
    return acertos, total

def testar_arquivos_csv():
    """Testa o sistema com arquivos CSV se disponíveis"""
    print("\nTESTE COM ARQUIVOS CSV")
    print("="*60)
    
    arquivos_encontrados = []
    for arquivo in RESULTADOS_ESPERADOS.keys():
        if os.path.exists(arquivo):
            arquivos_encontrados.append(arquivo)
    
    if not arquivos_encontrados:
        print("Nenhum arquivo CSV encontrado para teste")
        return 0, 0
    
    print(f"Encontrados {len(arquivos_encontrados)} arquivos CSV")
    
    acertos = 0
    total = 0
    
    for arquivo in arquivos_encontrados[:5]:  # Testar apenas os primeiros 5
        print(f"\nTESTANDO: {arquivo}")
        print("-" * 40)
        
        try:
            # Análise
            resultados = analisar_vibracoes(arquivo)
            
            # Mostrar resultados resumidos
            tipos_detectados = extrair_tipos_diagnosticos(resultados)
            esperado = RESULTADOS_ESPERADOS[arquivo]
            
            print(f"Esperado: {esperado}")
            print(f"Detectado: {tipos_detectados}")
            
            if validar_resultado(esperado, tipos_detectados):
                print("CORRETO")
                acertos += 1
            else:
                print("INCORRETO")
            
            total += 1
            
        except Exception as e:
            print(f"ERRO: {e}")
            total += 1
    
    return acertos, total

def debug_caso_especifico(dados, fs, nome="Caso"):
    """Debug detalhado de um caso específico"""
    print(f"\nDEBUG DETALHADO: {nome}")
    print("="*50)
    
    try:
        resultados = analisar_vibracoes(dados, fs)
        
        print(f"Diagnósticos encontrados: {len(resultados)}")
        
        for i, diag in enumerate(resultados, 1):
            print(f"\n{i}. {diag['titulo']}")
            print(f"   {diag['descricao_quantitativa']}")
            if 'score' in diag:
                print(f"   Score: {diag['score']:.1f}")
            if 'sugestao' in diag:
                print(f"   {diag['sugestao']}")
                
    except Exception as e:
        print(f"ERRO: {e}")
        import traceback
        traceback.print_exc()

def salvar_relatorio(acertos_sint, total_sint, acertos_csv, total_csv):
    """Salva relatório de testes em arquivo"""
    timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    arquivo_relatorio = f"relatorio_testes_{timestamp}.txt"
    
    try:
        with open(arquivo_relatorio, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("RELATÓRIO DE TESTES - SISTEMA DE ANÁLISE DE VIBRAÇÕES\n")
            f.write("="*60 + "\n")
            f.write(f"Data/Hora: {pd.Timestamp.now()}\n\n")
            
            f.write("RESULTADOS:\n")
            f.write(f"- Testes Sintéticos: {acertos_sint}/{total_sint} ({(acertos_sint/total_sint)*100:.1f}%)\n")
            if total_csv > 0:
                f.write(f"- Testes CSV: {acertos_csv}/{total_csv} ({(acertos_csv/total_csv)*100:.1f}%)\n")
            
            total_geral = total_sint + total_csv
            acertos_geral = acertos_sint + acertos_csv
            if total_geral > 0:
                f.write(f"- RESULTADO GERAL: {acertos_geral}/{total_geral} ({(acertos_geral/total_geral)*100:.1f}%)\n\n")
                
                if (acertos_geral/total_geral) >= 0.8:
                    f.write("STATUS: SISTEMA APROVADO!\n")
                elif (acertos_geral/total_geral) >= 0.6:
                    f.write("STATUS: Sistema funcional\n")
                else:
                    f.write("STATUS: Precisa melhorar\n")
        
        print(f"\nRelatório salvo em: {arquivo_relatorio}")
        return arquivo_relatorio
        
    except Exception as e:
        print(f"Erro ao salvar relatório: {e}")
        return None

def gerar_bateria_csv():
    """Gera uma bateria completa de arquivos CSV para todos os tipos de defeitos"""
    print("\nGERANDO BATERIA DE ARQUIVOS CSV")
    print("="*60)
    
    dados_teste, fs = gerar_dados_sinteticos()
    arquivos_gerados = []
    
    # Mapeamento de nomes para arquivos CSV
    nomes_arquivos = {
        'NORMAL': '001_normal.csv',
        'DESBALANCEAMENTO': '002_desbalanceamento.csv',
        'DESALINHAMENTO': '003_desalinhamento.csv',
        'FOLGA': '004_folga_mecanica.csv',
        'ROLAMENTO': '005_defeito_rolamento.csv',
        'RESSONANCIA': '006_ressonancia_150hz.csv',
        'ELETRICO': '007_falha_eletrica.csv',
        'LUBRIFICACAO': '008_problema_lubrificacao.csv'
    }
    
    try:
        for tipo_defeito, dados in dados_teste.items():
            nome_arquivo = nomes_arquivos[tipo_defeito]
            
            # Criar DataFrame com metadados
            df = pd.DataFrame({
                'Vibracao_m_s2': dados,
                'Tempo_s': np.linspace(0, 2, len(dados)),
                'Frequencia_Hz': [fs] * len(dados)
            })
            
            # Salvar CSV
            df.to_csv(nome_arquivo, index=False)
            arquivos_gerados.append(nome_arquivo)
            print(f"✅ {nome_arquivo} - {tipo_defeito}")
        
        print(f"\n🎉 {len(arquivos_gerados)} arquivos CSV gerados com sucesso!")
        print("\n📁 ARQUIVOS GERADOS:")
        for arquivo in arquivos_gerados:
            print(f"   • {arquivo}")
            
        print("\n💡 COMO USAR:")
        print("1. Abra o sistema web (app.py ou executável)")
        print("2. Faça upload dos arquivos CSV")
        print("3. Compare os resultados com os testes sintéticos")
        print("4. Use 'python testes.py --csv' para validação automática")
        
        return arquivos_gerados
        
    except Exception as e:
        print(f"❌ Erro ao gerar arquivos CSV: {e}")
        return []

def menu_interativo():
    """Menu interativo para escolher tipo de teste"""
    while True:
        print("\n" + "="*60)
        print("SISTEMA DE TESTES - ANALISE DE VIBRACOES")
        print("="*60)
        print("1. Teste com dados sinteticos")
        print("2. Teste com arquivos CSV")
        print("3. Debug caso especifico")
        print("4. Relatorio completo")
        print("5. Gerar bateria de arquivos CSV")
        print("6. Sair")
        print("="*60)
        
        escolha = input("Escolha uma opção (1-6): ").strip()
        
        if escolha == "1":
            acertos, total = testar_dados_sinteticos()
            if total > 0:
                print(f"\nRESULTADO SINTETICOS: {acertos}/{total} ({(acertos/total)*100:.1f}%)")
        
        elif escolha == "2":
            acertos, total = testar_arquivos_csv()
            if total > 0:
                print(f"\nRESULTADO CSV: {acertos}/{total} ({(acertos/total)*100:.1f}%)")
        
        elif escolha == "3":
            print("\nEscolha o tipo de dados para debug:")
            print("1. Desbalanceamento")
            print("2. Desalinhamento") 
            print("3. Folga")
            print("4. Rolamento")
            print("5. Ressonância")
            print("6. Elétrico")
            print("7. Lubrificação")
            sub_escolha = input("Opção (1-7): ").strip()
            
            dados_teste, fs = gerar_dados_sinteticos()
            tipos = ['DESBALANCEAMENTO', 'DESALINHAMENTO', 'FOLGA', 'ROLAMENTO', 'RESSONANCIA', 'ELETRICO', 'LUBRIFICACAO']
            
            if sub_escolha in ['1', '2', '3', '4', '5', '6', '7']:
                tipo = tipos[int(sub_escolha)-1]
                debug_caso_especifico(dados_teste[tipo], fs, tipo)
        
        elif escolha == "4":
            print("\nEXECUTANDO RELATORIO COMPLETO...")
            acertos_sint, total_sint = testar_dados_sinteticos()
            acertos_csv, total_csv = testar_arquivos_csv()
            
            print(f"\n{'='*60}")
            print("RELATORIO FINAL CONSOLIDADO")
            print(f"{'='*60}")
            print(f"Testes Sinteticos: {acertos_sint}/{total_sint} ({(acertos_sint/total_sint)*100:.1f}%)")
            if total_csv > 0:
                print(f"Testes CSV: {acertos_csv}/{total_csv} ({(acertos_csv/total_csv)*100:.1f}%)")
            
            total_geral = total_sint + total_csv
            acertos_geral = acertos_sint + acertos_csv
            if total_geral > 0:
                print(f"RESULTADO GERAL: {acertos_geral}/{total_geral} ({(acertos_geral/total_geral)*100:.1f}%)")
                
                if (acertos_geral/total_geral) >= 0.8:
                    print("SISTEMA APROVADO!")
                elif (acertos_geral/total_geral) >= 0.6:
                    print("Sistema funcional")
                else:
                    print("Precisa melhorar")
                
                # Salvar relatório em arquivo
                salvar_relatorio(acertos_sint, total_sint, acertos_csv, total_csv)
        
        elif escolha == "5":
            arquivos = gerar_bateria_csv()
            if arquivos:
                print(f"\n🎉 Bateria de {len(arquivos)} arquivos CSV criada!")
                print("Agora você pode testar com a opção 2 ou no sistema web.")
        
        elif escolha == "6":
            print("Saindo do sistema de testes...")
            break
        
        else:
            print("Opção inválida!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Modo linha de comando
        if sys.argv[1] == "--sintetico":
            acertos, total = testar_dados_sinteticos()
            print(f"\nRESULTADO: {acertos}/{total} ({(acertos/total)*100:.1f}%)")
        elif sys.argv[1] == "--csv":
            acertos, total = testar_arquivos_csv()
            print(f"\nRESULTADO: {acertos}/{total} ({(acertos/total)*100:.1f}%)")
        elif sys.argv[1] == "--gerar-csv":
            arquivos = gerar_bateria_csv()
            print(f"\n🎉 {len(arquivos)} arquivos CSV gerados com sucesso!")
        elif sys.argv[1] == "--completo":
            acertos_sint, total_sint = testar_dados_sinteticos()
            acertos_csv, total_csv = testar_arquivos_csv()
            total_geral = total_sint + total_csv
            acertos_geral = acertos_sint + acertos_csv
            print(f"\nRESULTADO GERAL: {acertos_geral}/{total_geral} ({(acertos_geral/total_geral)*100:.1f}%)")
            
            # Salvar relatório automaticamente
            salvar_relatorio(acertos_sint, total_sint, acertos_csv, total_csv)
        elif sys.argv[1] == "--completo-com-csv":
            print("GERANDO ARQUIVOS CSV...")
            arquivos = gerar_bateria_csv()
            print(f"\n✅ {len(arquivos)} arquivos CSV gerados!")
            
            print("\nEXECUTANDO TESTES COMPLETOS...")
            acertos_sint, total_sint = testar_dados_sinteticos()
            acertos_csv, total_csv = testar_arquivos_csv()
            total_geral = total_sint + total_csv
            acertos_geral = acertos_sint + acertos_csv
            print(f"\nRESULTADO GERAL: {acertos_geral}/{total_geral} ({(acertos_geral/total_geral)*100:.1f}%)")
            
            # Salvar relatório automaticamente
            salvar_relatorio(acertos_sint, total_sint, acertos_csv, total_csv)
        else:
            print("Uso: python testes.py [--sintetico|--csv|--gerar-csv|--completo|--completo-com-csv]")
    else:
        # Modo interativo
        menu_interativo()