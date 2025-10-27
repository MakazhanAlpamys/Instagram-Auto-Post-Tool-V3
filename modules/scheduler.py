"""
Планировщик времени публикаций
"""
import json
from datetime import datetime, timedelta
from typing import List, Dict

from config import SCHEDULER_FILE, POSTING_START_HOUR, POSTING_END_HOUR, DEFAULT_SETTINGS
from utils.logger import log_info, log_success
from modules.post_manager import post_manager

class PostScheduler:
    """Планировщик времени публикации постов"""
    
    def __init__(self):
        self.schedule = self._load_schedule()
    
    def _load_schedule(self) -> Dict:
        """Загружает расписание из файла"""
        if SCHEDULER_FILE.exists():
            try:
                with open(SCHEDULER_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_schedule(self):
        """Сохраняет расписание в файл"""
        with open(SCHEDULER_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.schedule, f, ensure_ascii=False, indent=2)
    
    def schedule_posts_for_account(self, account_id: str, post_ids: List[str], 
                                   posts_per_day: int, start_date: datetime = None) -> List[Dict]:
        """
        Равномерно распределяет посты по времени для одного аккаунта
        
        Args:
            account_id: ID аккаунта
            post_ids: Список ID постов для планирования
            posts_per_day: Количество постов в день
            start_date: Дата начала (по умолчанию - сейчас)
        
        Returns:
            Список запланированных постов
        """
        if not start_date:
            start_date = datetime.now()
        
        # ВАЖНО: Устанавливаем время начала с учетом текущего времени
        now = datetime.now()
        start_time = start_date.replace(minute=0, second=0, microsecond=0)
        
        # Если дата в прошлом, начинаем с текущего момента
        if start_time < now:
            start_time = now
        
        # Проверяем, попадаем ли в рабочее время
        if start_time.hour < POSTING_START_HOUR:
            # Слишком рано - начинаем с 8:00
            start_time = start_time.replace(hour=POSTING_START_HOUR, minute=0)
        elif start_time.hour >= POSTING_END_HOUR:
            # Слишком поздно - начинаем завтра с 8:00
            start_time = start_time + timedelta(days=1)
            start_time = start_time.replace(hour=POSTING_START_HOUR, minute=0)
        else:
            # В рабочее время - добавляем минимальный интервал к текущему времени
            start_time = start_time + timedelta(minutes=DEFAULT_SETTINGS['min_post_interval'])
        
        scheduled_posts = []
        
        # Распределяем посты по дням
        total_posts = len(post_ids)
        days_needed = (total_posts + posts_per_day - 1) // posts_per_day
        
        current_day = 0
        post_index = 0
        
        while post_index < total_posts:
            # Количество постов на этот день
            posts_today = min(posts_per_day, total_posts - post_index)
            
            # Равномерно распределяем по времени
            scheduled_times = self._distribute_posts_in_day(
                start_time + timedelta(days=current_day),
                posts_today
            )
            
            for scheduled_time in scheduled_times:
                if post_index >= total_posts:
                    break
                
                post_id = post_ids[post_index]
                
                # Планируем пост
                post = post_manager.schedule_post(
                    post_id,
                    scheduled_time.isoformat()
                )
                
                if post:
                    scheduled_posts.append(post)
                    
                    # Добавляем в расписание
                    if account_id not in self.schedule:
                        self.schedule[account_id] = []
                    
                    self.schedule[account_id].append({
                        'post_id': post_id,
                        'scheduled_time': scheduled_time.isoformat(),
                        'status': 'scheduled'
                    })
                
                post_index += 1
            
            current_day += 1
        
        self._save_schedule()
        log_success(f"Запланировано {len(scheduled_posts)} постов для аккаунта {account_id}")
        
        return scheduled_posts
    
    def _distribute_posts_in_day(self, start_date: datetime, posts_count: int) -> List[datetime]:
        """Равномерно распределяет посты в течение дня"""
        now = datetime.now()
        
        # Время начала и конца постинга
        start_time = start_date.replace(hour=POSTING_START_HOUR, minute=0)
        end_time = start_date.replace(hour=POSTING_END_HOUR, minute=0)
        
        # ВАЖНО: Если планируем на сегодня и start_time в прошлом, начинаем с текущего времени
        if start_time.date() == now.date() and start_time < now:
            start_time = now + timedelta(minutes=DEFAULT_SETTINGS['min_post_interval'])
            # Округляем до ближайших 5 минут для красоты
            start_time = start_time.replace(second=0, microsecond=0)
            minute = (start_time.minute // 5) * 5
            start_time = start_time.replace(minute=minute)
        
        # Общее количество минут
        total_minutes = (end_time - start_time).total_seconds() / 60
        
        # Если времени недостаточно, переносим на следующий день
        min_interval = DEFAULT_SETTINGS['min_post_interval']
        required_minutes = posts_count * min_interval
        
        if total_minutes < required_minutes:
            # Не хватает времени сегодня - начинаем завтра
            start_time = (start_time + timedelta(days=1)).replace(hour=POSTING_START_HOUR, minute=0)
            end_time = start_time.replace(hour=POSTING_END_HOUR, minute=0)
            total_minutes = (end_time - start_time).total_seconds() / 60
        
        # Интервал между постами
        interval = total_minutes / posts_count
        
        if interval < min_interval:
            interval = min_interval
        
        scheduled_times = []
        for i in range(posts_count):
            scheduled_time = start_time + timedelta(minutes=interval * i)
            
            # Проверяем, что не выходим за пределы рабочего времени
            if scheduled_time.hour >= POSTING_END_HOUR:
                break
            
            # Дополнительная проверка: пост не в прошлом
            if scheduled_time <= now:
                continue
            
            scheduled_times.append(scheduled_time)
        
        return scheduled_times
    
    def get_scheduled_posts_for_account(self, account_id: str) -> List[Dict]:
        """Получает все запланированные посты для аккаунта"""
        return self.schedule.get(account_id, [])
    
    def remove_from_schedule(self, post_id: str):
        """Удаляет пост из расписания"""
        for account_id in self.schedule:
            self.schedule[account_id] = [
                item for item in self.schedule[account_id]
                if item['post_id'] != post_id
            ]
        
        self._save_schedule()
    
    def mark_as_published(self, post_id: str):
        """Отмечает пост как опубликованный в расписании"""
        for account_id in self.schedule:
            for item in self.schedule[account_id]:
                if item['post_id'] == post_id:
                    item['status'] = 'published'
        
        self._save_schedule()

# Глобальный экземпляр
post_scheduler = PostScheduler()
