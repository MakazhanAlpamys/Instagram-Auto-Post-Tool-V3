"""
Менеджер аккаунтов Instagram
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from instagrapi import Client
import threading

from config import ACCOUNTS_DIR, ACCOUNT_STATUS
from utils.encryption import encrypt_password, decrypt_password
from utils.logger import log_info, log_success, log_error, log_account_login

class AccountManager:
    """Управление множественными Instagram аккаунтами"""
    
    def __init__(self):
        self.accounts = {}
        self.clients = {}  # account_id -> Client
        self.load_all_accounts()
    
    def load_all_accounts(self):
        """Загружает все сохраненные аккаунты"""
        if not ACCOUNTS_DIR.exists():
            return
        
        for account_dir in ACCOUNTS_DIR.iterdir():
            if account_dir.is_dir():
                config_file = account_dir / 'config.json'
                if config_file.exists():
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            account_data = json.load(f)
                            self.accounts[account_data['id']] = account_data
                    except Exception as e:
                        log_error(f"Ошибка загрузки аккаунта из {account_dir}: {e}")
    
    def create_account(self, username: str, password: str, 
                      theme: str = "", language: str = "русский",
                      posts_per_day: int = 5, format: str = "photo") -> Dict:
        """Создает новый аккаунт"""
        account_id = str(uuid.uuid4())
        
        account_data = {
            "id": account_id,
            "username": username,
            "password": encrypt_password(password),
            "status": ACCOUNT_STATUS["INACTIVE"],
            "last_login": None,
            "theme": theme,
            "language": language,
            "posts_per_day": posts_per_day,
            "format": format,
            "created_at": datetime.now().isoformat()
        }
        
        # Создаем директорию для аккаунта
        account_dir = ACCOUNTS_DIR / account_id
        account_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем конфигурацию
        config_file = account_dir / 'config.json'
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(account_data, f, ensure_ascii=False, indent=2)
        
        # Создаем файл логов
        log_file = account_dir / 'logs.txt'
        log_file.touch()
        
        self.accounts[account_id] = account_data
        log_success(f"Создан аккаунт {username} (ID: {account_id})")
        
        return account_data
    
    def login_account(self, account_id: str) -> bool:
        """Входит в аккаунт Instagram БЕЗ двухфакторной верификации"""
        if account_id not in self.accounts:
            return False
        
        account = self.accounts[account_id]
        username = account['username']
        password = decrypt_password(account['password'])
        
        # Обновляем статус
        self._update_account_status(account_id, ACCOUNT_STATUS["LOGGING_IN"])
        
        try:
            client = Client()
            client.delay_range = [1, 3]
            
            account_dir = ACCOUNTS_DIR / account_id
            session_file = account_dir / 'session.json'
            
            # Отключаем обработку 2FA и challenge - работаем только с сохраненными сессиями
            client.challenge_code_handler = lambda username, choice: None
            client.change_password_handler = lambda username: None
            
            # Пытаемся загрузить существующую сессию
            if session_file.exists():
                try:
                    client.load_settings(session_file)
                    client.login(username, password)
                    log_info(f"Вход выполнен с сохраненной сессией: {username}")
                except Exception as e:
                    log_info(f"Не удалось использовать сохраненную сессию: {e}")
                    # Пробуем новый вход без 2FA
                    try:
                        client.login(username, password)
                    except Exception as login_error:
                        # Если требуется 2FA или challenge - отменяем
                        if "challenge" in str(login_error).lower() or "two" in str(login_error).lower():
                            raise Exception("❌ Аккаунт требует двухфакторную верификацию. Используйте только аккаунты БЕЗ 2FA!")
                        raise login_error
            else:
                # Новый вход без 2FA
                try:
                    client.login(username, password)
                except Exception as login_error:
                    # Если требуется 2FA или challenge - отменяем
                    if "challenge" in str(login_error).lower() or "two" in str(login_error).lower() or "checkpoint" in str(login_error).lower():
                        raise Exception("❌ Аккаунт требует двухфакторную верификацию или проверку. Используйте только аккаунты БЕЗ 2FA!")
                    raise login_error
            
            # Сохраняем сессию
            client.dump_settings(session_file)
            
            # Сохраняем клиент
            self.clients[account_id] = client
            
            # Обновляем статус
            self._update_account_status(account_id, ACCOUNT_STATUS["ACTIVE"])
            account['last_login'] = datetime.now().isoformat()
            self._save_account(account_id)
            
            log_account_login(username, True)
            return True
            
        except Exception as e:
            self._update_account_status(account_id, ACCOUNT_STATUS["ERROR"])
            log_account_login(username, False, str(e))
            return False
    
    def logout_account(self, account_id: str):
        """Выходит из аккаунта"""
        if account_id in self.clients:
            del self.clients[account_id]
        
        self._update_account_status(account_id, ACCOUNT_STATUS["INACTIVE"])
        
        if account_id in self.accounts:
            log_info(f"Выход из аккаунта {self.accounts[account_id]['username']}")
    
    def delete_account(self, account_id: str):
        """Удаляет аккаунт"""
        if account_id in self.clients:
            del self.clients[account_id]
        
        if account_id in self.accounts:
            username = self.accounts[account_id]['username']
            del self.accounts[account_id]
            
            # Удаляем директорию
            import shutil
            account_dir = ACCOUNTS_DIR / account_id
            if account_dir.exists():
                shutil.rmtree(account_dir)
            
            log_info(f"Удален аккаунт {username}")
    
    def get_account(self, account_id: str) -> Optional[Dict]:
        """Получает данные аккаунта"""
        return self.accounts.get(account_id)
    
    def get_all_accounts(self) -> List[Dict]:
        """Получает все аккаунты"""
        return list(self.accounts.values())
    
    def get_active_accounts(self) -> List[Dict]:
        """Получает только активные аккаунты"""
        return [acc for acc in self.accounts.values() 
                if acc['status'] == ACCOUNT_STATUS["ACTIVE"]]
    
    def get_client(self, account_id: str) -> Optional[Client]:
        """Получает Instagram клиент для аккаунта"""
        return self.clients.get(account_id)
    
    def auto_login_all(self):
        """Автоматически входит во все аккаунты при запуске"""
        log_info("Начало автологина всех аккаунтов...")
        
        threads = []
        for account_id in self.accounts:
            thread = threading.Thread(
                target=self.login_account,
                args=(account_id,)
            )
            threads.append(thread)
            thread.start()
        
        # Ждем завершения всех потоков
        for thread in threads:
            thread.join()
        
        active_count = len(self.get_active_accounts())
        total_count = len(self.accounts)
        log_success(f"Автологин завершен: {active_count}/{total_count} аккаунтов активны")
    
    def _update_account_status(self, account_id: str, status: str):
        """Обновляет статус аккаунта"""
        if account_id in self.accounts:
            self.accounts[account_id]['status'] = status
            self._save_account(account_id)
    
    def _save_account(self, account_id: str):
        """Сохраняет данные аккаунта"""
        if account_id not in self.accounts:
            return
        
        account_dir = ACCOUNTS_DIR / account_id
        config_file = account_dir / 'config.json'
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(self.accounts[account_id], f, ensure_ascii=False, indent=2)

# Глобальный экземпляр менеджера
account_manager = AccountManager()
