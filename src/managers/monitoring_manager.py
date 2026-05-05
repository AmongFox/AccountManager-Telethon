import asyncio
import json
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from telethon import TelegramClient, events, functions, types, hints
from telethon.tl.types import SendMessageTypingAction, SendMessageCancelAction, SendMessageRecordAudioAction, \
    SendMessageRecordRoundAction, SendMessageChooseStickerAction, SendMessageUploadVideoAction, \
    SendMessageUploadPhotoAction, SendMessageUploadDocumentAction, SendMessageGeoLocationAction, \
    SendMessageGamePlayAction, UserStatusOnline, UserStatusOffline, UserStatusRecently, UserProfilePhotoEmpty, \
    UserStatusLastMonth, UserStatusLastWeek

from src.core import get_settings, get_logger

logger = get_logger()


def _load_index(index_file: Path) -> dict:
    """Загружает индекс-файл или создаёт пустой."""
    if index_file.exists():
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Ошибка чтения индекса {index_file}: {e}")
    return {"downloaded_items": [], "last_check": None}


def _save_index(index_file: Path, index: dict):
    """Сохраняет индекс-файл."""
    index_file.parent.mkdir(parents=True, exist_ok=True)
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def _load_username_map() -> dict:
    """Загружает маппинг username -> user_id и access_hash."""
    map_file = get_settings().MANAGERS_PATH / "monitoring" / "username_map.json"
    if map_file.exists():
        try:
            with open(map_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Ошибка чтения username_map: {e}")
    return {}


def _save_username_map(username_map: dict):
    """Сохраняет маппинг username -> user_id и access_hash."""
    map_file = get_settings().MANAGERS_PATH / "monitoring" / "username_map.json"
    map_file.parent.mkdir(parents=True, exist_ok=True)
    with open(map_file, 'w', encoding='utf-8') as f:
        json.dump(username_map, f, ensure_ascii=False, indent=2)


async def _resolve_target_users(client: TelegramClient, user_check_path: Path) -> dict:
    """
    Загружает список пользователей (ID и username) из файла.
    Для username получает user_id и access_hash.
    Возвращает dict: {user_id: {'username': str|None, 'access_hash': int|None}}
    Поддерживает разделители: точка с запятой (;) и новая строка.
    """
    if not user_check_path.exists():
        logger.warning(f"Файл не найден: {user_check_path}")
        return {}

    with open(user_check_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Разделяем по ; или новой строке
    raw_entries = []
    for line in content.split('\n'):
        # Каждая строка может содержать несколько записей через ;
        raw_entries.extend(line.split(';'))

    # Очищаем от пробелов и пустых
    entries = [e.strip() for e in raw_entries if e.strip()]

    # Загружаем сохранённый маппинг
    username_map = _load_username_map()
    result = {}

    for entry in entries:
        entry = entry.lstrip('@')  # Убираем @ если есть

        # Проверяем, это ID или username
        if entry.isdigit():
            # Это ID
            user_id = int(entry)
            result[user_id] = {'username': None, 'access_hash': None}
            logger.info(f"Добавлен пользователь по ID: {user_id}")
        else:
            # Это username - пробуем получить данные
            try:
                user = await client.get_entity(entry)
                user_id = user.id
                access_hash = user.access_hash

                result[user_id] = {
                    'username': user.username,
                    'access_hash': access_hash
                }

                # Сохраняем в маппинг для будущего
                username_map[entry.lower()] = {
                    'user_id': user_id,
                    'access_hash': access_hash
                }

                logger.info(f"Получен user_id={user_id} для @{entry}")

            except Exception as e:
                logger.warning(f"Не удалось получить @{entry}: {e}")
                continue

    # Сохраняем обновлённый маппинг
    _save_username_map(username_map)

    return result


class MonitoringAccountManager:
    def __init__(self, client: TelegramClient):
        self.config = get_settings()
        self.client: TelegramClient = client
        self.scheduler = AsyncIOScheduler()

    async def start_user_listener(self):
        """
        Слушает обновления пользователей.
        Поддерживает ID и username в файле logging_user_updates.txt
        """
        target_users = set()

        user_updates_path = get_settings().MANAGERS_PATH / "monitoring" / "logging_user_updates.txt"

        if user_updates_path.exists():
            with open(user_updates_path, 'r', encoding='utf-8') as users_file:
                entries = [e.strip() for e in users_file.read().split(';') if e.strip()]

            # Загружаем сохранённый маппинг
            username_map = _load_username_map()

            for entry in entries:
                entry = entry.lstrip('@')
                if not entry:
                    continue

                if entry.isdigit():
                    # Это ID
                    target_users.add(int(entry))
                    logger.info(f"Добавлен пользователь по ID: {entry}")
                else:
                    # Это username — пробуем получить ID
                    # Сначала проверяем в маппинге
                    if entry.lower() in username_map:
                        user_id = username_map[entry.lower()]['user_id']
                        target_users.add(user_id)
                        logger.info(f"Добавлен пользователь @{entry} (ID: {user_id} из маппинга)")
                    else:
                        # Получаем через Telegram
                        try:
                            user = await self.client.get_entity(entry)
                            user_id = user.id
                            access_hash = user.access_hash

                            target_users.add(user_id)
                            logger.info(f"Добавлен пользователь @{entry} (ID: {user_id})")

                            # Сохраняем в маппинг
                            username_map[entry.lower()] = {
                                'user_id': user_id,
                                'access_hash': access_hash
                            }
                        except Exception as e:
                            logger.warning(f"Не удалось получить @{entry}: {e}")

            # Сохраняем обновлённый маппинг
            _save_username_map(username_map)

        else:
            logger.warning(f"Файл не найден: {user_updates_path}")

        if not target_users:
            logger.info("Нет пользователей для отслеживания обновлений")
            return

        logger.info(f"Отслеживаем пользователей: {list(target_users)}")

        @self.client.on(events.UserUpdate(chats=list(target_users)))
        async def user_update_handler(event: events.UserUpdate.Event):
            logger.info(f"Обновление пользователя: {event}")

            # Получаем user_id из события
            user_id = event.user_id
            action = event.action
            status = event.status
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

            if isinstance(status, UserStatusOnline):
                message_action = "зашёл в сеть"
            elif isinstance(status, UserStatusOffline):
                message_action = "вышел из сети"
            elif isinstance(status, UserStatusRecently):
                message_action = "установил недавно"
            elif isinstance(action, SendMessageTypingAction):
                message_action = "пишет сообщение"
            elif isinstance(action, SendMessageRecordAudioAction):
                message_action = "записывает голосовое"
            elif isinstance(action, SendMessageRecordRoundAction):
                message_action = "записывает видеосообщение"
            elif isinstance(action, SendMessageChooseStickerAction):
                message_action = "выбирает стикер"
            elif isinstance(action, SendMessageUploadPhotoAction):
                message_action = "отправляет фото"
            elif isinstance(action, SendMessageUploadVideoAction):
                message_action = "отправляет видео"
            elif isinstance(action, SendMessageUploadDocumentAction):
                message_action = "отправляет документ"
            elif isinstance(action, SendMessageGeoLocationAction):
                message_action = "отправляет геопозицию"
            elif isinstance(action, SendMessageGamePlayAction):
                message_action = "играет в игру"
            elif isinstance(action, SendMessageCancelAction):
                message_action = "отменил действие"
            else:
                message_action = "неопределенно"

            log_file_path = get_settings().USERS_PATH / f"{user_id}" / "monitoring" / "logging_user_updates" / "updates.log"

            if not log_file_path.exists():
                logger.warning(f"Файл лога не найден: {log_file_path}")
                log_file_path.parent.mkdir(parents=True, exist_ok=True)
                log_file_path.touch()
                logger.info("Создан новый файл лога")

            with open(log_file_path, 'a', encoding='utf-8') as log_file:
                log_file.write(f"[{current_time}] Пользователь {user_id} {message_action}\n")

    async def start_scheduler(self):
        """Запускается вместе с приложением."""
        self.scheduler.add_job(
            self._check_users_data,
            trigger=IntervalTrigger(seconds=20),
            id='check_users',
            name='Проверка пользователей',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info("Планировщик задач запущен (интервал: 12 часов )")

    async def _check_users_data(self):
        """
        Запланированная проверка пользователей.
        Поддерживает ID и username в файле user_check_scheduler.txt.
        Для username автоматически получает user_id и access_hash.
        """
        logger.info("Запланированная проверка пользователей")

        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        current_time_for_path = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")

        user_check_path = get_settings().MANAGERS_PATH / "monitoring" / "user_check_scheduler.txt"

        # Получаем список пользователей (поддерживает ID и username)
        target_users = await _resolve_target_users(self.client, user_check_path)

        if not target_users:
            logger.warning("Нет пользователей для проверки")
            return

        logger.info(f"Пользователи для проверки: {list(target_users.keys())}")

        # Загружаем диалоги для кэширования access_hash
        logger.info("Загрузка диалогов для кэширования access_hash...")
        try:
            await self.client.get_dialogs()
        except Exception as e:
            logger.error(f"Ошибка при загрузке диалогов: {e}")

        for user_id, user_data in target_users.items():
            username = f"@{user_data['username']}" if user_data['username'] else "@None"
            logger.info("")
            logger.info(f"Пользователь: {user_id} ({username})")
            try:
                try:
                    # Если есть access_hash, используем его
                    if user_data['access_hash']:
                        from telethon.tl.types import InputPeerUser
                        peer = InputPeerUser(user_id, user_data['access_hash'])
                        user = await self.client.get_entity(peer)
                        logger.info(f"Получен через access_hash: {user_data['access_hash']}")
                    else:
                        # Пробуем напрямую по ID
                        user = await self.client.get_entity(entity=user_id)
                        logger.info("Получен напрямую по ID")

                except ValueError as e:
                    # Не удалось получить — пробуем через диалоги/контакты
                    logger.warning(f"Не удалось получить пользователя {user_id}: {e}")
                    logger.info(f"Пропускаем пользователя {user_id} — добавьте его в контакты, диалоги или используйте username")
                    continue

                logger.info(f"Получены данные пользователя {user_id}")

                username_str = user.username if user.username else f"None"

                user_dir = get_settings().USERS_PATH / f"{user_id}_{username_str}"

                current_dir = (
                    user_dir
                    / "monitoring"
                    / "user_check_scheduler"
                    / "logs"
                    / f"{current_time_for_path}"
                )
                images_dir = current_dir / "images"
                publications_dir = current_dir / "publications"
                stories_dir = publications_dir / "stories"
                log_file = current_dir / "data.log"

                # Постоянная директория для индексов: /monitoring/user_check_scheduler/
                user_base_dir = (
                    user_dir
                    / "monitoring"
                    / "user_check_scheduler"
                )
                user_base_dir.mkdir(parents=True, exist_ok=True)

                # Создание директорий
                current_dir.mkdir(parents=True, exist_ok=True)
                images_dir.mkdir(parents=True, exist_ok=True)
                stories_dir.mkdir(parents=True, exist_ok=True)

                # Сохранение фотографий профиля
                await self._download_user_photos(user, images_dir, user_base_dir, current_time_for_path)

                # Запись данных пользователя в лог
                await self._write_user_data_to_log(user, log_file, current_time)

                # Скачивание историй пользователя
                await self._download_user_stories(user, stories_dir, user_base_dir, current_time_for_path)

            except Exception as e:
                logger.error(f"Ошибка при проверке пользователя {user_id}: {e}", exc_info=True)

    async def _download_user_photos(self, user, images_dir: Path, user_base_dir: Path, timestamp_str: str):
        """
        Скачивает только новые фотографии профиля пользователя.
        Формат: photo_<photo_id>_<%d-%m-%Y_%H-%M-%S>.jpg
        Загрузка происходит параллельно (до 5 фото одновременно).
        Использует отдельный индекс для каждого пользователя.
        """
        if not user.photo or isinstance(user.photo, UserProfilePhotoEmpty):
            logger.warning(f"У пользователя {user.id} нет фотографий профиля")
            return

        try:
            # Загрузка индекса (единый файл photo_index.json)
            index_file = user_base_dir / "photo_index.json"
            index = _load_index(index_file)
            downloaded_photo_ids = {item["photo_id"] for item in index.get("downloaded_items", [])}

            # Получаем все фотографии профиля
            photos = await self.client.get_profile_photos(user.id, limit=100)

            if not photos:
                logger.info(f"У пользователя {user.id} нет фотографий для скачивания")
                return

            # Фильтруем только новые фотографии
            new_photos = [p for p in photos if p.id not in downloaded_photo_ids]
            skipped_count = len(photos) - len(new_photos)

            if skipped_count > 0:
                logger.info(f"Пропущено уже скачанных фотографий: {skipped_count}")

            if not new_photos:
                logger.info(f"У пользователя {user.id} нет новых фотографий")
                index["last_check"] = datetime.now().isoformat()
                _save_index(index_file, index)
                return

            logger.info(f"Найдено новых фотографий для скачивания: {len(new_photos)} (всего: {len(photos)})")

            # Ограничитель одновременных загрузок (до 5 фото параллельно)
            semaphore = asyncio.Semaphore(5)
            downloaded_count = 0
            new_items = []

            async def download_photo(photo) -> bool:
                """Скачивает одно фото с ограничением через semaphore."""
                nonlocal downloaded_count
                async with semaphore:
                    try:
                        # Формат: photo_<photo_id>_<%d-%m-%Y_%H-%M-%S>.jpg
                        file_path = images_dir / f"photo_{photo.id}_{timestamp_str}.jpg"

                        result = await self.client.download_media(photo, file=str(file_path))
                        if result:
                            logger.info(f"Скачано фото (ID: {photo.id}): {file_path}")
                            downloaded_count += 1
                            new_items.append({
                                "photo_id": photo.id,
                                "filename": file_path.name,
                                "date": timestamp_str
                            })
                            return True
                        else:
                            logger.warning(f"Не удалось скачать фото (ID: {photo.id})")
                            return False
                    except Exception as e:
                        logger.error(f"Ошибка при скачивании фото (ID: {photo.id}): {e}", exc_info=True)
                        return False

            tasks = [download_photo(photo) for photo in new_photos]

            await asyncio.gather(*tasks)

            # Обновляем индекс
            index["downloaded_items"].extend(new_items)
            index["last_check"] = datetime.now().isoformat()
            _save_index(index_file, index)

            logger.info(f"Скачано новых фотографий: {downloaded_count}/{len(new_photos)} (пропущено: {skipped_count})")

        except Exception as e:
            logger.error(f"Ошибка при получении фотографий профиля: {e}", exc_info=True)

    async def _download_user_stories(self, user, stories_dir: Path, user_base_dir: Path, timestamp_str: str):
        """
        Скачивает только новые истории (stories) пользователя.
        Формат: story_<story_id>_<%d-%m-%Y_%H-%M-%S>.jpg/mp4
        Загрузка происходит параллельно (до 5 историй одновременно).
        Использует отдельный индекс для каждого пользователя.
        """
        try:
            # Получаем все истории пользователя через GetUserStoriesRequest
            if not hasattr(user, 'stories_max_id') or user.stories_max_id is None:
                logger.warning(f"У пользователя {user.id} нет историй")
                return

            logger.info(f"Получаем истории пользователя {user.id} (max_id={user.stories_max_id})")

            result = await self.client(functions.stories.GetPeerStoriesRequest(
                peer=user.id
            ))

            logger.info(f"Result type: {type(result)}, result: {result}")

            if not result:
                logger.info(f"У пользователя {user.id} нет доступных историй (result=None)")
                return

            # result.stories -> PeerStories, result.stories.stories -> список StoryItem
            if hasattr(result, 'stories') and result.stories:
                if hasattr(result.stories, 'stories'):
                    stories = result.stories.stories
                else:
                    stories = result.stories if isinstance(result.stories, list) else []
            else:
                stories = []

            if not stories:
                logger.info(f"У пользователя {user.id} нет доступных историй")
                return

            index_file = user_base_dir / f"stories_index_{user.id}.json"
            index = _load_index(index_file)
            downloaded_story_ids = {item["story_id"] for item in index.get("downloaded_items", [])}

            new_stories = [s for s in stories if s.id not in downloaded_story_ids]
            skipped_count = len(stories) - len(new_stories)

            if skipped_count > 0:
                logger.info(f"Пропущено уже скачанных историй: {skipped_count}")

            if not new_stories:
                logger.info(f"У пользователя {user.id} нет новых историй")
                index["last_check"] = datetime.now().isoformat()
                _save_index(index_file, index)
                return

            logger.info(f"Найдено новых историй для скачивания: {len(new_stories)} (всего: {len(stories)})")

            # Ограничитель одновременных загрузок (до 5 историй параллельно)
            semaphore = asyncio.Semaphore(5)
            downloaded_count = 0
            new_items = []

            async def download_story(story) -> bool:
                """Скачивает одну историю с ограничением через semaphore."""
                nonlocal downloaded_count
                async with semaphore:
                    try:
                        story_id = story.id

                        # Определяем тип медиа и расширение
                        media = story.media
                        extension = "jpg"

                        # Проверяем тип контента
                        if isinstance(media, types.MessageMediaPhoto):
                            extension = "jpg"
                        elif isinstance(media, types.MessageMediaDocument):
                            if media.document and hasattr(media.document, 'attributes'):
                                for attr in media.document.attributes:
                                    if isinstance(attr, types.DocumentAttributeVideo):
                                        extension = "mp4"
                                        break

                        # Формат: story_<story_id>_<%d-%m-%Y_%H-%M-%S>.ext
                        file_path = stories_dir / f"story_{story_id}_{timestamp_str}.{extension}"

                        result = await self.client.download_media(media, file=str(file_path))
                        if result:
                            logger.info(f"Скачана история #{story_id}: {file_path}")
                            downloaded_count += 1
                            new_items.append({
                                "story_id": story_id,
                                "filename": file_path.name,
                                "date": timestamp_str,
                                "extension": extension
                            })
                            return True
                        else:
                            logger.warning(f"Не удалось скачать историю #{story_id}")
                            return False
                    except Exception as e:
                        logger.error(f"Ошибка при скачивании истории: {e}", exc_info=True)
                        return False

            tasks = [download_story(story) for story in new_stories]

            await asyncio.gather(*tasks)

            # Обновляем индекс
            index["downloaded_items"].extend(new_items)
            index["last_check"] = datetime.now().isoformat()
            _save_index(index_file, index)

            logger.info(f"Скачано новых историй: {downloaded_count}/{len(new_stories)} (пропущено: {skipped_count})")

        except Exception as e:
            logger.error(f"Ошибка при получении историй: {e}", exc_info=True)

    async def _write_user_data_to_log(self, user: hints.Entity, log_file: Path, current_time: str):
        """Записывает данные пользователя в лог-файл."""
        status_str = "Неизвестно"
        was_online = None

        if hasattr(user, 'status') and user.status:
            if isinstance(user.status, UserStatusOnline):
                status_str = "Online (в сети)"
            elif isinstance(user.status, UserStatusOffline):
                status_str = "Offline (не в сети)"
                was_online_dt = user.status.was_online
                if was_online_dt is None:
                    was_online = "—"
                elif isinstance(was_online_dt, datetime):
                    was_online = was_online_dt.strftime("%d.%m.%Y %H:%M:%S")
                else:
                    was_online = str(was_online_dt)
            elif isinstance(user.status, UserStatusRecently):
                status_str = "Recently (недавно)"
            elif isinstance(user.status, UserStatusLastMonth):
                status_str = "LastMonth (в течение месяца)"
            elif isinstance(user.status, UserStatusLastWeek):
                status_str = "LastWeek (в течение недели)"
            else:
                status_str = type(user.status).__name__

        # Формирование данных для записи
        data = {
            "Время проверки": current_time,

            "ID пользователя": user.id,
            "Имя": user.first_name or "Нет данных",
            "Фамилия": user.last_name or "Нет данных",
            "Юзернейм": f"@{user.username}" if user.username else "Нет данных",
            "Телефон": user.phone or "Нет данных",
            "Статус": status_str,
            "Был онлайн": was_online or "—",

            "Я (текущий пользователь)": "Да" if user.is_self else "Нет",
            "Бот": "Да" if user.bot else "Нет",
            "Аккаунт поддержки": "Да" if user.support else "Нет",
            "Подозрение мошенничества": "Да" if user.scam else "Нет",
            "Фейковый аккаунт": "Да" if user.fake else "Нет",

            "В контактах": "Да" if user.contact else "Нет",
            "Взаимный контакт": "Да" if user.mutual_contact else "Нет",

            "Близкий друг": "Да" if user.close_friend else "Нет",

            "Premium": "Да" if user.premium else "Нет",
            "Верифицирован": "Да" if user.verified else "Нет",
            "Ограничен": "Да" if user.restricted else "Нет",
            "Причина ограничения: ": f"{user.restriction_reason}" if user.restriction_reason else "Нет данных",
            "Удалён": "Да" if user.deleted else "Нет",

            "Премиум для связи": "Да" if user.contact_require_premium else "Нет",

            "Язык": user.lang_code or "Не указан",
            "Access Hash": user.access_hash,

            "Истории (max ID)": user.stories_max_id if hasattr(user, 'stories_max_id') and user.stories_max_id else "Нет",
            "Истории скрыты": "Да" if user.stories_hidden else "Нет",
            "Истории недоступны": "Да" if user.stories_unavailable else "Нет",
        }

        # Добавление информации о фото
        if user.photo:
            from telethon.tl.types import UserProfilePhotoEmpty
            if not isinstance(user.photo, UserProfilePhotoEmpty):
                data["Фото профиля"] = "Есть"
                data["DC ID фото"] = getattr(user.photo, 'dc_id', 'Не указан')
                data["Есть видео"] = "Да" if getattr(user.photo, 'has_video', False) else "Нет"
                data["Photo ID"] = getattr(user.photo, 'photo_id', 'Не указан')
            else:
                data["Фото профиля"] = "Нет"
        else:
            data["Фото профиля"] = "Нет"

        with open(log_file, 'w', encoding='utf-8') as file:
            file.write("=" * 60 + "\n")
            file.write(f"ОТЧЁТ ПРОВЕРКИ ПОЛЬЗОВАТЕЛЯ\n")
            file.write("=" * 60 + "\n\n")

            for key, value in data.items():
                file.write(f"{key}: {value}\n")

            file.write("\n" + "=" * 60 + "\n")
            file.write("Конец отчёта\n")
            file.write("=" * 60 + "\n")

        logger.info(f"Данные пользователя {user.id} записаны в {log_file}")

    async def __aenter__(self):
        """
        Проверяет и создаёт все необходимые директории для мониторинга.
        Вызывается при инициализации перед началом работы.
        """
        me = await self.client.get_me()
        self.user_id = me.id

        # Директории для текущего пользователя
        base_path = get_settings().USERS_PATH / f"{self.user_id}"
        
        dirs = [
            base_path / "monitoring" / "logging_user_updates" / "logs",
            base_path / "monitoring" / "user_check_scheduler" / "logs",
        ]

        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Директория проверена: {dir_path}")

        # Файлы
        users_files = [
            base_path / "monitoring" / "logging_user_updates" / "users.txt",
            base_path / "monitoring" / "user_check_scheduler" / "users.txt",
        ]

        for file_path in users_files:
            if not file_path.exists():
                file_path.touch()
                logger.info(f"Создан файл: {file_path}")

        logger.info(f"Все директории для мониторинга проверены и созданы (user_id={self.user_id})")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Остановка планировщика при выходе из контекста."""
        if self.scheduler.running:
            self.scheduler.shutdown()
        return self
