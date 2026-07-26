import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ApplicationBuilder, InlineQueryHandler, MessageHandler, filters
import sqlite3
from datetime import datetime, timedelta
import asyncio
import emoji

TOKEN = "8765639328:AAFk1v5PnqcnqOqk3N7Xbugquy8MT3BBr_U"
CREATOR_ID = 8269156736
TELEGRAM_API_PROXY = None

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== ВСТРОЕННЫЕ ДЕЙСТВИЯ =====
DEFAULT_ACTIONS = {
    "обнять": {"male": "Обнял", "female": "Обняла", "emoji": "🫂"},
    "ударить": {"male": "Ударил", "female": "Ударила", "emoji": "👊"},
    "погладить": {"male": "Погладил", "female": "Погладила", "emoji": "🤲"},
    "поцеловать": {"male": "Поцеловал", "female": "Поцеловала", "emoji": "💋"},
    "сесть": {"male": "Сел рядом с", "female": "Села рядом с", "emoji": "🪑"},
    "успокоить": {"male": "Успокоил", "female": "Успокоила", "emoji": "🫂"},
    "поговорить": {"male": "Поговорил с", "female": "Поговорила с", "emoji": "💬"},
    "пожениться": {"male": "Поженился на", "female": "Поженилась на", "emoji": "💍❤️"},
    "завести отношения": {"male": "Завёл отношения с", "female": "Завела отношения с", "emoji": "💕"},
    "укусить": {"male": "Укусил", "female": "Укусила", "emoji": "🦷"},
    "щекотать": {"male": "Пощекотал", "female": "Пощекотала", "emoji": "😂"},
    "подарить цветы": {"male": "Подарил цветы", "female": "Подарила цветы", "emoji": "💐"},
    "обнять крепко": {"male": "Крепко обнял", "female": "Крепко обняла", "emoji": "🤗"},
    "потанцевать": {"male": "Потанцевал с", "female": "Потанцевала с", "emoji": "💃🕺"},
    "спеть": {"male": "Спел для", "female": "Спела для", "emoji": "🎤"},
    "приготовить еду": {"male": "Приготовил еду для", "female": "Приготовила еду для", "emoji": "🍳"},
    "сделать массаж": {"male": "Сделал массаж", "female": "Сделала массаж", "emoji": "💆"},
    "поздравить": {"male": "Поздравил", "female": "Поздравила", "emoji": "🎉"},
    "извиниться": {"male": "Извинился перед", "female": "Извинилась перед", "emoji": "🙏"},
    "попросить прощения": {"male": "Попросил прощения у", "female": "Попросила прощения у", "emoji": "🥺"}
}

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        gender TEXT DEFAULT 'male',
        custom_name TEXT DEFAULT '',
        role TEXT DEFAULT 'user',
        is_premium BOOLEAN DEFAULT FALSE,
        premium_until TIMESTAMP NULL,
        registered_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS allowed_users (
        user_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        added_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS custom_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        trigger TEXT,
        response_male TEXT,
        response_female TEXT,
        emoji TEXT DEFAULT '',
        uses INTEGER DEFAULT 0,
        created_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS action_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action_name TEXT,
        target_name TEXT,
        used_at TIMESTAMP
    )''')
    c.execute('''INSERT OR IGNORE INTO users (user_id, first_name, role, registered_at)
        VALUES (?, ?, ?, ?)''', (CREATOR_ID, "𝓜𝓪𝓭𝓪𝓶", "creator", datetime.now()))
    c.execute('''INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at)
        VALUES (?, ?, ?)''', (CREATOR_ID, CREATOR_ID, datetime.now()))
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def get_user(user_id):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def register_user(user_id, first_name, gender='male'):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, first_name, gender, registered_at) VALUES (?, ?, ?, ?)',
              (user_id, first_name, gender, datetime.now()))
    conn.commit()
    conn.close()

def update_user_gender(user_id, gender):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET gender = ? WHERE user_id = ?', (gender, user_id))
    conn.commit()
    conn.close()

def update_user_name(user_id, name):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET custom_name = ? WHERE user_id = ?', (name, user_id))
    conn.commit()
    conn.close()

def is_trusted(user_id):
    if user_id == CREATOR_ID:
        return True
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('SELECT 1 FROM allowed_users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def get_custom_actions():
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('SELECT id, trigger, response_male, response_female, emoji, uses FROM custom_actions')
    actions = c.fetchall()
    conn.close()
    return actions

def add_custom_action(owner_id, trigger, response_male, response_female, emoji=''):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('INSERT INTO custom_actions (owner_id, trigger, response_male, response_female, emoji, created_at) VALUES (?, ?, ?, ?, ?, ?)',
              (owner_id, trigger, response_male, response_female, emoji, datetime.now()))
    conn.commit()
    conn.close()

def delete_custom_action(action_id):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('DELETE FROM custom_actions WHERE id = ?', (action_id,))
    conn.commit()
    conn.close()

def get_user_actions_count(user_id):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM custom_actions WHERE owner_id = ?', (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_allowed_users():
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM allowed_users')
    users = c.fetchall()
    conn.close()
    return [u[0] for u in users]

def add_allowed_user(user_id, added_by):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at) VALUES (?, ?, ?)',
              (user_id, added_by, datetime.now()))
    conn.commit()
    conn.close()

def remove_allowed_user(user_id):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('DELETE FROM allowed_users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_premium_users():
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('SELECT user_id, premium_until FROM users WHERE is_premium = TRUE')
    users = c.fetchall()
    conn.close()
    return users

def set_premium(user_id, until=None):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET is_premium = TRUE, premium_until = ? WHERE user_id = ?', (until, user_id))
    conn.commit()
    conn.close()

def remove_premium(user_id):
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET is_premium = FALSE, premium_until = NULL WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def check_access(user_id):
    return user_id == CREATOR_ID or is_trusted(user_id)

# ===== ИНЛАЙН-РЕЖИМ =====
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.strip()
    user_id = update.effective_user.id
    
    # Проверка доступа
    if not check_access(user_id):
        await update.inline_query.answer([], cache_time=0)
        return
    
    # Пустой запрос
    if not query_text:
        results = [InlineQueryResultArticle(
            id="help",
            title="📖 DotBotRPG",
            description="Введите: trig. <действие> @username",
            input_message_content=InputTextMessageContent(
                "📖 <b>DotBotRPG</b>\nВведите trig. &lt;действие&gt; @username",
                parse_mode="HTML"
            )
        )]
        await update.inline_query.answer(results, cache_time=60)
        return
    
    # Не trig.
    if not query_text.lower().startswith("trig."):
        results = [InlineQueryResultArticle(
            id="hint",
            title="💡 Начните с trig.",
            description='Пример: trig. Обнять @username',
            input_message_content=InputTextMessageContent(
                '💡 Напишите: <b>trig. Обнять @username</b>',
                parse_mode="HTML"
            )
        )]
        await update.inline_query.answer(results, cache_time=60)
        return
    
    # Разбор: trig. Обнять @username
    parts = query_text.split(" ", 2)
    if len(parts) < 3:
        results = []
        for action in ["обнять", "поцеловать", "ударить", "погладить"]:
            display = action.capitalize()
            results.append(InlineQueryResultArticle(
                id=action,
                title=display,
                description=f"✨ {display}",
                input_message_content=InputTextMessageContent(
                    f"@{update.effective_user.username} <b>{display}</b> @username {DEFAULT_ACTIONS[action]['emoji']}",
                    parse_mode="HTML"
                )
            ))
        await update.inline_query.answer(results[:5], cache_time=60)
        return
    
    action = parts[1].lower()
    target_input = parts[2].strip()
    if target_input.startswith("@"):
        target_input = target_input[1:]
    
    # Проверка на себя
    if target_input == update.effective_user.username:
        results = [InlineQueryResultArticle(
            id="self",
            title="😅 Нельзя на себя!",
            description="Попробуйте выбрать другого пользователя",
            input_message_content=InputTextMessageContent(
                "😅 Нельзя сделать это на самого себя!\n\nПопробуйте: <b>trig. Обнять @username</b>",
                parse_mode="HTML"
            )
        )]
        await update.inline_query.answer(results, cache_time=0)
        return
    
    # Проверка на бота
    if target_input == "DotBotRPG_bot":
        results = [InlineQueryResultArticle(
            id="bot",
            title="🤖 Я бот!",
            description="Спасибо, но я всего лишь бот 🤖",
            input_message_content=InputTextMessageContent(
                "🤖 Я всего лишь бот, но спасибо за внимание! 💜"
            )
        )]
        await update.inline_query.answer(results, cache_time=0)
        return
    
    # Получаем отправителя
    user = get_user(user_id)
    if not user:
        results = [InlineQueryResultArticle(
            id="nouser",
            title="❌ Зарегистрируйтесь!",
            description="Напишите /start в личные сообщения",
            input_message_content=InputTextMessageContent(
                "❌ Вы не зарегистрированы!\nНапишите <b>/start</b> в личные сообщения боту",
                parse_mode="HTML"
            )
        )]
        await update.inline_query.answer(results, cache_time=60)
        return
    
    sender_gender = user[2] if user else 'male'
    sender_name = user[3] if user and user[3] else user[1] if user else update.effective_user.first_name
    
    # Получаем настоящее имя цели
    target_name = target_input
    try:
        target_user = await context.bot.get_chat(f"@{target_input}")
        if target_user and target_user.first_name:
            target_name = target_user.first_name
    except:
        target_name = target_input
    
    # Проверяем встроенные действия
    if action in DEFAULT_ACTIONS:
        data = DEFAULT_ACTIONS[action]
        verb = data['male'] if sender_gender == 'male' else data['female']
        emoji = data['emoji']
        response = f"<b>{sender_name}</b> {verb} <b>{target_name}</b> {emoji}"
        
        results = [InlineQueryResultArticle(
            id=action,
            title=f"✨ {action.capitalize()} → {target_name}",
            description=response,
            input_message_content=InputTextMessageContent(
                response,
                parse_mode="HTML"
            )
        )]
        await update.inline_query.answer(results, cache_time=0)
        return
    
    # Проверяем кастомные действия
    custom = get_custom_actions()
    for c in custom:
        if c[1].lower() == action:
            verb = c[2] if sender_gender == 'male' else c[3]
            emoji = c[4] if c[4] else ""
            response = f"<b>{sender_name}</b> {verb} <b>{target_name}</b> {emoji}"
            results = [InlineQueryResultArticle(
                id=f"custom_{action}",
                title=f"✨ {action.capitalize()} → {target_name}",
                description=response,
                input_message_content=InputTextMessageContent(
                    response,
                    parse_mode="HTML"
                )
            )]
            await update.inline_query.answer(results, cache_time=0)
            return
    
    # Действие не найдено
    results = [InlineQueryResultArticle(
        id="notfound",
        title="🤖 Такого действия нет!",
        description="Попробуйте другое действие",
        input_message_content=InputTextMessageContent(
            "🤖 Такого действия нет!\n\nДоступные действия:\n" + ", ".join(list(DEFAULT_ACTIONS.keys())[:10])
        )
    )]
    await update.inline_query.answer(results, cache_time=60)

# ===== КОМАНДЫ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not check_access(user_id):
        return
    
    user = get_user(user_id)
    if user is None:
        keyboard = [[
            InlineKeyboardButton("👦 Мужской", callback_data="gender_male"),
            InlineKeyboardButton("👧 Женский", callback_data="gender_female")
        ]]
        await update.message.reply_text(
            "👋 Добро пожаловать в DotBotRPG!\n\nДля начала выберите свой пол:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    user = get_user(user_id)
    if not user:
        return
    name = user[3] if user[3] else user[1]
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
    
    await update.message.reply_text(
        f"📱 DotBotRPG — главное меню\n\n👋 Привет, {name}!\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_main_menu_from_query(query):
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if not user:
        await query.edit_message_text("❌ Ошибка")
        return
    name = user[3] if user[3] else user[1]
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
    
    await query.edit_message_text(
        f"📱 DotBotRPG — главное меню\n\n👋 Привет, {name}!\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== НАСТРОЙКИ =====
async def settings_menu(query):
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if not user:
        return
    gender = "Мужской" if user[2] == 'male' else "Женский"
    name = user[3] if user[3] else user[1]
    role = "Создатель" if user[5] == 'creator' else "Премиум" if user[6] else "Бесплатный"
    actions_count = get_user_actions_count(user_id)
    max_actions = 999 if user[5] == 'creator' else 25 if user[6] else 5
    
    text = f"⚙️ Настройки DotBotRPG\n\n👤 Имя: {name}\n⚧ Пол: {gender}\n📊 Статус: {role}"
    if user[5] != 'creator':
        text += f"\n📊 Действий: {actions_count}/{max_actions}"
    if user[6] and user[7]:
        text += f"\n📅 Активен до: {user[7][:10]}"
    elif user[6]:
        text += "\n📅 Активен: навсегда"
    
    keyboard = []
    if user[6] or user[5] == 'creator':
        keyboard.append([InlineKeyboardButton("📝 Изменить имя", callback_data="change_name")])
    keyboard.append([InlineKeyboardButton("🔄 Сменить пол", callback_data="change_gender")])
    keyboard.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===== СМЕНА ИМЕНИ =====
async def change_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if not user or (not user[6] and user[5] != 'creator'):
        await query.edit_message_text("🔒 Смена имени доступна только в Премиум-версии.")
        return
    
    await query.edit_message_text(
        "✏️ Введите новое имя для отображения:\n"
        "(Максимум 64 символа, /cancel для отмены)"
    )
    context.user_data['changing_name'] = True

async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    if not context.user_data.get('changing_name'):
        return
    
    new_name = update.message.text.strip()
    
    if new_name == "/cancel":
        context.user_data['changing_name'] = False
        await update.message.reply_text("❌ Отменено")
        await show_main_menu(update, context)
        return
    
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
    
    update_user_name(user_id, new_name)
    context.user_data['changing_name'] = False
    await update.message.reply_text(f"✅ Имя изменено на \"{new_name}\"!")
    await show_main_menu(update, context)

# ===== СМЕНА ПОЛА =====
async def change_gender_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not check_access(query.from_user.id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    keyboard = [[
        InlineKeyboardButton("👦 Мужской", callback_data="set_gender_male"),
        InlineKeyboardButton("👧 Женский", callback_data="set_gender_female")
    ]]
    await query.edit_message_text("Выберите ваш пол:", reply_markup=InlineKeyboardMarkup(keyboard))

async def change_gender_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    gender = "male" if query.data == "set_gender_male" else "female"
    update_user_gender(user_id, gender)
    await query.edit_message_text(f"✅ Пол изменён на {'Мужской' if gender == 'male' else 'Женский'}!")
    await settings_menu(query)

# ===== СТАТИСТИКА =====
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    conn = sqlite3.connect('dotbot.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM custom_actions')
    total_actions = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM action_logs')
    total_uses = c.fetchone()[0]
    c.execute('SELECT action_name, COUNT(*) FROM action_logs GROUP BY action_name ORDER BY COUNT(*) DESC LIMIT 5')
    top_actions = c.fetchall()
    conn.close()
    
    text = f"📊 Статистика DotBotRPG\n\nВсего создано действий: {total_actions}\nВсего использований: {total_uses}\n\n🏆 Популярные действия:\n"
    if top_actions:
        for i, (name, count) in enumerate(top_actions, 1):
            text += f"{i}. {name.capitalize()} — {count} раз\n"
    else:
        text += "Пока нет данных."
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===== ВСЕ ДЕЙСТВИЯ =====
async def all_actions_menu(query):
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    text = "📋 Доступные действия:\n\n🔹 Встроенные (20 шт.):\n"
    for i, action in enumerate(list(DEFAULT_ACTIONS.keys())[:10], 1):
        text += f"{i}. {action.capitalize()}\n"
    text += f"... и ещё {len(DEFAULT_ACTIONS) - 10}\n\n"
    
    custom = get_custom_actions()
    if custom:
        text += f"🔸 Кастомные ({len(custom)} шт.):\n"
        for c in custom:
            text += f"• {c[1].capitalize()}\n"
    else:
        text += "🔸 Кастомных действий пока нет.\n"
    
    text += "\n📌 Используй в инлайн-режиме:\n@DotBotRPG_bot trig. Обнять @username"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===== МОИ ДЕЙСТВИЯ (ТОЛЬКО ДЛЯ СОЗДАТЕЛЯ) =====
async def my_actions_menu(query):
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if user[5] != 'creator':
        await query.edit_message_text("❌ Доступно только для Создателя")
        return
    
    custom = get_custom_actions()
    if not custom:
        text = "📋 Ваши действия:\n\nУ вас нет кастомных действий.\nСоздайте первое через '➕ Создать действие'."
    else:
        text = "📋 Ваши действия:\n\n"
        for i, c in enumerate(custom, 1):
            text += f"{i}. {c[1].capitalize()} (использовано: {c[5]} раз)\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===== СОЗДАНИЕ КАСТОМНОГО ДЕЙСТВИЯ =====
async def create_action_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if not user:
        await query.edit_message_text("❌ Ошибка")
        return
    
    max_actions = 999 if user[5] == 'creator' else 25 if user[6] else 5
    current = get_user_actions_count(user_id)
    
    if current >= max_actions:
        if user[5] == 'creator':
            limit_text = "безлимитный"
        else:
            limit_text = f"{max_actions}"
        await query.edit_message_text(
            f"❌ Вы достигли лимита в {limit_text} кастомных действий.\n"
            f"{'Оформите Премиум для доступа к 25 действиям.' if not user[6] and user[5] != 'creator' else ''}"
        )
        return
    
    await query.edit_message_text(
        "✏️ Введите название действия (триггер).\nМаксимум 35 символов.\n(/cancel для отмены)"
    )
    context.user_data['creating_action'] = {'step': 'trigger'}

async def create_action_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    if 'creating_action' not in context.user_data:
        return
    
    data = context.user_data['creating_action']
    text = update.message.text.strip()
    
    if text == "/cancel":
        context.user_data.pop('creating_action', None)
        await update.message.reply_text("❌ Создание действия отменено.")
        await show_main_menu(update, context)
        return
    
    if data['step'] == 'trigger':
        if not text:
            await update.message.reply_text("❌ Название не может быть пустым.")
            return
        if len(text) > 35:
            await update.message.reply_text("❌ Название не может быть длиннее 35 символов.")
            return
        if text.lower() in DEFAULT_ACTIONS:
            await update.message.reply_text("⚠️ Действие с таким названием уже есть (встроенное).")
            return
        custom = get_custom_actions()
        for c in custom:
            if c[1].lower() == text.lower():
                await update.message.reply_text("⚠️ Действие с таким названием уже есть (кастомное).")
                return
        
        data['trigger'] = text
        data['step'] = 'male_response'
        await update.message.reply_text(
            f"✏️ Теперь введите ответ для МУЖСКОГО пола.\n"
            f"Используйте шаблон: Username1 [действие] Username2\n"
            f"Можно добавлять свой текст после Username2.\n\n"
            f"Пример: Username1 Чмокнул Username2 и убежал"
        )
    
    elif data['step'] == 'male_response':
        if "Username1" not in text or "Username2" not in text:
            await update.message.reply_text("❌ В ответе должны быть Username1 и Username2")
            return
        data['male_response'] = text
        data['step'] = 'female_response'
        await update.message.reply_text(
            f"✏️ Теперь введите ответ для ЖЕНСКОГО пола.\n"
            f"Используйте шаблон: Username1 [действие] Username2\n"
            f"Можно добавлять свой текст после Username2.\n\n"
            f"Пример: Username1 Чмокнула Username2 и убежала"
        )
    
    elif data['step'] == 'female_response':
        if "Username1" not in text or "Username2" not in text:
            await update.message.reply_text("❌ В ответе должны быть Username1 и Username2")
            return
        data['female_response'] = text
        data['step'] = 'emoji'
        
        user = get_user(user_id)
        if user[6] or user[5] == 'creator':
            keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_emoji")]]
            await update.message.reply_text(
                "✏️ Отправьте ОДИН эмодзи для этого действия.\n"
                "Или нажмите кнопку 'Пропустить'.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text("🔒 Эмодзи доступны только в Премиум-версии. Пропускаем...")
            data['emoji'] = ''
            add_custom_action(user_id, data['trigger'], data['male_response'], data['female_response'], '')
            context.user_data.pop('creating_action', None)
            await update.message.reply_text(
                f"✅ Действие \"{data['trigger'].capitalize()}\" создано!\n\n"
                f"Теперь вы можете использовать его в чате:\n"
                f"@DotBotRPG_bot trig. {data['trigger'].capitalize()} @username"
            )
            await show_main_menu(update, context)

async def skip_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    if 'creating_action' not in context.user_data:
        await query.edit_message_text("❌ Ошибка")
        return
    
    data = context.user_data['creating_action']
    data['emoji'] = ''
    add_custom_action(user_id, data['trigger'], data['male_response'], data['female_response'], '')
    context.user_data.pop('creating_action', None)
    
    await query.edit_message_text(
        f"✅ Действие \"{data['trigger'].capitalize()}\" создано!\n\n"
        f"Теперь вы можете использовать его в чате:\n"
        f"@DotBotRPG_bot trig. {data['trigger'].capitalize()} @username"
    )
    await show_main_menu_from_query(query)

async def handle_emoji_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    if 'creating_action' not in context.user_data:
        return
    if context.user_data['creating_action'].get('step') != 'emoji':
        return
    
    text = update.message.text.strip()
    data = context.user_data['creating_action']
    
    if len(text) != 1 or not emoji.is_emoji(text):
        await update.message.reply_text("❌ Нужно отправить ТОЛЬКО ОДИН эмодзи")
        return
    
    data['emoji'] = text
    add_custom_action(user_id, data['trigger'], data['male_response'], data['female_response'], text)
    context.user_data.pop('creating_action', None)
    
    await update.message.reply_text(
        f"✅ Действие \"{data['trigger'].capitalize()}\" создано!\n\n"
        f"Теперь вы можете использовать его в чате:\n"
        f"@DotBotRPG_bot trig. {data['trigger'].capitalize()} @username"
    )
    await show_main_menu(update, context)

# ===== УДАЛЕНИЕ КАСТОМНОГО ДЕЙСТВИЯ =====
async def delete_action_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if user[5] != 'creator':
        await query.edit_message_text("❌ Доступно только для Создателя")
        return
    
    custom = get_custom_actions()
    if not custom:
        await query.edit_message_text("📋 У вас нет кастомных действий для удаления.")
        return
    
    keyboard = []
    for c in custom:
        keyboard.append([InlineKeyboardButton(f"🗑️ {c[1].capitalize()}", callback_data=f"delete_{c[0]}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    
    await query.edit_message_text(
        "🗑️ Выберите действие для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_action_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    action_id = int(query.data.split("_")[1])
    custom = get_custom_actions()
    action_name = None
    for c in custom:
        if c[0] == action_id:
            action_name = c[1]
            break
    
    delete_custom_action(action_id)
    await query.edit_message_text(f"✅ Действие '{action_name.capitalize()}' удалено!")
    await delete_action_start(update, context)

# ===== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ =====
async def users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if user[5] != 'creator':
        await query.edit_message_text("❌ Доступно только для Создателя")
        return
    
    allowed = get_allowed_users()
    text = "👥 Доверенные пользователи:\n\n"
    if not allowed:
        text += "Список пуст."
    else:
        for i, uid in enumerate(allowed[:10], 1):
            u = get_user(uid)
            name = u[1] if u else str(uid)
            premium = "⭐ Премиум" if u and u[6] else "Бесплатный"
            text += f"{i}. {name} (ID: {uid}) — {premium}\n"
        if len(allowed) > 10:
            text += f"\n... и ещё {len(allowed) - 10} пользователей"
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить", callback_data="add_user")],
        [InlineKeyboardButton("➖ Удалить", callback_data="remove_user")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    await query.edit_message_text(
        "✏️ Введите ID или @username пользователя, которого хотите добавить:\n(/cancel для отмены)"
    )
    context.user_data['adding_user'] = True

async def add_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    if not context.user_data.get('adding_user'):
        return
    
    text = update.message.text.strip()
    
    if text == "/cancel":
        context.user_data.pop('adding_user', None)
        await update.message.reply_text("❌ Отменено")
        await show_main_menu(update, context)
        return
    
    if text.startswith("@"):
        text = text[1:]
    
    try:
        if text.isdigit():
            target_id = int(text)
        else:
            target = await context.bot.get_chat(f"@{text}")
            target_id = target.id
    except:
        await update.message.reply_text("❌ Пользователь не найден. Убедитесь, что ID или @username верный.")
        return
    
    if target_id == CREATOR_ID:
        await update.message.reply_text("❌ Вы не можете добавить самого себя.")
        return
    
    if is_trusted(target_id):
        await update.message.reply_text("⚠️ Этот пользователь уже имеет доступ.")
        return
    
    add_allowed_user(target_id, user_id)
    context.user_data.pop('adding_user', None)
    await update.message.reply_text(f"✅ Пользователь добавлен в доверенные!")
    await show_main_menu(update, context)

async def remove_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    allowed = get_allowed_users()
    allowed = [u for u in allowed if u != CREATOR_ID]
    
    if not allowed:
        await query.edit_message_text("👥 Нет пользователей для удаления.")
        return
    
    keyboard = []
    for uid in allowed[:10]:
        u = get_user(uid)
        name = u[1] if u else str(uid)
        keyboard.append([InlineKeyboardButton(f"❌ {name}", callback_data=f"remove_{uid}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    
    await query.edit_message_text(
        "👥 Выберите пользователя для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def remove_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    target_id = int(query.data.split("_")[1])
    remove_allowed_user(target_id)
    await query.edit_message_text(f"✅ Доступ отозван.")
    await remove_user_start(update, context)

# ===== ПРЕМИУМ =====
async def premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if not user:
        return
    
    if user[5] == 'creator':
        premium_users = get_premium_users()
        free_users = len(get_allowed_users()) - len(premium_users)
        
        text = f"⭐ Премиум-система\n\n👑 Ваш статус: Создатель\n📊 Премиум-пользователей: {len(premium_users)}\n📊 Бесплатных пользователей: {free_users}\n\nУправление:"
        keyboard = [
            [InlineKeyboardButton("📋 Список премиум", callback_data="premium_list")],
            [InlineKeyboardButton("⭐ Выдать премиум", callback_data="give_premium")],
            [InlineKeyboardButton("❌ Забрать премиум", callback_data="remove_premium")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    if user[6]:
        text = f"⭐ Ваш Премиум активен!\n\n👤 Статус: Премиум\n📊 Действий создано: {get_user_actions_count(user_id)} из 25\n✨ Эмодзи: доступны\n✏️ Смена имени: доступна"
        if user[7]:
            text += f"\n📅 Активен до: {user[7][:10]}"
        else:
            text += "\n📅 Активен: навсегда"
        text += "\n\nСпасибо, что поддерживаете проект! 💜"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    else:
        text = "⭐ DotBotRPG Премиум\n\n🔓 Что вы получите:\n✅ 25 кастомных действий (вместо 5)\n✅ Эмодзи в действиях\n✅ Смена имени в настройках\n✅ Приоритетная поддержка\n\n💳 Тарифы:\n• 199 ₽ / месяц\n• 1 490 ₽ / навсегда"
        keyboard = [
            [InlineKeyboardButton("💳 Оплатить 199 ₽ (месяц)", callback_data="pay_month")],
            [InlineKeyboardButton("💳 Оплатить 1 490 ₽ (навсегда)", callback_data="pay_forever")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def premium_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    premium_users = get_premium_users()
    if not premium_users:
        await query.edit_message_text("📋 Премиум-пользователей нет.")
        return
    
    text = "📋 Премиум-пользователи:\n\n"
    for uid, until in premium_users:
        u = get_user(uid)
        name = u[1] if u else str(uid)
        status = "навсегда" if until is None else until[:10]
        text += f"• {name} — {status}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="premium")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def give_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    await query.edit_message_text(
        "✏️ Введите ID или @username пользователя для выдачи премиум:\n(/cancel для отмены)"
    )
    context.user_data['giving_premium'] = True

async def give_premium_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    if not context.user_data.get('giving_premium'):
        return
    
    text = update.message.text.strip()
    if text == "/cancel":
        context.user_data.pop('giving_premium', None)
        await update.message.reply_text("❌ Отменено")
        await show_main_menu(update, context)
        return
    
    if text.startswith("@"):
        text = text[1:]
    
    try:
        if text.isdigit():
            target_id = int(text)
        else:
            target = await context.bot.get_chat(f"@{text}")
            target_id = target.id
    except:
        await update.message.reply_text("❌ Пользователь не найден.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📅 1 месяц", callback_data=f"premium_month_{target_id}")],
        [InlineKeyboardButton("♾️ Навсегда", callback_data=f"premium_forever_{target_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="premium")]
    ]
    await update.message.reply_text(
        f"Выберите срок для пользователя:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.pop('giving_premium', None)

async def give_premium_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    parts = query.data.split("_")
    period = parts[1]
    target_id = int(parts[2])
    
    if period == "month":
        until = (datetime.now() + timedelta(days=30)).isoformat()
    else:
        until = None
    
    set_premium(target_id, until)
    await query.edit_message_text(f"✅ Премиум выдан! {'1 месяц' if period == 'month' else 'Навсегда'}")
    await premium_menu(update, context)

async def remove_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    await query.edit_message_text(
        "✏️ Введите ID или @username пользователя для отзыва премиум:\n(/cancel для отмены)"
    )
    context.user_data['removing_premium'] = True

async def remove_premium_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    if not context.user_data.get('removing_premium'):
        return
    
    text = update.message.text.strip()
    if text == "/cancel":
        context.user_data.pop('removing_premium', None)
        await update.message.reply_text("❌ Отменено")
        await show_main_menu(update, context)
        return
    
    if text.startswith("@"):
        text = text[1:]
    
    try:
        if text.isdigit():
            target_id = int(text)
        else:
            target = await context.bot.get_chat(f"@{text}")
            target_id = target.id
    except:
        await update.message.reply_text("❌ Пользователь не найден.")
        return
    
    remove_premium(target_id)
    context.user_data.pop('removing_premium', None)
    await update.message.reply_text("✅ Премиум отозван!")
    await show_main_menu(update, context)

# ===== КНОПКИ =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("gender_"):
        user_id = query.from_user.id
        if not check_access(user_id):
            await query.edit_message_text("❌ Доступ запрещён")
            return
        gender = "male" if data == "gender_male" else "female"
        register_user(user_id, query.from_user.first_name, gender)
        await query.edit_message_text(f"✅ Пол установлен: {'Мужской' if gender == 'male' else 'Женский'}!")
        await show_main_menu_from_query(query)
    
    elif data == "back":
        await show_main_menu_from_query(query)
    
    elif data == "settings":
        await settings_menu(query)
    
    elif data == "all_actions":
        await all_actions_menu(query)
    
    elif data == "my_actions":
        await my_actions_menu(query)
    
    elif data == "premium":
        await premium_menu(update, context)
    
    elif data == "change_gender":
        await change_gender_start(update, context)
    
    elif data.startswith("set_gender_"):
        await change_gender_set(update, context)
    
    elif data == "change_name":
        await change_name_start(update, context)
    
    elif data == "stats":
        await show_stats(update, context)
    
    elif data == "create_action":
        await create_action_start(update, context)
    
    elif data == "delete_action":
        await delete_action_start(update, context)
    
    elif data.startswith("delete_"):
        await delete_action_confirm(update, context)
    
    elif data == "users":
        await users_menu(update, context)
    
    elif data == "add_user":
        await add_user_start(update, context)
    
    elif data == "remove_user":
        await remove_user_start(update, context)
    
    elif data.startswith("remove_"):
        await remove_user_confirm(update, context)
    
    elif data == "skip_emoji":
        await skip_emoji(update, context)
    
    elif data == "premium_list":
        await premium_list(update, context)
    
    elif data == "give_premium":
        await give_premium_start(update, context)
    
    elif data.startswith("premium_month_") or data.startswith("premium_forever_"):
        await give_premium_confirm(update, context)
    
    elif data == "remove_premium":
        await remove_premium_start(update, context)

# ===== HELP =====
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    text = """🤖 DotBotRPG — помощь

📌 Команды в ЛС:
/start — Главное меню
/menu — Главное меню
/settings — Настройки
/custom — Создать кастомное действие
/cancel — Отменить текущее действие
/help — Помощь"""

    if user_id == CREATOR_ID:
        text += """
/name <имя> — Изменить имя
/adduser <ID или @> — Добавить пользователя
/removeuser <ID или @> — Удалить пользователя
/userlist — Список доверенных
/setpremium <ID или @> — Выдать премиум
/removepremium <ID или @> — Забрать премиум
/premiumlist — Список премиум"""

    text += """

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

    await update.message.reply_text(text)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено")

# ===== ЗАПУСК =====
async def main():
    print("🚀 Инициализация базы данных...")
    init_db()
    
    print("🔧 Создание приложения...")
    builder = ApplicationBuilder().token(TOKEN)
    if TELEGRAM_API_PROXY:
        builder = builder.base_url(TELEGRAM_API_PROXY)
    else:
        print("🌐 Прямое подключение к Telegram API")
    
    builder = builder.connect_timeout(60).read_timeout(60).write_timeout(60)
    app = builder.build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    # Кнопки
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Инлайн
    app.add_handler(InlineQueryHandler(inline_query))
    
    # Обработчики ввода
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_emoji_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, create_action_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, give_premium_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, remove_premium_input))
    
    print("=" * 50)
    print("🤖 DotBotRPG запущен!")
    print(f"👑 Создатель: {CREATOR_ID}")
    print(f"📋 Действий: {len(DEFAULT_ACTIONS)}")
    print("=" * 50)
    print("✅ Бот готов к работе!")
    print("=" * 50)
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
