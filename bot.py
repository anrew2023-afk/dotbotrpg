import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ApplicationBuilder
import sqlite3
from datetime import datetime
import asyncio

TOKEN = "8765639328:AAFk1v5PnqcnqOqk3N7Xbugquy8MT3BBr_U"
CREATOR_ID = 8269156736
TELEGRAM_API_PROXY = None

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect('dotbot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            gender TEXT DEFAULT 'male',
            custom_name TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            is_premium BOOLEAN DEFAULT FALSE,
            premium_until TIMESTAMP NULL,
            registered_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS allowed_users (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            trigger TEXT,
            response_male TEXT,
            response_female TEXT,
            emoji TEXT DEFAULT '',
            uses INTEGER DEFAULT 0,
            created_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_name TEXT,
            target_name TEXT,
            used_at TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, first_name, role, registered_at)
        VALUES (?, ?, ?, ?)
    ''', (CREATOR_ID, "𝓜𝓪𝓭𝓪𝓶", "creator", datetime.now()))
    
    cursor.execute('''
        INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at)
        VALUES (?, ?, ?)
    ''', (CREATOR_ID, CREATOR_ID, datetime.now()))
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def get_user(user_id):
    conn = sqlite3.connect('dotbot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def register_user(user_id, first_name, gender='male'):
    conn = sqlite3.connect('dotbot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, first_name, gender, registered_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, first_name, gender, datetime.now()))
    conn.commit()
    conn.close()

def update_user_gender(user_id, gender):
    conn = sqlite3.connect('dotbot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET gender = ? WHERE user_id = ?', (gender, user_id))
    conn.commit()
    conn.close()

def is_trusted(user_id):
    conn = sqlite3.connect('dotbot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM allowed_users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    
    user = get_user(user_id)
    
    if user is None:
        keyboard = [
            [
                InlineKeyboardButton("👦 Мужской", callback_data="gender_male"),
                InlineKeyboardButton("👧 Женский", callback_data="gender_female")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👋 Добро пожаловать в DotBotRPG!\n\n"
            "Для начала выберите свой пол:",
            reply_markup=reply_markup
        )
    else:
        await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ Ошибка: пользователь не найден")
        return
    
    role = user[5] if user else 'user'
    
    keyboard = []
    
    if role == 'creator':
        keyboard = [
            [InlineKeyboardButton("📋 Мои действия", callback_data="my_actions")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action")],
            [InlineKeyboardButton("🗑️ Удалить действие", callback_data="delete_action")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="users")],
            [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Все действия", callback_data="all_actions")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action")],
            [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    name = user[3] if user and user[3] else update.effective_user.first_name
    
    await update.message.reply_text(
        f"📱 DotBotRPG — главное меню\n\n"
        f"👋 Привет, {name}!\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def show_main_menu_from_query(query):
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("❌ Ошибка: пользователь не найден")
        return
    
    role = user[5] if user else 'user'
    
    keyboard = []
    
    if role == 'creator':
        keyboard = [
            [InlineKeyboardButton("📋 Мои действия", callback_data="my_actions")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action")],
            [InlineKeyboardButton("🗑️ Удалить действие", callback_data="delete_action")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="users")],
            [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Все действия", callback_data="all_actions")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action")],
            [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    name = user[3] if user and user[3] else query.from_user.first_name
    
    await query.edit_message_text(
        f"📱 DotBotRPG — главное меню\n\n"
        f"👋 Привет, {name}!\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("gender_"):
        gender = "male" if data == "gender_male" else "female"
        register_user(user_id, query.from_user.first_name, gender)
        
        await query.edit_message_text(
            f"✅ Пол установлен: {'Мужской' if gender == 'male' else 'Женский'}!"
        )
        await show_main_menu_from_query(query)
    
    elif data == "settings":
        await show_settings(query)
    
    elif data == "back_to_menu":
        await show_main_menu_from_query(query)
    
    elif data == "change_gender":
        await change_gender(update, context)
    
    elif data.startswith("set_gender_"):
        await set_gender(update, context)
    
    elif data == "stats":
        await show_stats(update, context)
    
    elif data == "change_name":
        await change_name(update, context)

async def show_settings(query):
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("❌ Ошибка: пользователь не найден")
        return
    
    gender_text = "Мужской" if user[2] == 'male' else "Женский"
    role_text = "Создатель" if user[5] == 'creator' else "Премиум" if user[6] else "Бесплатный"
    name = user[3] if user[3] else user[1]
    
    settings_text = f"""⚙️ Настройки DotBotRPG

👤 Имя: {name}
⚧ Пол: {gender_text}
📊 Статус: {role_text}
"""
    
    keyboard = [
        [InlineKeyboardButton("🔄 Сменить пол", callback_data="change_gender")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
    ]
    
    if user[6] or user[5] == 'creator':
        keyboard.insert(1, [InlineKeyboardButton("📝 Изменить имя", callback_data="change_name")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(settings_text, reply_markup=reply_markup)

async def change_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("👦 Мужской", callback_data="set_gender_male"),
            InlineKeyboardButton("👧 Женский", callback_data="set_gender_female")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("Выберите ваш пол:", reply_markup=reply_markup)

async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    gender = "male" if query.data == "set_gender_male" else "female"
    
    update_user_gender(user_id, gender)
    
    gender_text = "Мужской" if gender == "male" else "Женский"
    await query.edit_message_text(f"✅ Пол изменён на {gender_text}!")
    await show_settings(query)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    stats_text = """📊 Статистика DotBotRPG

Всего создано действий: 0
Всего использований: 0

Список действий по использованию:
Пока нет данных."""
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(stats_text, reply_markup=reply_markup)

async def change_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Введите новое имя для отображения:\n"
        "(или напишите /cancel для отмены)"
    )
    
    context.user_data['changing_name'] = True

async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_name = update.message.text.strip()
    
    if len(new_name) > 64:
        await update.message.reply_text("❌ Имя не может быть длиннее 64 символов.")
        return
    
    if not new_name:
        await update.message.reply_text("❌ Имя не может быть пустым.")
        return
    
    user = get_user(user_id)
    if not user or (not user[6] and user[5] != 'creator'):
        await update.message.reply_text("🔒 Смена имени доступна только в Премиум-версии.")
        return
    
    conn = sqlite3.connect('dotbot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET custom_name = ? WHERE user_id = ?', (new_name, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Имя изменено на \"{new_name}\"!")
    await show_main_menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 DotBotRPG — помощь

📌 Команды в ЛС:
/start — Главное меню
/menu — Главное меню
/settings — Настройки
/custom — Создать кастомное действие
/cancel — Отменить текущее действие
/help — Помощь

📌 Инлайн-режим (в чатах):
@DotBotRPG_bot trig. <действие> @username

Примеры:
@DotBotRPG_bot trig. Обнять @petya
@DotBotRPG_bot trig. Поцеловать @masha

📌 Встроенные действия (20):
Обнять, Ударить, Погладить, Поцеловать, Сесть,
Успокоить, Поговорить, Пожениться, Завести отношения,
Укусить, Щекотка, Подарить цветы, Обнять крепко,
Потанцевать, Спеть, Приготовить еду, Сделать массаж,
Поздравить, Извиниться, Попросить прощения"""
    
    await update.message.reply_text(help_text)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")

async def main():
    print("🚀 Инициализация базы данных...")
    init_db()
    
    print("🔧 Создание приложения...")
    
    builder = ApplicationBuilder().token(TOKEN)
    
    if TELEGRAM_API_PROXY:
        print(f"🌐 Используется прокси: {TELEGRAM_API_PROXY}")
        builder = builder.base_url(TELEGRAM_API_PROXY)
    else:
        print("🌐 Прокси не используется, прямое подключение к Telegram API")
    
    builder = builder.connect_timeout(60).read_timeout(60).write_timeout(60)
    
    application = builder.build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("settings", lambda u, c: u.message.reply_text("Используйте кнопки в меню")))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.add_handler(CommandHandler("name", change_name))
    application.add_handler(CommandHandler("custom", lambda u, c: u.message.reply_text("🚧 В разработке")))
    
    print("=" * 50)
    print("🤖 DotBotRPG запущен!")
    print("=" * 50)
    print(f"👑 Создатель: {CREATOR_ID}")
    print(f"🌐 Прокси: {TELEGRAM_API_PROXY if TELEGRAM_API_PROXY else 'Не используется'}")
    print("=" * 50)
    print("✅ Бот готов к работе!")
    print("=" * 50)
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
