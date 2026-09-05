import re
import os
import logging
from typing import Optional, Tuple
import pandas as pd
import numpy as np


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitiza nome de arquivo para prevenir ataques de path traversal
    
    Args:
        filename: Nome original do arquivo
        max_length: Tamanho máximo permitido
    
    Returns:
        Nome de arquivo seguro
    
    Raises:
        ValueError: Se o nome for inválido ou vazio
    """
    if not filename:
        raise ValueError("Nome de arquivo vazio")
    
    # Extrair apenas o nome do arquivo (remover qualquer path)
    filename = os.path.basename(filename)
    
    # Remover caracteres perigosos, manter apenas: a-z, A-Z, 0-9, ., _, -
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    
    # Remover múltiplos underscores consecutivos
    safe_name = re.sub(r'_+', '_', safe_name)
    
    # Remover .. (tentativas de path traversal)
    safe_name = safe_name.replace('..', '')
    
    # Limitar tamanho
    if len(safe_name) > max_length:
        # Manter extensão
        name, ext = os.path.splitext(safe_name)
        safe_name = name[:max_length - len(ext)] + ext
    
    # Garantir que não comece com . ou -
    safe_name = safe_name.lstrip('.-')
    
    if not safe_name:
        raise ValueError("Nome de arquivo inválido após sanitização")
    
    return safe_name


def validate_csv_file(file_path: str, min_rows: int = 50, max_size_mb: int = 50) -> Tuple[bool, Optional[str]]:
    """
    Valida arquivo CSV de forma robusta
    
    Args:
        file_path: Caminho do arquivo
        min_rows: Mínimo de linhas necessárias
        max_size_mb: Tamanho máximo em MB
    
    Returns:
        Tupla (valido: bool, mensagem_erro: str ou None)
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 1. Verificar existência
        if not os.path.exists(file_path):
            return False, "Arquivo não encontrado"
        
        # 2. Verificar tamanho
        file_size = os.path.getsize(file_path)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if file_size == 0:
            return False, "Arquivo vazio"
        
        if file_size > max_size_bytes:
            return False, f"Arquivo muito grande ({file_size / 1024 / 1024:.1f}MB). Máximo: {max_size_mb}MB"
        
        # 3. Tentar ler como CSV (safe_read_csv suporta decimais europeus e múltiplos encodings)
        try:
            df = safe_read_csv(file_path, nrows=100)
        except pd.errors.EmptyDataError:
            return False, "Arquivo CSV vazio ou sem dados"
        except pd.errors.ParserError as e:
            return False, f"Erro ao parsear CSV: {str(e)}"
        except ValueError as e:
            return False, f"Arquivo inválido: {str(e)}"
        except Exception as e:
            return False, f"Erro ao ler arquivo: {str(e)}"
        
        # 4. Verificar estrutura básica
        if df.shape[0] < min(min_rows, 10):  # Pelo menos 10 linhas nas primeiras 100
            return False, f"Dados insuficientes (mínimo: {min_rows} linhas)"
        
        if df.shape[1] < 1:
            return False, "CSV deve ter pelo menos 1 coluna de dados"
        
        # 5. Verificar se há dados numéricos
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if len(numeric_cols) == 0:
            # Tentar converter primeira coluna
            try:
                pd.to_numeric(df.iloc[:, 0], errors='coerce')
            except Exception:
                return False, "Nenhuma coluna numérica detectada. Verifique o formato do arquivo"
        
        # 6. Verificar valores inválidos (apenas colunas numéricas com dados parciais)
        for col in df.columns:
            try:
                if pd.api.types.is_numeric_dtype(df[col]):
                    valid_ratio = df[col].notna().sum() / len(df[col])
                    if 0 < valid_ratio < 0.5:
                        logger.warning(f"Coluna '{col}' tem {valid_ratio*100:.1f}% de dados válidos")
            except Exception:
                pass

        # 7. Verificar variância — percorre TODAS as colunas numéricas
        # (a 1ª coluna pode ser timestamp constante, como X_Value do NI LabVIEW)
        try:
            tem_variancia = False
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    col_data = df[col].dropna()
                    if len(col_data) > 1 and col_data.std() > 1e-10:
                        tem_variancia = True
                        break
            if not tem_variancia:
                return False, "Sinal muito uniforme - possível problema nos dados"
        except Exception as e:
            logger.warning(f"Não foi possível verificar variância: {e}")
        
        logger.info(f"CSV validado: {df.shape[0]} linhas, {df.shape[1]} colunas")
        return True, None
        
    except Exception as e:
        logger.error(f"Erro inesperado na validação: {e}", exc_info=True)
        return False, f"Erro na validação: {str(e)}"


def validate_sampling_frequency(fs: float, min_fs: float = 0.1, max_fs: float = 1000000.0) -> Tuple[bool, Optional[str]]:
    """
    Valida frequência de amostragem
    
    Args:
        fs: Frequência de amostragem
        min_fs: Frequência mínima permitida
        max_fs: Frequência máxima permitida
    
    Returns:
        Tupla (valido: bool, mensagem_erro: str ou None)
    """
    try:
        fs_val = float(fs)
        
        if fs_val <= 0:
            return False, "Frequência de amostragem deve ser positiva"
        
        if fs_val < min_fs:
            return False, f"Frequência muito baixa (mínimo: {min_fs} Hz)"
        
        if fs_val > max_fs:
            return False, f"Frequência muito alta (máximo: {max_fs} Hz)"
        
        return True, None
        
    except (ValueError, TypeError):
        return False, "Frequência de amostragem inválida"


