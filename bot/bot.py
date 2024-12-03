import logging
import os
import asyncio
from datetime import datetime, timedelta
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackContext, 
    CallbackQueryHandler, 
    ConversationHandler, 
    MessageHandler, 
    filters
)
from dotenv import load_dotenv
from db import create_task, get_tasks, create_table, delete_task, update_task
from dateutil.relativedelta import relativedelta

# Загрузка переменных окружения
load_dotenv()

# Получаем токен Telegram и строку подключения к базе данных из .env
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if TELEGRAM_TOKEN is None:
    raise ValueError("Не указан TELEGRAM_TOKEN в переменных окружения")
if DATABASE_URL is None:
    raise ValueError("Не указана DATABASE_URL в переменных окружения")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация асинхронного планировщика (AsyncIO Scheduler)
scheduler = AsyncIOScheduler()
scheduler.start()

# Состояния для ConversationHandler при редактировании задачи
EDIT_TASK_ID, EDIT_TASK_TEXT, EDIT_TASK_DUE_DATE = range(3)

# Функция для отправки напоминания
async def send_reminder(user_id: int, text: str):
    try:
        await application.bot.send_message(user_id, f"Напоминание: {text}")
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания: {e}")

# Постоянная inline клавиатура
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("Добавить задачу", callback_data='add_task')],
        [InlineKeyboardButton("Просмотреть задачи", callback_data='view_tasks')],
        [InlineKeyboardButton("Редактировать задачу", callback_data='edit_task')],
        [InlineKeyboardButton("Удалить задачу", callback_data='delete_task')],
        [InlineKeyboardButton("Помощь", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команда /start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я бот-напоминалка. Выберите действие ниже:",
        reply_markup=main_menu_keyboard()
    )

# Команда /help
async def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Команды:\n"
        "/start - Запуск бота и отображение меню\n"
        "/help - Помощь\n"
        "/add - Добавление задачи\n"
        "/tasks - Показать все задачи\n"
        "/edit - Редактировать задачу\n"
        "/delete - Удалить задачу\n\n"
        "Добавление задачи:\n"
        "Например:\n"
        "'/add 2024-12-05 14:30 Купить продукты'\n"
        "Или через время:\n"
        "'/add через 30 минут Проверить почту'\n"
        "Поддерживаемые единицы времени: секунды, минуты, часы, дни, недели, месяцы, годы"
    )
    # Определяем источник обновления
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if message:
        await message.reply_text(help_text)

# Callback обработчик для inline кнопок меню
async def main_menu_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'add_task':
        await query.edit_message_text(
            text="Введите задачу в формате:\n'/add <дата> <время> <текст>'\nили\n'/add через <количество> <единица времени> <текст>'\n\nПоддерживаемые единицы времени: секунды, минуты, часы, дни, недели, месяцы, годы"
        )
    elif data == 'view_tasks':
        await show_tasks_command(update, context)
    elif data == 'edit_task':
        await query.edit_message_text(text="Введите ID задачи, которую хотите отредактировать:")
        return EDIT_TASK_ID
    elif data == 'delete_task':
        await query.edit_message_text(
            text="Введите ID задачи, которую хотите удалить:\nИспользуйте команду '/delete <ID>'"
        )
    elif data == 'help':
        await help_command(update, context)
    return ConversationHandler.END


