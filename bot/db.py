import asyncpg
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Получаем строку подключения к базе данных из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL is None:
    raise ValueError("Не указана DATABASE_URL в переменных окружения")

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def get_db_connection():
    """Функция для получения соединения с базой данных."""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        logger.info("Соединение с базой данных установлено.")
        return conn
    except Exception as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
        return None

async def create_table():
    """Функция для создания таблицы задач в базе данных."""
    conn = await get_db_connection()
    if conn:
        try:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    text TEXT NOT NULL,
                    due_date TIMESTAMP NOT NULL
                )
            ''')
            logger.info("Таблица 'tasks' успешно создана или уже существует.")
        except Exception as e:
            logger.error(f"Ошибка при создании таблицы: {e}")
        finally:
            await conn.close()
            logger.info("Соединение с базой данных закрыто.")

async def create_task(user_id, text, due_date):
    """Функция для создания новой задачи в базе данных."""
    conn = await get_db_connection()
    if conn:
        try:
            result = await conn.fetch('''
                INSERT INTO tasks (user_id, text, due_date) 
                VALUES ($1, $2, $3) RETURNING id
            ''', user_id, text, due_date)
            task_id = result[0]['id']
            logger.info(f"Задача создана с ID: {task_id}")
            return task_id
        except Exception as e:
            logger.error(f"Ошибка при создании задачи: {e}")
        finally:
            await conn.close()
            logger.info("Соединение с базой данных закрыто.")

async def get_tasks(user_id):
    """Функция для получения всех задач пользователя."""
    conn = await get_db_connection()
    if conn:
        try:
            rows = await conn.fetch('''
                SELECT id, text, due_date FROM tasks WHERE user_id = $1
            ''', user_id)
            logger.info(f"Полученные задачи: {rows}")
            return rows
        except Exception as e:
            logger.error(f"Ошибка при получении задач: {e}")
            return []
        finally:
            await conn.close()
            logger.info("Соединение с базой данных закрыто.")

async def delete_task(task_id):
    """Функция для удаления задачи по ID."""
    conn = await get_db_connection()
    if conn:
        try:
            await conn.execute('''
                DELETE FROM tasks WHERE id = $1
            ''', task_id)
            logger.info(f"Задача с ID {task_id} удалена.")
        except Exception as e:
            logger.error(f"Ошибка при удалении задачи: {e}")
        finally:
            await conn.close()
            logger.info("Соединение с базой данных закрыто.")

async def update_task(task_id, new_text, new_due_date):
    """Функция для обновления существующей задачи."""
    conn = await get_db_connection()
    if conn:
        try:
            await conn.execute('''
                UPDATE tasks 
                SET text = $1, due_date = $2 
                WHERE id = $3
            ''', new_text, new_due_date, task_id)
            logger.info(f"Задача с ID {task_id} обновлена.")
        except Exception as e:
            logger.error(f"Ошибка при обновлении задачи: {e}")
        finally:
            await conn.close()
            logger.info("Соединение с базой данных закрыто.")
