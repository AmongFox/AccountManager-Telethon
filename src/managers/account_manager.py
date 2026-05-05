from typing import Optional, Dict

from telethon import TelegramClient

from src.core import get_logger
from .telethon_manager import TelethonAccountManager
from .automation_manager import AutomationAccountManager
from .monitoring_manager import MonitoringAccountManager
from .secure_manager import SecureAccountManager

logger = get_logger()


class AccountManager:
    """
    Единая точка входа для управления аккаунтом.
    Координирует работу всех менеджеров.
    
    Пример использования:
        async with AccountManager() as manager:
            client = await manager.fast_login("session_name")
            await manager.start_automation()
            await manager.start_monitoring()
    """

    def __init__(self):
        self.telethon = TelethonAccountManager()
        self.client: Optional[TelegramClient] = None
        self.session_name: str = ""
        
        # Менеджеры инициализируются после получения клиента
        self._automation: Optional[AutomationAccountManager] = None
        self._monitoring: Optional[MonitoringAccountManager] = None
        self._secure: Optional[SecureAccountManager] = None

    @property
    def automation(self) -> AutomationAccountManager:
        if self._automation is None:
            raise RuntimeError("Клиент не инициализирован. Вызовите fast_login() или connect()")
        return self._automation

    @property
    def monitoring(self) -> MonitoringAccountManager:
        if self._monitoring is None:
            raise RuntimeError("Клиент не инициализирован. Вызовите fast_login() или connect()")
        return self._monitoring

    @property
    def secure(self) -> SecureAccountManager:
        if self._secure is None:
            self._secure = SecureAccountManager()
        return self._secure

    async def fast_login(self, session_name: str) -> Optional[TelegramClient]:
        """Быстрый вход по существующей сессии."""
        self.session_name = session_name
        self.client = await self.telethon.fast_login(session_name)

        if not self.client:
            logger.warning(f"Не удалось войти в сессию: {session_name}")
            return None

        # Инициализируем зависимые менеджеры
        self._automation = AutomationAccountManager(self.client, session_name)
        self._monitoring = MonitoringAccountManager(self.client)
        self._secure = SecureAccountManager()

        logger.info(f"Успешный вход в сессию: {session_name}")
        return self.client

    async def authentication(self, user_id: int, method: str, phone: Optional[str] = None):
        """Начать аутентификацию (phone или qr)."""
        return await self.telethon.authentication(user_id, method, phone)

    async def confirm_authentication(
        self,
        user_id: int,
        session_name: str,
        code: str,
        password: Optional[str] = None
    ):
        """Подтвердить аутентификацию кодом."""
        return await self.telethon.confirm_authentication(user_id, session_name, code, password)

    async def cancel_authentication(self, user_id: int):
        """Отменить процесс аутентификации."""
        return await self.telethon.cancel_authentication(user_id)

    async def register_session(
        self,
        user_id: int,
        method: str,
        phone: Optional[str] = None,
        code: Optional[str] = None,
        password: Optional[str] = None
    ) -> Optional[TelegramClient]:
        """
        Полный цикл регистрации сессии.
        
        Args:
            user_id: ID пользователя в БД
            method: 'phone' или 'qr'
            phone: номер телефона (для method='phone')
            code: код подтверждения (если есть)
            password: 2FA пароль (если требуется)
            
        Returns:
            TelegramClient при успешной авторизации, None иначе
        """
        # Шаг 1: Начало аутентификации
        if not code:
            result = await self.authentication(user_id, method, phone)
            
            if result.get("status") == "already_authorized":
                logger.info(f"Сессия уже существует: {result['session_name']}")
                return await self.fast_login(result["session_name"])
            
            if result.get("status") != "code_sent" and result.get("status") != "qr_generated":
                logger.error(f"Ошибка начала аутентификации: {result}")
                return None
                
            return result  # Возвращаем результат для следующего шага
        
        # Шаг 2: Подтверждение кодом
        session_name = f"user_{user_id}"
        result = await self.confirm_authentication(user_id, session_name, code, password)
        
        if result.get("status") == "password_needed":
            logger.info("Требуется 2FA пароль")
            return result  # Клиент ждёт пароль
        
        if result.get("status") == "authorized":
            logger.info(f"Сессия зарегистрирована: {result['session_name']}")
            return await self.fast_login(result["session_name"])
        
        logger.error(f"Ошибка подтверждения: {result}")
        return None

    async def start_automation(self):
        """Запустить автоматизацию (прослушка каналов)."""
        await self.automation.start_channel_listener()
        logger.info("Автоматизация запущена")

    async def stop_automation(self):
        """Остановить автоматизацию."""
        await self.automation.stop_channel_listener()
        logger.info("Автоматизация остановлена")

    async def start_monitoring(self):
        """Запустить мониторинг пользователей."""
        await self.monitoring.start_user_listener()
        await self.monitoring.start_scheduler()
        logger.info("Мониторинг запущен")

    async def stop_monitoring(self):
        """Остановить мониторинг."""
        # shutdown() — синхронный метод, вызываем через run_in_executor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.monitoring.scheduler.shutdown)
        logger.info("Мониторинг остановлен")

    async def disconnect(self):
        """Отключить клиента и остановить все процессы."""
        await self.stop_automation()
        await self.stop_monitoring()
        
        if self.client:
            await self.client.disconnect()
            logger.info(f"Клиент отключён: {self.session_name}")

    async def __aenter__(self):
        """Инициализация менеджеров при входе в контекст."""
        # Если клиент уже инициализирован (например, через fast_login до входа в контекст),
        # создаём менеджеры
        if self.client:
            self._automation = AutomationAccountManager(self.client, self.session_name)
            self._monitoring = MonitoringAccountManager(self.client)
            self._secure = SecureAccountManager()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
