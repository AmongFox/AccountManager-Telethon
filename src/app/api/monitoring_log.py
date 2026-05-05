from fastapi import APIRouter, HTTPException
from pathlib import Path

from src.core import get_logger, get_settings

logger = get_logger()
settings = get_settings()

router = APIRouter(prefix="/monitoring")


@router.get("/{user_id}/logs")
async def get_log_updates(user_id: int):
    """Получить логи обновлений пользователя"""
    logger.info(f"Поступил запрос: user_id={user_id}")

    filepath: Path = settings.USERS_PATH / f"{user_id}" / "monitoring" / "logging_user_updates" / "updates.log"

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Лог файл не найден: {filepath}")

    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            text = file.read()
    except Exception as e:
        logger.error(f"Ошибка чтения файла: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка чтения файла: {str(e)}")

    return {
        "message": "success",
        "data": text
    }
