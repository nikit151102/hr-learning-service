import asyncio
import logging
import os
from typing import Optional
from uuid import UUID

from maxapi import Bot

from app.models import Material, Test, User

logger = logging.getLogger(__name__)


class MaxNotificationService:
    def __init__(self):
        self.bot_token = os.getenv("MAX_BOT_TOKEN")
        self.bot: Optional[Bot] = None
        
        if self.bot_token:
            try:
                self.bot = Bot(self.bot_token)
                logger.info("MAX Bot инициализирован для уведомлений")
            except Exception as e:
                logger.error(f"Ошибка инициализации MAX Bot: {e}")
        else:
            logger.warning("MAX_BOT_TOKEN не установлен, уведомления отключены")

    async def _send_message(self, user_id_max: str, text: str) -> bool:
        """Отправляет сообщение пользователю через MAX"""
        if not self.bot:
            logger.warning("MAX Bot не инициализирован")
            return False

        try:
            # user_id_max это и есть user_id в MAX
            response = await self.bot.send_message(
                user_id=int(user_id_max),
                text=text
            )
            logger.info(f"Сообщение отправлено пользователю {user_id_max}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {user_id_max}: {e}")
            return False

    def send_assignment_notification(
        self,
        user: User,
        material: Optional[Material] = None,
        test: Optional[Test] = None,
        due_date: Optional[str] = None,
        note: Optional[str] = None
    ):
        """Отправляет уведомление о новом назначении"""
        if not self.bot:
            return

        # Формируем текст уведомления
        if material:
            object_type = "материал"
            object_title = material.title
        elif test:
            object_type = "тест"
            object_title = test.title
        else:
            return

        text = (
            f"📚 **Новое назначение**\n\n"
            f"Здравствуйте, {user.full_name}!\n\n"
            f"Вам назначен {object_type}: **{object_title}**\n\n"
        )

        if due_date:
            text += f"Срок выполнения: {due_date}\n\n"

        if note:
            text += f"Комментарий: {note}\n\n"

        text += (
            f"Откройте бота, чтобы начать выполнение.\n\n"
            f"Удачи!"
        )

        # Запускаем отправку в отдельной задаче, чтобы не блокировать основной поток
        asyncio.create_task(self._send_message(user.id_max, text))

    def send_bulk_assignment_notification(
        self,
        users: list[User],
        material: Optional[Material] = None,
        test: Optional[Test] = None,
        due_date: Optional[str] = None,
        note: Optional[str] = None
    ):
        """Отправляет массовое уведомление о назначении"""
        for user in users:
            self.send_assignment_notification(
                user=user,
                material=material,
                test=test,
                due_date=due_date,
                note=note
            )


# Глобальный экземпляр сервиса
max_notification_service = MaxNotificationService()