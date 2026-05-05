import asyncio
import json
import os.path
from dataclasses import dataclass, field
from typing import Optional, Union, List

from telethon import TelegramClient, events
from telethon.tl.types import Message, TypeKeyboardButton, KeyboardButtonUrl, KeyboardButtonCallback

from src.core import get_logger, get_settings
from src.patterns import RegexPattern

logger = get_logger()


@dataclass
class GiveawayInfo:
    message_id: int
    chat_id: int
    mini_app_url: Optional[str] = None
    button_texts: List[str] = field(default_factory=list)


@dataclass
class ButtonInfo:
    row_idx: int
    col_idx: int
    text: str
    button_type: str
    url: Optional[str] = None
    data: Optional[bytes] = None


class AutomationAccountManager:
    def __init__(self, client: TelegramClient, session_name: str = ""):
        self.config = get_settings()
        self.client: TelegramClient = client
        self.session_name: str = session_name
        self._listening: bool = False
        self._listen_task: Optional[asyncio.Task] = None

    async def start_channel_listener(self) -> None:
        """Запуск прослушки каналов в фоновом режиме (не блокируя поток)."""
        if self._listening:
            logger.warning(f"Прослушка уже запущена для сессии: {self.session_name}")
            return

        self._listening = True
        self._listen_task = asyncio.create_task(self._channel_listener_loop())
        logger.info(f"Запущена прослушка групп для сессии: {self.session_name}")

    async def stop_channel_listener(self) -> None:
        """Остановка прослушки групп."""
        if not self._listening:
            return

        self._listening = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        logger.info(f"Остановлена прослушка групп для сессии: {self.session_name}")

    async def _channel_listener_loop(self) -> None:
        """Цикл прослушки событий от каналов."""
        channel_ids = self.config.channel_ids_list

        if not channel_ids:
            logger.error("Нет ID каналов для прослушки")
            return

        await self.client.get_dialogs()

        @self.client.on(events.NewMessage(chats=3872616339))
        async def new_message_handler(event: events.NewMessage.Event) -> None:
            if self._listening:
                await self._process_channel_message(event)

        try:
            while self._listening:
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass
        finally:
            self.client.remove_event_handler(new_message_handler)

    async def _process_channel_message(
        self,
        event: Union[events.NewMessage.Event, events.MessageEdited.Event]
    ) -> None:
        try:
            message: Message = event.message
            chat = await event.get_chat()

            logger.info(f"[{self.session_name}] Сообщение из группы: {chat.id}")
            logger.info(f"Message ID: {message.id} - {message.message}")

            # Проверка кнопок
            if message.reply_markup:
                buttons_info = await self._analyze_buttons(message)
                logger.debug(f"Buttons info: {buttons_info}")
            else:
                logger.info("Сообщение без кнопок")

            # Обработка сообщения (ищем паттерн по ID группы)
            result, pattern_id = await self._handle_message(channel_id=chat.id, message=message)
            logger.info(f"pattern_id: {pattern_id}")

            if not result or pattern_id is None:
                logger.info("_handle_message не вернул pattern_id. Завершаю обработку.")
                return

            # Отвечаем на сообщение в той же группе
            message = await self._handle_response(
                chat_id=chat.id,
                pattern_id=pattern_id,
                reply_to=message.id
            )
            logger.info(f"message: {message}")

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)

    async def _analyze_buttons(self, message: Message) -> List[ButtonInfo]:
        buttons_count = sum(len(row.buttons) for row in message.reply_markup.rows)
        logger.info(f"Найдена кнопок: {buttons_count}")

        result: List[ButtonInfo] = []
        for row_idx, row in enumerate(message.reply_markup.rows):
            for col_idx, button in enumerate(row.buttons):
                button_type = await self._get_button_type(button)
                button_info = ButtonInfo(
                    row_idx=row_idx,
                    col_idx=col_idx,
                    text=button.text,
                    button_type=button_type,
                    url=getattr(button, 'url', None),
                    data=getattr(button, 'data', None)
                )
                result.append(button_info)

        return result

    async def _get_button_type(self, button: TypeKeyboardButton) -> str:
        if isinstance(button, KeyboardButtonUrl):
            return 'url'
        elif isinstance(button, KeyboardButtonCallback):
            return 'callback'
        else:
            return 'simple'

    async def _handle_message(self, channel_id: int, message: Message):
        """Мега обработчик. Использует паттерны для определения"""
        text = message.message

        pattern_path = get_settings().PATTERN_PATH / f"{channel_id}.json"

        if not os.path.exists(pattern_path):
            logger.info(pattern_path)
            logger.warning(f"Файл паттерн {channel_id}.json не найден")
            return False, None

        try:
            with open(pattern_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                patterns = data["patterns"]
                logger.info(f"Файл паттерн {channel_id}.json найден и загружен")

        except json.JSONDecodeError as e:
            logger.error(f"Ошибки формата паттерна {channel_id}.json: {e}")
            return False, None
        except Exception as e:
            logger.error(f"Ошибки при загрузке паттерна {channel_id}.json: {e}")
            return False, None

        for pattern in patterns:
            logger.info(f"pattern: {pattern}")
            regex_pattern = RegexPattern(
                pattern=pattern["text"],
                threshold=pattern['threshold']
            )
            result = regex_pattern.match(text=text)

            logger.info(f"Результат: {result}")

            if result:
                return True, pattern["id"]

        return False, None

    async def _handle_response(self, channel_id: int, pattern_id: int, reply_to: int = None):
        """
        Отправка ответа в комментарии к посту канала.

        Для комментариев нужно отправлять сообщение в группу комментариев
        (chat_id из паттерна), а reply_to указывает на сообщение в канале.
        """
        pattern_path = get_settings().PATTERN_PATH / f"{channel_id}.json"

        if not os.path.exists(pattern_path):
            logger.info(pattern_path)
            logger.warning(f"Файл паттерн {channel_id}.json не найден")
            return False

        try:
            with open(pattern_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                patterns = data["patterns"]
                logger.info(f"Файл паттерн {channel_id}.json найден и загружен")

        except json.JSONDecodeError as e:
            logger.error(f"Ошибки формата паттерна {channel_id}.json: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибки при загрузке паттерна {channel_id}.json: {e}")
            return False

        for pattern in patterns:
            if pattern["id"] == pattern_id:
                chat_id = pattern["chat_id"]  # Группа комментариев
                response = pattern["response"]
                break
        else:
            logger.warning(f"Не удалось найти паттерн с ID: {pattern_id}")
            return False

        # Отправляем в группу комментариев с reply_to на сообщение в канале
        logger.info(f"chat_id={chat_id}, reply_to={reply_to}")
        message = await self.client.send_message(
            entity=chat_id,
            message=response,
            reply_to=reply_to
        )

        return message
