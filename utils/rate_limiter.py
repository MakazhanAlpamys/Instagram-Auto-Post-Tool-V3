"""
Rate limiter для Gemini API
"""
import time
from datetime import datetime, timedelta
from threading import Lock

class GeminiRateLimiter:
    """Глобальный rate limiter для Gemini API"""
    
    def __init__(self, min_interval: float = 2.0):
        """
        Args:
            min_interval: Минимальный интервал между запросами в секундах
        """
        self.min_interval = min_interval
        self.last_request_time = None
        self.lock = Lock()
        self.request_count = 0
        self.reset_time = datetime.now() + timedelta(minutes=1)
    
    def wait_if_needed(self):
        """Ждет если необходимо соблюсти rate limit"""
        with self.lock:
            now = datetime.now()
            
            # Сброс счетчика каждую минуту
            if now >= self.reset_time:
                self.request_count = 0
                self.reset_time = now + timedelta(minutes=1)
            
            # Проверяем последний запрос
            if self.last_request_time:
                elapsed = (now - self.last_request_time).total_seconds()
                
                if elapsed < self.min_interval:
                    wait_time = self.min_interval - elapsed
                    print(f"⏳ Rate limiter: ожидание {wait_time:.1f}s перед следующим запросом к Gemini...")
                    time.sleep(wait_time)
            
            self.last_request_time = datetime.now()
            self.request_count += 1
    
    def get_stats(self):
        """Возвращает статистику запросов"""
        return {
            'request_count': self.request_count,
            'last_request': self.last_request_time.isoformat() if self.last_request_time else None,
            'reset_time': self.reset_time.isoformat()
        }

# Глобальный экземпляр rate limiter
gemini_rate_limiter = GeminiRateLimiter(min_interval=2.5)  # 2.5 секунды между запросами

