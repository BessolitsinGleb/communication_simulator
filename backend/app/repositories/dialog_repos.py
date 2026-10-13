from ..core.config import s
# FIX: суммаризация шла через openai.chat.completions.create без ключа OpenAI и падала после 6 реплик.
# Теперь используется тот же OpenRouter-клиент, что и для основных ответов.
from .openrout_repos import send_to_ai
from ..services.redis_service import RedisLiveMessages
from redis import Redis

class SummarizedConversationMemory:
    def __init__(self, user_id: str, system_prompt: str | None = None):

        self.system_prompt = system_prompt
        self.live_messages = RedisLiveMessages(redis_url=s.REDIS_URL,
                                                        time_to_leave_sec=s.REDIS_TTL,
                                                        user_id=user_id,
                                                        max_live_turns=s.DIALOG_LEN_BEFORE_SUM) 
        self.db = Redis.from_url(s.REDIS_URL)
        self.history_key = f"chat:history:{user_id}"
        self.summary_key = f"chat:summary:{user_id}"

    # FIX: метод стал async, потому что суммаризация делает сетевой запрос к LLM.
    # Синхронный вызов блокировал бы event loop для всех пользователей.
    async def add_message(self, role: str, text: str) -> None:
        """Добавляет новую реплику продавца или клиента в память."""
        deleted_turns = self.live_messages.append(role, text)
        if deleted_turns:
            await self._summarize_oldest_turns(messages_to_summary=deleted_turns)

    async def _summarize_oldest_turns(self, messages_to_summary: dict) -> None:
        """Берет самые старые реплики, объединяет с прошлым суммари и сжимает через LLM."""
        # Отрезаем первые 2 реплики (один круг диалога: продавец + клиент) для сжатия
        turns_to_summarize = messages_to_summary
        
        # Формируем текст для отправки на суммаризацию
        # FIX: реплики хранятся как {"role", "content"}, ключа 'replic' нет → был KeyError.
        dialogue_chunk = "\n".join([f"{m['role']}: {m['content']}" for m in turns_to_summarize])
        
        prompt = f"""
        У тебя есть предыдущее краткое содержание разговора и пара новых реплик.
        Объедини их и напиши ОДНО новое, обновленное краткое содержание разговора.
        Пиши строго в третьем лице, тезисно и емко. Максимум 2-3 предложения.

        Текущее краткое содержание: {self.live_messages.get_summary()}
        Новые реплики для добавления:
        {dialogue_chunk}
        """
        
        # Запрос к LLM для генерации нового суммари
        # В реальном коде используйте ваш клиент (openai, vllm, ollama и т.д.)
        summary = await send_to_ai([{"role": "user", "content": prompt}])
        self.live_messages.save_summary(new_summary=summary.strip())

    def get_messages_for_llm(self) -> list:
        """Собирает финальный пакет данных, который отправляется боту для генерации ответа."""
        # Формируем динамический системный промпт, куда подмешано суммари
        dynamic_system_content = f"""{self.system_prompt}

        КРАТКОЕ СОДЕРЖАНИЕ ПРЕДЫДУЩЕЙ ЧАСТИ РАЗГОВОРА (для контекста):
        {self.live_messages.get_summary()}
        """
        
        # Собираем итоговый массив: Системный промпт с суммари + последние «живые» реплики
        return [{"role": "system", "content": dynamic_system_content}] + self.live_messages.get_all()

    def clear_all_data(self) -> bool:
        """Удаляет все данные сессии из Redis. Возвращает True, если что-то было удалено."""
        # Команда delete возвращает количество удаленных ключей
        deleted_count = self.db.delete(self.history_key, self.summary_key)
        return deleted_count > 0