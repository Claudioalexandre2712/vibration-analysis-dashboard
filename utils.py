"""Leitura CSV e validações compartilhadas sem efeitos de importação."""
import csv
import io
import os
import re
import numpy as np
import pandas as pd


def sanitize_filename(filename, max_length=200):
    name = re.sub(r'[^a-zA-Z0-9._-]', '_', str(filename or '').replace('\\', '/').split('/')[-1])
    name = re.sub('_+', '_', name).replace('..', '').lstrip('.-')[:max_length]
    if not name:
        raise ValueError('Nome de arquivo inválido.')
    return name


def validate_sampling_frequency(fs, min_fs=.1, max_fs=1_000_000):
    try:
        x = float(fs)
        if not np.isfinite(x) or not min_fs <= x <= max_fs:
            return False, f'Frequência de amostragem deve estar entre {min_fs} e {max_fs} Hz.'
        return True, None
    except (ValueError, TypeError):
        return False, 'Frequência de amostragem inválida.'


def safe_read_csv(source, nrows=None):
    if isinstance(source, bytes):
        data = source
    elif hasattr(source, 'read'):
        source.seek(0)
        data = source.read()
    else:
        with open(source, 'rb') as handle:
            data = handle.read()
    if isinstance(data, bytes):
        for encoding in ['utf-8-sig', 'cp1252', 'latin-1']:
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    else:
        text = data.lstrip('\ufeff')
    if not text.strip() or '\x00' in text:
        raise ValueError('CSV vazio ou inválido.')
    sample = '\n'.join(text.splitlines()[:30])
    try:
        sep = csv.Sniffer().sniff(sample, delimiters=';,\t|').delimiter
    except csv.Error:
        sep = ';' if ';' in sample else '\t' if '\t' in sample else ','
    first = next(csv.reader(io.StringIO(text), delimiter=sep), [])
    if len(first) > 32:
        raise ValueError('CSV excede o limite de 32 colunas.')
    try:
        records = csv.reader(io.StringIO(text), delimiter=sep, strict=True)
        next(records, None)
        for count, record in enumerate(records):
            if record and len(record) != len(first):
                raise ValueError('CSV malformado: quantidade de campos diferente do cabeçalho.')
            if nrows is not None and count >= nrows:
                break
    except csv.Error as exc:
        raise ValueError('CSV malformado: aspas ou campos inválidos.') from exc
    def numeric(cell):
        try:
            float(cell.strip().replace(',', '.'))
            return True
        except ValueError:
            return False
    header = None if first and all(numeric(cell) for cell in first) else 0
    if header == 0:
        names = [cell.strip().casefold() for cell in first]
        if not all(names) or len(set(names)) != len(names):
            raise ValueError('Cabeçalhos vazios ou duplicados. Use um nome único por coluna.')
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, header=header, nrows=nrows, dtype=str, on_bad_lines='error')
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError('CSV malformado. Confira separadores e quantidade de colunas.') from exc
    if header is None:
        df.columns = [f'coluna_{i+1}' for i in range(df.shape[1])]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        cleaned = df[col].str.strip().str.replace(',', '.', regex=False)
        converted = pd.to_numeric(cleaned, errors='coerce')
        if converted.notna().any():
            df[col] = converted
    return df


def validate_csv_file(file_path, min_rows=50, max_size_mb=50):
    try:
        if os.path.getsize(file_path) > max_size_mb*1024*1024:
            return False, 'Arquivo excede o limite.'
        df = safe_read_csv(file_path)
        if len(df) < min_rows:
            return False, f'CSV precisa de pelo menos {min_rows} amostras.'
        return True, None
    except (OSError, ValueError) as exc:
        return False, str(exc)


def safe_float(value, default=0.):
    try:
        result = float(str(value).replace(',', '.'))
        return result if np.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    return int(safe_float(value, default))


def format_file_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f'{size_bytes:.1f} {unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f} TB'


def get_csv_info(file_path):
    df = safe_read_csv(file_path)
    size = os.path.getsize(file_path)
    return {'exists':True, 'size':size, 'size_formatted':format_file_size(size), 'rows':len(df), 'columns':len(df.columns), 'column_names':list(df.columns)}
