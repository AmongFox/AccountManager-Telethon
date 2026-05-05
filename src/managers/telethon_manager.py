from typing import Union, Optional, Dict

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from src.core import get_settings, get_logger

logger = get_logger()


class TelethonAccountManager:
    def __init__(self):
        self.config = get_settings()
        self._auth_clients: Dict[int, TelegramClient] = {}

    async def fast_login(self, session_name: str) -> Union[TelegramClient | None]:
        """Быстрый вход по существующей сессии без аутентификации."""
        logger.info(f"Быстрый вход в сессию: {session_name}")
        client = await self._create_client(session_name)
        await client.connect()

        if not await client.is_user_authorized():
            logger.warning(f"Сессия {session_name} не авторизована")
            return

        logger.info(f"Успешный вход в сессию: {session_name}")
        return client

    async def authentication(
        self,
        user_id: int,
        method: str,
        phone: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Начать аутентификацию (phone или qr).
        
        Args:
            user_id: ID пользователя в БД
            method: 'phone' или 'qr'
            phone: номер телефона (для method='phone')
            
        Returns:
            Dict со статусом и данными для следующего шага
        """
        session_name = f"user_{user_id}"
        client = await self._create_client(session_name)
        await client.connect()
        
        if await client.is_user_authorized():
            logger.warning(f"Пользователь {user_id} уже авторизован")
            await client.disconnect()
            return {"status": "already_authorized", "session_name": session_name}
        
        self._auth_clients[user_id] = client
        
        if method == "phone":
            if not phone:
                return {"status": "error", "message": "Требуется номер телефона"}
            
            logger.info(f"Отправка кода на номер {phone} для пользователя {user_id}")
            try:
                result = await client.send_code_request(phone=phone)
                logger.info(f"Код отправлен (phone_code_hash={result.phone_code_hash})")
                return {
                    "status": "code_sent",
                    "session_name": session_name,
                    "phone": phone,
                    "phone_code_hash": result.phone_code_hash
                }
            except Exception as e:
                logger.error(f"Ошибка отправки кода: {e}")
                return {"status": "error", "message": str(e)}
                
        elif method == "qr":
            logger.info(f"Генерация QR-кода для пользователя {user_id}")
            try:
                from telethon.tl.functions.auth import ExportLoginTokenRequest
                from telethon.tl.types import auth
                from telethon.utils import get_display_name
                
                token_request = ExportLoginTokenRequest(
                    api_id=self.config.API_ID,
                    api_hash=self.config.API_HASH,
                    except_ids=[]
                )
                result = await client(token_request)
                
                if isinstance(result, auth.LoginToken):
                    from base64 import b64encode
                    token = b64encode(result.token).decode('ascii')
                    url = f"tg://login?token={token}"
                    
                    return {
                        "status": "qr_generated",
                        "session_name": session_name,
                        "qr_url": url,
                        "token": token
                    }
                else:
                    return {"status": "error", "message": "Не удалось получить QR-токен"}
                    
            except Exception as e:
                logger.error(f"Ошибка генерации QR: {e}")
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": "Неподдерживаемый метод аутентификации"}

    async def confirm_authentication(
        self,
        user_id: int,
        session_name: str,
        code: str,
        password: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Подтвердить аутентификацию кодом.
        
        Args:
            user_id: ID пользователя в БД
            session_name: название сессии
            code: код из SMS/Telegram
            password: 2FA пароль (если требуется)
            
        Returns:
            Dict со статусом и данными авторизации
        """
        if user_id not in self._auth_clients:
            client = await self._create_client(session_name)
            await client.connect()
            self._auth_clients[user_id] = client
        else:
            client = self._auth_clients[user_id]
        
        try:
            logger.info(f"Подтверждение кода для пользователя {user_id}")
            
            if password:
                await client.sign_in(password=password)
            else:
                await client.sign_in(code=code)
            
            if await client.is_user_authorized():
                me = await client.get_me()
                logger.info(f"Пользователь {me.id} (@{me.username}) успешно авторизован")
                
                await client.disconnect()
                del self._auth_clients[user_id]
                
                return {
                    "status": "authorized",
                    "session_name": session_name,
                    "user_id": me.id,
                    "username": me.username,
                    "first_name": me.first_name,
                    "last_name": me.last_name
                }
            else:
                return {"status": "error", "message": "Авторизация не удалась"}
                
        except SessionPasswordNeededError:
            logger.info(f"Требуется 2FA пароль для пользователя {user_id}")
            return {
                "status": "password_needed",
                "session_name": session_name,
                "message": "Требуется двухфакторный пароль"
            }
        except PhoneCodeInvalidError:
            logger.warning(f"Неверный код для пользователя {user_id}")
            return {"status": "error", "message": "Неверный код подтверждения"}
        except Exception as e:
            logger.error(f"Ошибка подтверждения кода: {e}")
            return {"status": "error", "message": str(e)}

    async def cancel_authentication(self, user_id: int) -> bool:
        """Отменить процесс аутентификации."""
        if user_id in self._auth_clients:
            client = self._auth_clients[user_id]
            await client.disconnect()
            del self._auth_clients[user_id]
            logger.info(f"Аутентификация пользователя {user_id} отменена")
            return True
        return False

    async def _create_client(self, session_name: str) -> TelegramClient:
        """Создать клиента с опциональным прокси"""
        client_kwargs = {
            "session": str(self.config.SESSIONS_PATH / session_name),
            "api_id": self.config.API_ID,
            "api_hash": self.config.API_HASH,
            "system_version": self.config.SYSTEM_VERSION,
            "device_model": self.config.DEVICE_MODEL,
        }

        # Добавляем прокси если включен
        if self.config.PROXY_ENABLED:
            from telethon import connection

            client_kwargs["connection"] = connection.ConnectionTcpMTProxySecretLike

            # Парсим секрет прокси
            secret = self._parse_proxy_secret(self.config.PROXY_SECRET)

            client_kwargs["proxy"] = (
                self.config.PROXY_SERVER,
                self.config.PROXY_PORT,
                secret
            )

            logger.info(
                f"Прокси включен: {self.config.PROXY_SERVER}:{self.config.PROXY_PORT}"
            )

        client = TelegramClient(**client_kwargs)
        return client

    @staticmethod
    def _parse_proxy_secret(secret: str) -> bytes:
        """
        Распарсить секрет прокси из формата dd/dddd...

        Telegram proxy secret может быть в формате:
        - dd ee9a4f23b1d768c04a8d7f39120ca5f6e626973636f7474692e79656b74616e65742e636f6d
        - eee9a4f23b1d768c04a8d7f39120ca5f6e626973636f7474692e79656b74616e65742e636f6d
        """
        # Удаляем пробелы и приводим к нижнему регистру
        secret = secret.replace(" ", "").lower()

        # Если есть префикс dd, убираем его
        if secret.startswith("dd"):
            secret = secret[2:]

        # Конвертируем hex в bytes
        try:
            return bytes.fromhex(secret)
        except ValueError:
            # Если не hex, пробуем как строку
            logger.warning("Секрет прокси не в hex формате, используем как строку")
            return secret.encode() if isinstance(secret, str) else secret