# Функция для добавления задачи через команду /add
async def add_task_command(update: Update, context: CallbackContext):
    try:
        user_id = update.message.from_user.id
        args = context.args

        if not args:
            await update.message.reply_text("Пожалуйста, предоставьте детали задачи. Используйте /help для справки.")
            return

        # Определение типа задачи
        if args[0].lower() in ['через', 'через-']:
            if len(args) < 4:
                await update.message.reply_text("Недостаточно аргументов для создания задачи. Используйте /help для справки.")
                return
            time_value = int(args[1])
            unit = args[2].lower()
            text = " ".join(args[3:])

            # Определение единицы времени
            units = {
                'секунды': 'seconds',
                'секунду': 'seconds',
                'секунд': 'seconds',
                'минуты': 'minutes',
                'минуту': 'minutes',
                'минут': 'minutes',
                'часа': 'hours',
                'час': 'hours',
                'часов': 'hours',
                'дни': 'days',
                'день': 'days',
                'дней': 'days',
                'недели': 'weeks',
                'неделю': 'weeks',
                'недель': 'weeks',
                'месяцы': 'months',
                'месяц': 'months',
                'месяцев': 'months',
                'годы': 'years',
                'год': 'years',
                'лет': 'years'
            }

            if unit not in units:
                await update.message.reply_text("Ошибка: Неверная единица времени.\nПоддерживаемые единицы: секунды, минуты, часы, дни, недели, месяцы, годы.")
                return

            unit_key = units[unit]

            # Создание delta
            if unit_key in ['seconds', 'minutes', 'hours', 'days', 'weeks']:
                delta = timedelta(**{unit_key: time_value})
            elif unit_key in ['months', 'years']:
                delta = relativedelta(**{unit_key: time_value})
            else:
                await update.message.reply_text("Ошибка: Неверная единица времени.")
                return

            due_date = datetime.now() + delta

        else:
            if len(args) < 3:
                await update.message.reply_text("Недостаточно аргументов для создания задачи. Используйте /help для справки.")
                return
            date_str = args[0]
            time_str = args[1]
            text = " ".join(args[2:])
            try:
                due_date = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            except ValueError:
                await update.message.reply_text("Неверный формат даты или времени. Используйте YYYY-MM-DD HH:MM.")
                return

        # Создание задачи в базе данных
        task_id = await create_task(user_id, text, due_date)

        # Настройка напоминания
        trigger = DateTrigger(run_date=due_date)
        scheduler.add_job(send_reminder, trigger, args=[user_id, text], id=str(task_id))
        logger.info(f"Задача добавлена: {text} на {due_date.strftime('%d-%m-%Y %H:%M')} с ID {task_id}")

        await update.message.reply_text(f"Задача добавлена: {text} на {due_date.strftime('%d-%m-%Y %H:%M')}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении задачи: {e}")
        await update.message.reply_text("Ошибка при добавлении задачи. Попробуйте снова.")

