"""
Утилиты для шифрования паролей
"""
from cryptography.fernet import Fernet
import os
import base64
from pathlib import Path

# Генерируем или загружаем ключ шифрования
KEY_FILE = Path(__file__).parent.parent / 'data' / '.encryption_key'

def get_or_create_key():
    """Получает существующий ключ или создает новый"""
    if KEY_FILE.exists():
        with open(KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(KEY_FILE, 'wb') as f:
            f.write(key)
        return key

ENCRYPTION_KEY = get_or_create_key()
cipher = Fernet(ENCRYPTION_KEY)

def encrypt_password(password: str) -> str:
    """Шифрует пароль"""
    if not password:
        return ""
    return cipher.encrypt(password.encode()).decode()

def decrypt_password(encrypted: str) -> str:
    """Расшифровывает пароль"""
    if not encrypted:
        return ""
    try:
        return cipher.decrypt(encrypted.encode()).decode()
    except Exception:
        return ""
