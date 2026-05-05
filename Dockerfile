FROM python:3.11-slim
LABEL authors="AF"

WORKDIR /app

# Установка системных зависимостей для psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY .env ./
COPY storage/ ./storage/

# Создание директории для логов
RUN mkdir -p /app/logs

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Скрипт запуска с обработкой ошибок
RUN echo '#!/bin/sh\n\
set -e\n\
echo "========================================"\n\
echo "Запуск Account Manager"\n\
echo "Время: $(date)"\n\
echo "========================================"\n\
\n\
# Проверка наличия файлов\n\
if [ ! -f "src/app/main.py" ]; then\n\
    echo "ОШИБКА: main.py не найден!"\n\
    exit 1\n\
fi\n\
\n\
echo "Запуск приложения..."\n\
exec python src/app/main.py' > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]
