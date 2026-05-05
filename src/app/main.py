import asyncio

from src.managers import AccountManager
from src.app.services.uvicorn_service import get_uvicorn_service
from src.core import get_logger, get_settings

logger = get_logger()


async def main():
    settings = get_settings()

    if settings.UVICORN_SERVICE_ENABLED:
        uvicorn_service = get_uvicorn_service()
        await uvicorn_service.start()
    
    session_name = settings.SESSION_NAME
    phone_number = get_settings().PHONE_NUMBER
    app_id = get_settings().APP_ID

    async with AccountManager() as manager:
        logger.info(f"Название сессии: {session_name}")

        if not session_name:
            logger.info(f'phone {phone_number}')

            if not phone_number:
                raise "Ошибка во время получения номера телефона"

            logger.info("Аутентификация")

            result = await manager.authentication(user_id=app_id, method="phone", phone=phone_number)
            
            if result.get("status") == "code_sent":
                code = input("Введите код подтверждения: ")
                result = await manager.confirm_authentication(
                    user_id=app_id,
                    session_name=f"user_{app_id}",
                    code=code
                )
                logger.info(f"Результат подтверждения: {result}")
                
                if result.get("status") == "authorized":
                    session_name = f"user_{app_id}"
                elif result.get("status") == "password_needed":
                    password = input("Введите 2FA пароль: ")
                    result = await manager.confirm_authentication(
                        user_id=app_id,
                        session_name=f"user_{app_id}",
                        code=code,
                        password=password
                    )
                    if result.get("status") == "authorized":
                        session_name = f"user_{app_id}"
                    else:
                        logger.error("Ошибка авторизации с паролем")
                        return
                else:
                    logger.error("Ошибка авторизации")
                    return

            result = await manager.authentication(user_id=app_id, method="qr")
            if result.get("status") == "qr_generated":
                logger.info(f"QR-код: {result['qr_url']}")
                await asyncio.sleep(30)

        if not session_name:
            logger.error("Не удалось получить название сессии")
            return

        client = await manager.fast_login(session_name)

        if not client:
            logger.info(f"Не удалось войти в сессию: {session_name}")
            return

        me = await client.get_me()
        logger.info(f"User ID: {me.id} [{me.username}]")

        # Доступ к менеджерам напрямую
        # manager.automation - AutomationAccountManager
        # manager.monitoring - MonitoringAccountManager
        # manager.secure - SecureAccountManager
        # manager.telethon - TelethonAccountManager

        await manager.start_monitoring()

        logger.info("Приложение запущено")

        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        finally:
            # Остановка FastAPI сервиса
            if settings.UVICORN_SERVICE_ENABLED:
                uvicorn_service = get_uvicorn_service()
                await uvicorn_service.stop()


if __name__ == '__main__':
    asyncio.run(main())


