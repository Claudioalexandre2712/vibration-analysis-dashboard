"""
Configurações do Sistema de Análise de Vibrações
Suporta múltiplos ambientes: desenvolvimento, produção, testes
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any

def _get_base_dir() -> Path:
    """Retorna diretório base para arquivos graváveis (DB, logs, temp).
    Em dev: pasta do projeto. No .exe: pasta onde o .exe está."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.absolute()

BASE_DIR = _get_base_dir()

class Config:
    """Configuração base - valores padrão"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production-2025'
    DEBUG = False
    TESTING = False
    
    # Servidor
    HOST = os.environ.get('FLASK_HOST') or '0.0.0.0'
    PORT = int(os.environ.get('FLASK_PORT') or 5000)
    
    # Banco de dados
    DATABASE_PATH = os.environ.get('DATABASE_PATH') or str(BASE_DIR / 'vibracoes_historico.db')
    
    # Upload de arquivos
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_FILE_SIZE') or 50 * 1024 * 1024)  # 50MB padrão
    UPLOAD_EXTENSIONS = {'.csv'}
    TEMP_FOLDER = os.environ.get('TEMP_FOLDER') or str(BASE_DIR / 'temp')
    
    # Processamento
    DEFAULT_SAMPLING_FREQUENCY = float(os.environ.get('DEFAULT_FS') or 1000.0)
    MAX_SAMPLING_FREQUENCY = float(os.environ.get('MAX_FS') or 1000000.0)
    MIN_DATA_POINTS = int(os.environ.get('MIN_DATA_POINTS') or 50)
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FILE = os.environ.get('LOG_FILE') or str(BASE_DIR / 'logs' / 'vibracoes.log')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES') or 10 * 1024 * 1024)  # 10MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT') or 5)
    
    # Segurança
    ALLOWED_FILENAME_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')
    MAX_FILENAME_LENGTH = 200
    
    # Cache (futuro)
    ENABLE_CACHE = os.environ.get('ENABLE_CACHE', 'False').lower() == 'true'
    CACHE_TTL = int(os.environ.get('CACHE_TTL') or 3600)  # 1 hora


class DevelopmentConfig(Config):
    """Configuração para ambiente de desenvolvimento"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    

class ProductionConfig(Config):
    """Configuração para ambiente de produção"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    # Em produção, SECRET_KEY deve vir obrigatoriamente do ambiente
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    @classmethod
    def init_app(cls):
        """Validações para produção"""
        if not cls.SECRET_KEY or cls.SECRET_KEY == 'dev-secret-key-change-in-production-2025':
            raise RuntimeError(
                "ERRO: SECRET_KEY não configurada para produção! "
                "Configure a variável de ambiente SECRET_KEY."
            )


class TestingConfig(Config):
    """Configuração para testes automatizados"""
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ':memory:'  # SQLite em memória para testes
    LOG_LEVEL = 'DEBUG'


# Mapeamento de ambientes
config_map: Dict[str, Any] = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env: str = None) -> Config:
    """
    Retorna a configuração apropriada baseada no ambiente
    
    Args:
        env: Nome do ambiente ('development', 'production', 'testing')
             Se None, usa variável FLASK_ENV ou 'development'
    
    Returns:
        Objeto de configuração apropriado
    """
    if env is None:
        env = os.environ.get('FLASK_ENV', 'development')
    
    config_class = config_map.get(env.lower(), DevelopmentConfig)
    
    # Em produção, validar configurações críticas
    if env.lower() == 'production' and hasattr(config_class, 'init_app'):
        config_class.init_app()
    
    return config_class()


# Criar diretórios necessários
def ensure_directories():
    """Cria diretórios necessários se não existirem"""
    config = get_config()
    
    # Diretório de logs
    log_dir = Path(config.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Diretório temporário
    temp_dir = Path(config.TEMP_FOLDER)
    temp_dir.mkdir(parents=True, exist_ok=True)


if __name__ == '__main__':
    # Teste de configuração
    print("=== TESTE DE CONFIGURAÇÃO ===")
    
    for env_name in ['development', 'production', 'testing']:
        print(f"\n{env_name.upper()}:")
        try:
            if env_name == 'production':
                # Para teste, definir temporariamente
                os.environ['SECRET_KEY'] = 'test-prod-key'
            
            cfg = get_config(env_name)
            print(f"  DEBUG: {cfg.DEBUG}")
            print(f"  HOST: {cfg.HOST}:{cfg.PORT}")
            print(f"  LOG_LEVEL: {cfg.LOG_LEVEL}")
            print(f"  MAX_FILE_SIZE: {cfg.MAX_CONTENT_LENGTH / 1024 / 1024:.0f}MB")
            print(f"  DATABASE: {cfg.DATABASE_PATH}")
        except Exception as e:
            print(f"  ERRO: {e}")
    
    ensure_directories()
    print("\n✅ Diretórios criados com sucesso!")
