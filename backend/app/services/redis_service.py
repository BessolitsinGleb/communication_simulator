from redis import Redis
import json

class RedisLiveMessages:
    def __init__(self, redis_url: str, user_id: str, max_live_turns: int,  time_to_leave_sec: int | None = None):
        self.db = Redis.from_url(redis_url)
        self.history_key = f"chat:history:{user_id}"
        self.summary_key = f"chat:summary:{user_id}"
        self.user_session = user_id
        self.ttl = time_to_leave_sec
        self.max_live_turns = max_live_turns

    def append(self, role: str, text: str) -> list:
        """
        Добавляет реплику. Если в базе уже 6 элементов,
        удаляет первые 2 и возвращает их списком для суммаризации.
        Если удаления не было, возвращает пустой список [].
        """
        payload = {
            "role": role, "content": text,
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        removed_replicas = []

        # 1. Проверяем длину перед добавлением
        current_len = self.db.llen(self.history_key)

        # 2. Если достигли 6, забираем (извлекаем) первые 2 элемента
        if current_len >= self.max_live_turns:
            raw_1 = self.db.lpop(self.history_key)
            raw_2 = self.db.lpop(self.history_key)
            
            if raw_1: removed_replicas.append(json.loads(raw_1.decode('utf-8')))
            if raw_2: removed_replicas.append(json.loads(raw_2.decode('utf-8')))

        # 3. Добавляем новую реплику в конец списка
        self.db.rpush(self.history_key, serialized)
        
        # Обновляем TTL для истории
        self.db.expire(self.history_key, self.ttl)

        # Возвращаем удаленные элементы (или пустой список)
        return removed_replicas

    def get_summary(self) -> str:
        """Получить текущий текст суммаризации из Redis"""
        summary = self.db.get(self.summary_key)
        return summary.decode('utf-8') if summary else ""

    def save_summary(self, new_summary: str):
        """Сохранить обновленный текст суммаризации в Redis"""
        self.db.set(self.summary_key, new_summary)
        self.db.expire(self.summary_key, self.ttl)

    def get_all(self) -> list:
        """Получить текущие live-сообщения"""
        raw_messages = self.db.lrange(self.history_key, 0, -1)
        return [json.loads(msg.decode('utf-8')) for msg in raw_messages]