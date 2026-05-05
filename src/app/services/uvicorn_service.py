import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core import get_settings, get_logger
from src.app.api import monitoring_router

logger = get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Запуск UVICORN {get_settings().APP_NAME}")
    yield
    logger.info(f"Остановка UVICORN {get_settings().APP_NAME}")


def create_application():
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.cors_methods_list,
        allow_headers=settings.cors_headers_list,
    )

    routers = [monitoring_router]

    for router in routers:
        application.include_router(router)

    return application


class UvicornService:
    """Асинхронный сервис для запуска FastAPI"""
    
    def __init__(self):
        self.app = create_application()
        self.server: Optional[uvicorn.Server] = None
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Запуск сервера в фоновом режиме"""
        config = uvicorn.Config(
            app=self.app,
            host=settings.UVICORN_SERVICE_HOST,
            port=settings.UVICORN_SERVICE_PORT,
            log_level="info",
            access_log=False,
            loop="asyncio"
        )
        
        self.server = uvicorn.Server(config)
        
        logger.info(
            f"FastAPI запущен на http://{settings.UVICORN_SERVICE_HOST}:{settings.UVICORN_SERVICE_PORT}"
        )
        
        self._task = asyncio.create_task(self.server.serve())
        
        # Даём серверу время на запуск
        await asyncio.sleep(0.5)
    
    async def stop(self):
        """Остановка сервера"""
        if self.server:
            self.server.should_exit = True
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("FastAPI остановлен")


# Глобальный экземпляр сервиса
_uvicorn_service: Optional[UvicornService] = None


def get_uvicorn_service() -> UvicornService:
    """Получить экземпляр сервиса"""
    global _uvicorn_service
    if _uvicorn_service is None:
        _uvicorn_service = UvicornService()
    return _uvicorn_service


def run():
    """Синхронная функция для прямого запуска (блокирующая)"""
    application = create_application()
    uvicorn.run(
        app=application,
        host=settings.UVICORN_SERVICE_HOST,
        port=settings.UVICORN_SERVICE_PORT,
        log_level="info"
    )


if __name__ == '__main__':
    run()
