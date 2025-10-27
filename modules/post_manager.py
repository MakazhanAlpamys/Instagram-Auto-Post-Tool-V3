"""
Менеджер постов
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import (
    DRAFTS_DIR, SCHEDULED_DIR, PUBLISHED_DIR,
    POST_STATUS, PHOTOS_DIR, VIDEOS_DIR
)
from utils.logger import log_info, log_success, log_error

class PostManager:
    """Управление постами"""
    
    def __init__(self):
        pass
    
    def create_post(self, account_id: str, text: str, media: List[str],
                   post_format: str = "photo", status: str = POST_STATUS["DRAFT"]) -> Dict:
        """Создает новый пост"""
        post_id = str(uuid.uuid4())
        
        post_data = {
            "id": post_id,
            "account_id": account_id,
            "text": text,
            "media": media,
            "format": post_format,
            "status": status,
            "scheduled_time": None,
            "created_at": datetime.now().isoformat(),
            "published_at": None,
            "error": None
        }
        
        self._save_post(post_data)
        log_info(f"Создан пост {post_id} для аккаунта {account_id}")
        
        return post_data
    
    def update_post(self, post_id: str, updates: Dict) -> Optional[Dict]:
        """Обновляет пост"""
        post = self.get_post(post_id)
        if not post:
            return None
        
        old_status = post['status']
        post.update(updates)
        new_status = post['status']
        
        # Если статус изменился - удаляем старый файл
        if old_status != new_status:
            self._delete_post_file(post_id, old_status)
        
        self._save_post(post)
        
        return post
    
    def schedule_post(self, post_id: str, scheduled_time: str) -> Optional[Dict]:
        """Планирует публикацию поста"""
        post = self.get_post(post_id)
        if not post:
            return None
        
        # Перемещаем из drafts в scheduled
        if post['status'] == POST_STATUS["DRAFT"]:
            self._delete_post_file(post_id, POST_STATUS["DRAFT"])
        
        post['status'] = POST_STATUS["SCHEDULED"]
        post['scheduled_time'] = scheduled_time
        
        self._save_post(post)
        log_info(f"Пост {post_id} запланирован на {scheduled_time}")
        
        return post
    
    def publish_post(self, post_id: str) -> Optional[Dict]:
        """Отмечает пост как опубликованный"""
        post = self.get_post(post_id)
        if not post:
            return None
        
        # Перемещаем из scheduled в published
        if post['status'] == POST_STATUS["SCHEDULED"]:
            self._delete_post_file(post_id, POST_STATUS["SCHEDULED"])
        
        post['status'] = POST_STATUS["PUBLISHED"]
        post['published_at'] = datetime.now().isoformat()
        
        self._save_post(post)
        log_success(f"Пост {post_id} опубликован")
        
        return post
    
    def mark_post_error(self, post_id: str, error: str) -> Optional[Dict]:
        """Отмечает ошибку публикации"""
        post = self.get_post(post_id)
        if not post:
            return None
        
        post['status'] = POST_STATUS["ERROR"]
        post['error'] = error
        
        self._save_post(post)
        log_error(f"Ошибка поста {post_id}: {error}")
        
        return post
    
    def delete_post(self, post_id: str):
        """Удаляет пост"""
        post = self.get_post(post_id)
        if not post:
            return
        
        self._delete_post_file(post_id, post['status'])
        log_info(f"Удален пост {post_id}")
    
    def get_post(self, post_id: str) -> Optional[Dict]:
        """Получает пост по ID"""
        # Ищем во всех директориях
        for status_dir in [DRAFTS_DIR, SCHEDULED_DIR, PUBLISHED_DIR]:
            post_file = status_dir / f"{post_id}.json"
            if post_file.exists():
                try:
                    with open(post_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    log_error(f"Ошибка чтения поста {post_id}: {e}")
        
        return None
    
    def get_posts_by_account(self, account_id: str, status: Optional[str] = None) -> List[Dict]:
        """Получает все посты аккаунта"""
        posts = []
        
        if status:
            # Поиск только в определенной директории
            status_dir = self._get_status_dir(status)
            for post_file in status_dir.glob('*.json'):
                try:
                    with open(post_file, 'r', encoding='utf-8') as f:
                        post = json.load(f)
                        if post['account_id'] == account_id:
                            posts.append(post)
                except Exception:
                    pass
        else:
            # Поиск во всех директориях
            for status_dir in [DRAFTS_DIR, SCHEDULED_DIR, PUBLISHED_DIR]:
                for post_file in status_dir.glob('*.json'):
                    try:
                        with open(post_file, 'r', encoding='utf-8') as f:
                            post = json.load(f)
                            if post['account_id'] == account_id:
                                posts.append(post)
                    except Exception:
                        pass
        
        # Сортируем по дате создания
        posts.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return posts
    
    def get_all_posts(self, status: Optional[str] = None) -> List[Dict]:
        """Получает все посты"""
        posts = []
        
        if status:
            status_dir = self._get_status_dir(status)
            dirs_to_search = [status_dir]
        else:
            dirs_to_search = [DRAFTS_DIR, SCHEDULED_DIR, PUBLISHED_DIR]
        
        for status_dir in dirs_to_search:
            for post_file in status_dir.glob('*.json'):
                try:
                    with open(post_file, 'r', encoding='utf-8') as f:
                        posts.append(json.load(f))
                except Exception:
                    pass
        
        # Сортируем по дате создания
        posts.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return posts
    
    def get_scheduled_posts(self) -> List[Dict]:
        """Получает все запланированные посты"""
        return self.get_all_posts(POST_STATUS["SCHEDULED"])
    
    def _save_post(self, post: Dict):
        """Сохраняет пост в соответствующую директорию"""
        status = post['status']
        status_dir = self._get_status_dir(status)
        
        post_file = status_dir / f"{post['id']}.json"
        with open(post_file, 'w', encoding='utf-8') as f:
            json.dump(post, f, ensure_ascii=False, indent=2)
    
    def _delete_post_file(self, post_id: str, status: str):
        """Удаляет файл поста"""
        status_dir = self._get_status_dir(status)
        post_file = status_dir / f"{post_id}.json"
        
        if post_file.exists():
            post_file.unlink()
    
    def _get_status_dir(self, status: str) -> Path:
        """Получает директорию для статуса"""
        if status == POST_STATUS["DRAFT"]:
            return DRAFTS_DIR
        elif status == POST_STATUS["SCHEDULED"]:
            return SCHEDULED_DIR
        elif status == POST_STATUS["PUBLISHED"]:
            return PUBLISHED_DIR
        else:
            return DRAFTS_DIR

# Глобальный экземпляр менеджера
post_manager = PostManager()