def safe_float(value, default: float = 0.0) -> float:
    """
    Converte valor para float de forma segura
    
    Args:
        value: Valor a converter
        default: Valor padrão se conversão falhar
    
    Returns:
        Float convertido ou valor padrão
    """
    try:
        return float(str(value).replace(',', '.'))
    except (ValueError, TypeError, AttributeError):
        return default


def safe_int(value, default: int = 0) -> int:
    """
    Converte valor para int de forma segura
    
    Args:
        value: Valor a converter
        default: Valor padrão se conversão falhar
    
    Returns:
        Int convertido ou valor padrão
    """
    try:
        return int(float(str(value).replace(',', '.')))
    except (ValueError, TypeError, AttributeError):
        return default


def format_file_size(size_bytes: int) -> str:
    """
    Formata tamanho de arquivo de forma legível
    
    Args:
        size_bytes: Tamanho em bytes
    
    Returns:
        String formatada (ex: "2.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def get_csv_info(file_path: str) -> dict:
    """
    Extrai informações básicas do CSV sem carregar tudo na memória
    
    Args:
        file_path: Caminho do arquivo
    
    Returns:
        Dicionário com informações do arquivo
    """
    info = {
        'exists': False,
        'size': 0,
        'size_formatted': '0 B',
        'rows': 0,
        'columns': 0,
        'column_names': []
    }
    
    try:
        if os.path.exists(file_path):
            info['exists'] = True
            info['size'] = os.path.getsize(file_path)
            info['size_formatted'] = format_file_size(info['size'])
            
            # Ler apenas header e primeira linha para contar
            df_sample = pd.read_csv(file_path, nrows=1)
            info['columns'] = df_sample.shape[1]
            info['column_names'] = df_sample.columns.tolist()
            
            # Contar linhas de forma eficiente
            with open(file_path, 'r', encoding='utf-8') as f:
                info['rows'] = sum(1 for _ in f) - 1  # -1 para header
    
    except Exception as e:
        logging.getLogger(__name__).warning(f"Erro ao obter info do CSV: {e}")
    
    return info


def _converter_decimais_europeus(df):
    """Converte colunas não-numéricas com decimal europeu (vírgula) para float.
    Ex.: '0,143893' → 0.143893. Aplica apenas se >50% dos valores forem convertíveis."""
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            try:
                converted = pd.to_numeric(
                    df[col].astype(str).str.replace(',', '.', regex=False),
                    errors='coerce'
                )
                if len(converted) > 0 and converted.notna().sum() / len(converted) > 0.5:
                    df[col] = converted
            except Exception:
                pass
    return df


def safe_read_csv(file_path: str, nrows=None):
    """
    Lê um CSV tentando diferentes encodings e detectando delimitador quando necessário.
    Converte automaticamente separador decimal europeu (vírgula → ponto).
    Retorna um pandas.DataFrame ou levanta ValueError com mensagem amigável.
    """
    import pandas as _pd
    from csv import Sniffer

    encodings = ['utf-8', 'latin-1', 'cp1252']

    # Tentar leitura direta com encodings comuns
    for enc in encodings:
        try:
            df = _pd.read_csv(file_path, encoding=enc, nrows=nrows)
            if df is not None and df.shape[0] > 0 and df.shape[1] > 0:
                return _converter_decimais_europeus(df)
        except Exception:
            continue

    # Detectar delimitador com csv.Sniffer a partir de uma amostra
    delim = ','
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            sample = f.read(8192)
            sniffer = Sniffer()
            dialect = sniffer.sniff(sample)
            delim = dialect.delimiter
    except Exception:
        delim = ','

    # Tentar leitura com delimitador detectado
    for enc in encodings:
        try:
            df = _pd.read_csv(file_path, encoding=enc, sep=delim, engine='python', nrows=nrows)
            if df is not None and df.shape[0] > 0 and df.shape[1] > 0:
                return _converter_decimais_europeus(df)
        except Exception:
            continue

    # Última tentativa: ler sem cabeçalho
    for enc in encodings:
        try:
            df = _pd.read_csv(file_path, encoding=enc, header=None, engine='python', nrows=nrows)
            if df is not None and df.shape[0] > 0 and df.shape[1] > 0:
                return _converter_decimais_europeus(df)
        except Exception:
            continue

    raise ValueError('O arquivo CSV está vazio ou não contém colunas legíveis (tentadas múltiplas decodificações).')


if __name__ == '__main__':
    # Testes
    print("=== TESTES DE UTILITÁRIOS ===\n")
    
    # Teste sanitização
    print("1. Sanitização de nomes:")
    test_names = [
        "arquivo_normal.csv",
        "../../../etc/passwd",
        "arquivo com espaços.csv",
        "arquivo@#$%especial!.csv",
        "....csv",
        "arquivo_muito_longo" * 50 + ".csv"
    ]
    
    for name in test_names:
        try:
            safe = sanitize_filename(name)
            print(f"  '{name}' → '{safe}'")
        except ValueError as e:
            print(f"  '{name}' → ERRO: {e}")
    
    # Teste validação de FS
    print("\n2. Validação de frequência:")
    test_fs = [1000, 0, -100, 1e10, "abc"]
    for fs in test_fs:
        valid, msg = validate_sampling_frequency(fs)
        status = "✅" if valid else "❌"
        print(f"  {status} fs={fs}: {msg or 'OK'}")
    
    print("\n✅ Testes concluídos!")