# Функция для отображения задач
async def show_tasks_command(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        tasks = await get_tasks(user_id)

        # Определяем источник обновления
        message = update.message or (update.callback_query.message if update.callback_query else None)

        if not tasks:
            if message:
                await message.reply_text("У вас нет задач.")
            return

        for task in tasks:
            task_id, text, due_date = task
            due_date_formatted = due_date.strftime("%d-%m-%Y %H:%M")
            keyboard = [
                [
                    InlineKeyboardButton("Редактировать", callback_data=f'edit_{task_id}'),
                    InlineKeyboardButton("Удалить", callback_data=f'delete_{task_id}')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if message:
                await message.reply_text(
                    f"ID: {task_id}\nТекст: {text}\nДо: {due_date_formatted}",
                    reply_markup=reply_markup
                )
    except Exception as e:
        logger.error(f"Ошибка при отображении задач: {e}")
        message = update.message or (update.callback_query.message if update.callback_query else None)
        if message:
            await message.reply_text("Ошибка при отображении задач. Попробуйте снова.")

# Функция для удаления задачи через команду /delete
async def delete_task_command(update: Update, context: CallbackContext):
    try:
        args = context.args
        if not args:
            await update.message.reply_text("Пожалуйста, укажите ID задачи для удаления. Используйте /help для справки.")
            return

        task_id = int(args[0])
        user_id = update.effective_user.id
        tasks = await get_tasks(user_id)

        if not any(task[0] == task_id for task in tasks):
            await update.message.reply_text(f"Задача с ID {task_id} не найдена.")
            return

        await delete_task(task_id)
        scheduler.remove_job(str(task_id))
        logger.info(f"Задача с ID {task_id} удалена.")

        await update.message.reply_text(f"Задача {task_id} удалена.")
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка при удалении задачи: {e}")
        await update.message.reply_text("Ошибка при удалении задачи. Попробуйте снова.")

# Редактирование задачи: шаг 1 - ввод ID
async def edit_task_id(update: Update, context: CallbackContext):
    try:
        task_id = int(update.message.text)
        user_id = update.effective_user.id
        tasks = await get_tasks(user_id)

        if not any(task[0] == task_id for task in tasks):
            await update.message.reply_text(f"Задача с ID {task_id} не найдена.")
            return ConversationHandler.END

        context.user_data['edit_task_id'] = task_id
        await update.message.reply_text("Введите новый текст задачи:")
        return EDIT_TASK_TEXT
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом. Пожалуйста, введите корректный ID:")
        return EDIT_TASK_ID
    except Exception as e:
        logger.error(f"Ошибка при вводе ID задачи для редактирования: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END

# Редактирование задачи: шаг 2 - ввод нового текста
async def edit_task_text(update: Update, context: CallbackContext):
    try:
        new_text = update.message.text
        context.user_data['edit_task_text'] = new_text
        await update.message.reply_text("Введите новую дату и время выполнения задачи (YYYY-MM-DD HH:MM):")
        return EDIT_TASK_DUE_DATE
    except Exception as e:
        logger.error(f"Ошибка при вводе нового текста задачи: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте снова.")
        return ConversationHandler.END

# Редактирование задачи: шаг 3 - ввод новой даты и времени
async def edit_task_due_date(update: Update, context: CallbackContext):
    try:
        due_date_str = update.message.text
        new_due_date = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M")
        task_id = context.user_data['edit_task_id']
        new_text = context.user_data['edit_task_text']

        # Обновление задачи в базе данных
        await update_task(task_id, new_text, new_due_date)

        # Обновление напоминания в планировщике
        try:
            scheduler.remove_job(str(task_id))
        except Exception as e:
            logger.warning(f"Не удалось удалить существующее задание из планировщика: {e}")

        trigger = DateTrigger(run_date=new_due_date)
        scheduler.add_job(send_reminder, trigger, args=[update.effective_user.id, new_text], id=str(task_id))
        logger.info(f"Задача {task_id} обновлена: {new_text} на {new_due_date.strftime('%d-%m-%Y %H:%M')}")

        await update.message.reply_text(f"Задача {task_id} обновлена.")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Неверный формат даты или времени. Пожалуйста, введите в формате YYYY-MM-DD HH:MM:")
        return EDIT_TASK_DUE_DATE
    except Exception as e:
        logger.error(f"Ошибка при обновлении даты и времени задачи: {e}")
        await update.message.reply_text("Произошла ошибка при обновлении задачи. Попробуйте снова.")
        return ConversationHandler.END

# Завершение редактирования задачи
async def cancel_edit(update: Update, context: CallbackContext):
    await update.message.reply_text("Редактирование задачи отменено.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# Функция обработки редактирования и удаления конкретных задач из списка
async def task_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith('edit_'):
        task_id = int(data.split('_')[1])
        context.user_data['edit_task_id'] = task_id
        await query.edit_message_text(text="Введите новый текст задачи:")
        return EDIT_TASK_TEXT
    elif data.startswith('delete_'):
        task_id = int(data.split('_')[1])
        user_id = update.effective_user.id
        tasks = await get_tasks(user_id)

        if not any(task[0] == task_id for task in tasks):
            await query.edit_message_text(f"Задача с ID {task_id} не найдена.")
            return ConversationHandler.END

        await delete_task(task_id)
        try:
            scheduler.remove_job(str(task_id))
        except Exception as e:
            logger.warning(f"Не удалось удалить задание {task_id} из планировщика: {e}")
        await query.edit_message_text(f"Задача {task_id} удалена.")
    return ConversationHandler.END

# Основной обработчик ошибок
async def error_handler(update: object, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")

# Функция запуска бота
async def startup():
    """Функция, выполняемая при старте бота."""
    await create_table()
    logger.info("База данных инициализирована.")

# Инициализация бота
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Регистрация обработчиков команд
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("add", add_task_command))
application.add_handler(CommandHandler("tasks", show_tasks_command))
application.add_handler(CommandHandler("delete", delete_task_command))

# Регистрация обработчика callback query для inline клавиатуры
application.add_handler(CallbackQueryHandler(main_menu_callback))

# Регистрация ConversationHandler для редактирования задачи через кнопку меню
edit_task_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(main_menu_callback, pattern='^edit_task$')],
    states={
        EDIT_TASK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_id)],
        EDIT_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_text)],
        EDIT_TASK_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_due_date)]
    },
    fallbacks=[CommandHandler('cancel', cancel_edit)],
    allow_reentry=True
)
application.add_handler(edit_task_conv)


# Регистрация обработчика редактирования и удаления конкретных задач
application.add_handler(CallbackQueryHandler(task_callback, pattern='^(edit_|delete_)'))

# Регистрация обработчика ошибок
application.add_error_handler(error_handler)

# Регистрация и запуск функции startup при старте бота
async def on_startup(application: Application):
    await startup()

application.job_queue.run_once(on_startup, when=0)

# Основной запуск приложения
if __name__ == '__main__':
    try:
        application.run_polling()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную.")
