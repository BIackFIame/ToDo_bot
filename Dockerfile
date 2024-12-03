# Stage 1: Build
FROM python:3.9-slim AS builder

WORKDIR /app

# Установка зависимостей
COPY requirements.txt ./
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Run
FROM python:3.9-slim

WORKDIR /app

# Копирование зависимостей из builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Копирование всего кода приложения
COPY . /app

# Запуск бота
CMD ["python", "bot/bot.py"]
