"""
Система логирования
"""
import logging
from datetime import datetime
from pathlib import Path
from config import APP_LOG_FILE

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(APP_LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('instagram_auto_post')

def log_info(message: str):
    """Логирует информационное сообщение"""
    logger.info(message)

def log_warning(message: str):
    """Логирует предупреждение"""
    logger.warning(message)

def log_error(message: str):
    """Логирует ошибку"""
    logger.error(message)

def log_success(message: str):
    """Логирует успешную операцию"""
    logger.info(f"✅ {message}")

def log_account_login(username: str, success: bool, error: str = None):
    """Логирует попытку входа в аккаунт"""
    if success:
        log_success(f"Аккаунт {username} успешно залогинен")
    else:
        log_error(f"Аккаунт {username} не удалось залогинить: {error}")

def log_post_published(post_id: str, account_username: str):
    """Логирует публикацию поста"""
    log_success(f"Пост {post_id} опубликован на {account_username}")

def log_post_error(post_id: str, error: str):
    """Логирует ошибку публикации поста"""
    log_error(f"Ошибка публикации поста {post_id}: {error}")

def get_logs(limit: int = 100) -> list:
    """Получает последние логи"""
    try:
        with open(APP_LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return lines[-limit:]
    except Exception:
        return []
