import logging
import os
import sqlite3
from datetime import datetime, timedelta
import asyncio
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ApplicationBuilder, InlineQueryHandler, MessageHandler, filters

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.environ.get("BOT_TOKEN", "8765639328:AAEu7HrWbdaAHWyxu9yl94Qfc4K6HoagFyA")
CREATOR_ID = int(os.environ.get("CREATOR_ID", 8269156736))
TELEGRAM_API_PROXY = os.environ.get("TELEGRAM_API_PROXY", None)
DB_PATH = "/data/dotbot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== ВСТРОЕННЫЕ ДЕЙСТВИЯ =====
DEFAULT_ACTIONS = {
    "обнять": {"male": "обнял", "female": "обняла", "emoji": "🫂"},
    "ударить": {"male": "ударил", "female": "ударила", "emoji": "💥"},
    "погладить": {"male": "погладил", "female": "погладила", "emoji": "✨"},
    "поцеловать": {"male": "поцеловал", "female": "поцеловала", "emoji": "😘"},
    "сесть": {"male": "сел рядом с", "female": "села рядом с", "emoji": "🪑"},
    "успокоить": {"male": "успокоил", "female": "успокоила", "emoji": "🫂"},
    "поговорить": {"male": "поговорил с", "female": "поговорила с", "emoji": "💬"},
    "пожениться": {"male": "поженился на", "female": "поженилась на", "emoji": "💍"},
    "завести отношения": {"male": "завёл отношения с", "female": "завела отношения с", "emoji": "💕"},
    "укусить": {"male": "укусил", "female": "укусила", "emoji": "🦷"},
    "щекотать": {"male": "пощекотал", "female": "пощекотала", "emoji": "🤣"},
    "подарить цветы": {"male": "подарил цветы", "female": "подарила цветы", "emoji": "🌹"},
    "обнять крепко": {"male": "крепко обнял", "female": "крепко обняла", "emoji": "🤗"},
    "потанцевать": {"male": "потанцевал с", "female": "потанцевала с", "emoji": "💃"},
    "спеть": {"male": "спел для", "female": "спела для", "emoji": "🎤"},
    "приготовить еду": {"male": "приготовил еду для", "female": "приготовила еду для", "emoji": "🍳"},
    "сделать массаж": {"male": "сделал массаж", "female": "сделала массаж", "emoji": "💆"},
    "поздравить": {"male": "поздравил", "female": "поздравила", "emoji": "🎉"},
    "извиниться": {"male": "извинился перед", "female": "извинилась перед", "emoji": "🙏"},
    "попросить прощения": {"male": "попросил прощения у", "female": "попросила прощения у", "emoji": "🥺"}
}

# ===== ИНДЕКСЫ БД =====
U_ID = 0
U_FIRST_NAME = 1
U_GENDER = 2
U_CUSTOM_NAME = 3
U_ROLE = 4
U_IS_PREMIUM = 5
U_PREMIUM_UNTIL = 6
U_REGISTERED_AT = 7
PAGE_SIZE = 4

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        gender TEXT DEFAULT 'male',
        custom_name TEXT DEFAULT '',
        role TEXT DEFAULT 'user',
        is_premium BOOLEAN DEFAULT FALSE,
        premium_until TIMESTAMP NULL,
        registered_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS allowed_users (
        user_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        added_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS custom_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        trigger TEXT UNIQUE,
        response_male TEXT,
        response_female TEXT,
        emoji TEXT DEFAULT '',
        uses INTEGER DEFAULT 0,
        created_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS action_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action_name TEXT,
        target_name TEXT,
        used_at TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS user_names (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        custom_name TEXT,
        updated_at TIMESTAMP
    )""")
    c.execute("""INSERT OR IGNORE INTO users (user_id, first_name, gender, role, registered_at)
        VALUES (?, ?, ?, ?, ?)""", (CREATOR_ID, "𝓜𝓪𝓭𝓪𝓶", "female", "creator", datetime.now()))
    c.execute("""INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at)
        VALUES (?, ?, ?)""", (CREATOR_ID, CREATOR_ID, datetime.now()))
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def register_user(user_id, first_name, gender="male"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO users (user_id, first_name, gender, registered_at)
        VALUES (?, ?, ?, ?)""", (user_id, first_name, gender, datetime.now()))
    conn.commit()
    conn.close()

def update_user_gender(user_id, gender):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET gender = ? WHERE user_id = ?", (gender, user_id))
    conn.commit()
    conn.close()

def update_user_name(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET custom_name = ? WHERE user_id = ?", (name, user_id))
    conn.commit()
    conn.close()

def is_trusted(user_id):
    if user_id == CREATOR_ID:
        return True
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM allowed_users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def is_creator(user_id):
    return user_id == CREATOR_ID

def get_custom_actions(user_id=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if user_id is not None:
        c.execute("SELECT id, trigger, response_male, response_female, emoji, uses FROM custom_actions WHERE owner_id = ?", (user_id,))
    else:
        c.execute("SELECT id, trigger, response_male, response_female, emoji, uses FROM custom_actions")
    actions = c.fetchall()
    conn.close()
    return actions

def add_custom_action(owner_id, trigger, response_male, response_female, emoji=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO custom_actions (owner_id, trigger, response_male, response_female, emoji, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""", (owner_id, trigger.lower(), response_male, response_female, emoji, datetime.now()))
    conn.commit()
    conn.close()

def delete_custom_action(action_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM custom_actions WHERE id = ?", (action_id,))
    conn.commit()
    conn.close()

def get_user_actions_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM custom_actions WHERE owner_id = ?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_allowed_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM allowed_users")
    users = c.fetchall()
    conn.close()
    return [u[0] for u in users]

def add_allowed_user(user_id, added_by):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at)
        VALUES (?, ?, ?)""", (user_id, added_by, datetime.now()))
    conn.commit()
    conn.close()

def remove_allowed_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_premium_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, premium_until FROM users WHERE is_premium = TRUE")
    users = c.fetchall()
    conn.close()
    return users

def set_premium(user_id, until=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE users SET is_premium = TRUE, premium_until = ? WHERE user_id = ?""", (until, user_id))
    conn.commit()
    conn.close()

def remove_premium(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE users SET is_premium = FALSE, premium_until = NULL WHERE user_id = ?""", (user_id,))
    conn.commit()
    conn.close()

def log_action(user_id, action_name, target_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO action_logs (user_id, action_name, target_name, used_at)
        VALUES (?, ?, ?, ?)""", (user_id, action_name, target_name, datetime.now()))
    conn.commit()
    conn.close()

def check_access(user_id):
    return user_id == CREATOR_ID or is_trusted(user_id)

def save_user_name(user_id, username, first_name):
    if not username:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO user_names (user_id, username, first_name, updated_at)
        VALUES (?, ?, ?, ?)""", (user_id, username, first_name, datetime.now()))
    conn.commit()
    conn.close()

def get_user_display_name(username):
    if not username:
        return username
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, first_name, custom_name FROM user_names WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    if result:
        user = get_user(result[0])
        if user and user[U_CUSTOM_NAME]:
            return user[U_CUSTOM_NAME]
        if result[1]:
            return result[1]
    return username

# ===== УТИЛИТЫ =====
def _format_name(name):
    return f"<b><u>{name}</u></b>"

def _build_menu_text(title, lines):
    text = f"🌙 <b>{title}</b>\n"
    text += "━" * 16 + "\n\n"
    for line in lines:
        text += line + "\n"
    return text.rstrip("\n") + "\n\n"

def normalize_username_placeholders(text):
    text = re.sub(r'(?i)Username1', 'Username1', text)
    text = re.sub(r'(?i)Username2', 'Username2', text)
    return text

# ===== ИНЛАЙН-РЕЖИМ =====
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.strip()
    user_id = update.effective_user.id
    chat_type = update.inline_query.chat_type

    if not check_access(user_id):
        await update.inline_query.answer([], cache_time=0)
        return

    if not query_text:
        results = [
            InlineQueryResultArticle(
                id="help",
                title="📖 DotBotRPG",
                description="Введите: <Действие> @username",
                input_message_content=InputTextMessageContent(
                    "📖 <b>DotBotRPG</b>\n\nВведите:\n<code>&lt;Действие&gt; @username</code>\n\nПример:\n<code>Обнять @petya</code>",
                    parse_mode="HTML"
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=60)
        return

    if query_text.lower().startswith("trig."):
        query_text = query_text[5:].strip()

    target_input = ""
    action = query_text
    custom = get_custom_actions(user_id)

    found_custom = False
    for c in custom:
        trigger = c[1]
        if query_text.lower().startswith(trigger.lower()):
            action = trigger
            rest = query_text[len(trigger):].strip()
            if rest.startswith("@"):
                target_input = rest[1:]
            else:
                target_input = rest
            found_custom = True
            break

    if not found_custom:
        parts = query_text.split(" ", 1)
        if len(parts) > 1:
            first_word = parts[0].lower()
            if first_word in DEFAULT_ACTIONS:
                action = first_word
                rest = parts[1].strip()
                if rest.startswith("@"):
                    target_input = rest[1:]
                else:
                    target_input = rest
            else:
                action = parts[0]
                if len(parts) > 1:
                    if parts[1].startswith("@"):
                        target_input = parts[1][1:]
                    else:
                        target_input = parts[1]
        else:
            action = query_text

    if not target_input:
        words = query_text.split(" ")
        for i, w in enumerate(words):
            if w.startswith("@"):
                target_input = w[1:]
                action = " ".join(words[:i]).strip()
                if not action and i > 0:
                    action = " ".join(words[:i])
                break

    sender_gender = "male"
    sender_name = "Пользователь"
    user = get_user(user_id)
    if user:
        sender_gender = user[U_GENDER] if user else "male"
        sender_name = user[U_CUSTOM_NAME] or user[U_FIRST_NAME] or update.effective_user.first_name or "Пользователь"
    else:
        await update.inline_query.answer([
            InlineQueryResultArticle(
                id="nouser",
                title="❌ Зарегистрируйтесь!",
                description="Напишите /start",
                input_message_content=InputTextMessageContent(
                    "❌ Вы не зарегистрированы!\nНапишите <b>/start</b>", parse_mode="HTML"
                )
            )
        ], cache_time=60)
        return

    target_display_name = None
    target_id = None

    # ===== В ЛС — определяем собеседника =====
    if chat_type == "private":
        try:
            chat_id = update.inline_query.chat_id
            members = await context.bot.get_chat_members(chat_id)
            for member in members:
                if member.user.id != user_id:
                    target_display_name = member.user.first_name
                    if member.user.last_name:
                        target_display_name += " " + member.user.last_name
                    target_id = member.user.id
                    break
            if not target_display_name:
                target_display_name = "Собеседник"
        except Exception as e:
            target_display_name = "Собеседник"
    else:
        # В ГРУППЕ — нужен @username
        if not target_input:
            await update.inline_query.answer([
                InlineQueryResultArticle(
                    id="hint",
                    title="❌ Укажите получателя",
                    description="В группах нужно указывать @username",
                    input_message_content=InputTextMessageContent(
                        "❌ В группах нужно указывать @username\n\nПример: обнять @petya"
                    )
                )
            ], cache_time=60)
            return
        
        target_display_name = get_user_display_name(target_input)
        if target_display_name == target_input:
            try:
                target_user = await context.bot.get_chat(f"@{target_input}")
                if target_user and target_user.first_name:
                    target_display_name = target_user.first_name
                    if target_user.last_name:
                        target_display_name += " " + target_user.last_name
                    target_id = target_user.id
            except Exception:
                target_display_name = target_input

    if not target_display_name:
        target_display_name = target_input or "Собеседник"

    sender_name_f = _format_name(sender_name)
    target_name_f = _format_name(target_display_name)

    response = None
    action_found = None
    emoji = ""

    for c in custom:
        if c[1].lower() == action.lower():
            action_found = c[1]
            template = c[2] if sender_gender == "male" else c[3]
            emoji = c[4] or ""
            template = template.replace("Username1", sender_name_f)
            template = template.replace("Username2", target_name_f)
            response = f"{emoji} | <b>{template}</b>"
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE custom_actions SET uses = uses + 1 WHERE id = ?", (c[0],))
            conn.commit()
            conn.close()
            break

    if not response and action.lower() in DEFAULT_ACTIONS:
        action_found = action.lower()
        data = DEFAULT_ACTIONS[action_found]
        verb = data["male"] if sender_gender == "male" else data["female"]
        emoji = data["emoji"]
        response = f"{emoji} | <b>{sender_name_f} {verb} {target_name_f}</b>"

    if response:
        log_action(user_id, action_found, target_display_name)
        await update.inline_query.answer([
            InlineQueryResultArticle(
                id=action_found,
                title=f"{action_found.capitalize()} → {target_display_name}",
                description=response.replace("<b>", "").replace("</b>", "").replace("<u>", "").replace("</u>", ""),
                input_message_content=InputTextMessageContent(response, parse_mode="HTML")
            )
        ], cache_time=0)
        return

    await update.inline_query.answer([
        InlineQueryResultArticle(
            id="notfound",
            title="🤖 Такого действия нет!",
            description="Попробуйте: обнять, поцеловать, ударить, погладить",
            input_message_content=InputTextMessageContent(
                "🤖 Такого действия нет!\n\nДоступные действия:\n" + ", ".join(list(DEFAULT_ACTIONS.keys())[:10])
            )
        )
    ], cache_time=60)

# ===== ОБРАБОТЧИК ТЕКСТА =====
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return

    if update.effective_user:
        username = update.effective_user.username
        first_name = update.effective_user.first_name
        if username and first_name:
            save_user_name(user_id, username, first_name)

    state = context.user_data
    
    if state.get("creating_action") and state["creating_action"].get("step"):
        await create_action_input(update, context)
    elif state.get("changing_name"):
        await handle_name_input(update, context)
    elif state.get("adding_user"):
        await add_user_input(update, context)
    elif state.get("giving_premium"):
        await give_premium_input(update, context)
    elif state.get("removing_premium"):
        await remove_premium_input(update, context)
    elif state.get("creating_action_emoji"):
        await handle_emoji_input(update, context)

# ===== КОМАНДЫ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    if update.effective_user:
        username = update.effective_user.username
        first_name = update.effective_user.first_name
        if username and first_name:
            save_user_name(user_id, username, first_name)
    
    user = get_user(user_id)
    if user is None:
        keyboard = [[
            InlineKeyboardButton("👦 Мужской", callback_data="gender_male"),
            InlineKeyboardButton("👧 Женский", callback_data="gender_female")
        ]]
        text = _build_menu_text(
            "Добро пожаловать в DotBotRPG",
            [
                "✨ Ночной мир RPG ждёт тебя",
                "🤝 Взаимодействуй с другими",
                "💫 Создавай свои действия",
                "",
                "⬇️ <b>Выберите свой пол:</b>"
            ]
        )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    user = get_user(user_id)
    if not user:
        return
    name = user[U_CUSTOM_NAME] or user[U_FIRST_NAME]
    role = user[U_ROLE]

    if role == "creator":
        keyboard = [
            [InlineKeyboardButton("📋 Мои действия", callback_data="my_actions"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action"),
             InlineKeyboardButton("🗑️ Удалить действие", callback_data="delete_action")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="users"),
             InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Все действия", callback_data="all_actions"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action"),
             InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]

    text = _build_menu_text(
        "DotBotRPG — Главное меню",
        [
            f"👋 Привет, <b>{name}</b>!",
            "",
            "⬇️ Выберите действие:"
        ]
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_main_menu_from_query(query):
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    user = get_user(user_id)
    if not user:
        await query.edit_message_text("❌ Ошибка")
        return
    name = user[U_CUSTOM_NAME] or user[U_FIRST_NAME]
    role = user[U_ROLE]

    if role == "creator":
        keyboard = [
            [InlineKeyboardButton("📋 Мои действия", callback_data="my_actions"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action"),
             InlineKeyboardButton("🗑️ Удалить действие", callback_data="delete_action")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="users"),
             InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Все действия", callback_data="all_actions"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action"),
             InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]

    text = _build_menu_text(
        "DotBotRPG — Главное меню",
        [
            f"👋 Привет, <b>{name}</b>!",
            "",
            "⬇️ Выберите действие:"
        ]
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== НАСТРОЙКИ =====
async def settings_menu(query):
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    user = get_user(user_id)
    if not user:
        return
    gender = "Мужской" if user[U_GENDER] == "male" else "Женский"
    name = user[U_CUSTOM_NAME] or user[U_FIRST_NAME]
    role = user[U_ROLE]
    is_prem = user[U_IS_PREMIUM]
    prem_until = user[U_PREMIUM_UNTIL]
    actions_count = get_user_actions_count(user_id)
    max_actions = 999 if role == "creator" else 25 if is_prem else 5

    role_label = "👑 Создатель" if role == "creator" else "⭐ Премиум" if is_prem else "🔰 Бесплатный"

    lines = [
        f"👤 <b>Имя:</b> {name}",
        f"⚧ <b>Пол:</b> {gender}",
        f"📊 <b>Статус:</b> {role_label}"
    ]
    if role != "creator":
        lines.append(f"📊 <b>Действий:</b> {actions_count}/{max_actions}")
    if is_prem and prem_until:
        lines.append(f"📅 <b>Активен до:</b> {prem_until[:10]}")
    elif is_prem:
        lines.append("📅 <b>Активен:</b> навсегда")

    text = _build_menu_text("Настройки", lines)

    keyboard = []
    if is_prem or role == "creator":
        keyboard.append([InlineKeyboardButton("✏️ Изменить имя", callback_data="change_name")])
    keyboard.append([InlineKeyboardButton("🔄 Сменить пол", callback_data="change_gender")])
    keyboard.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])

    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def change_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    user = get_user(user_id)
    if not user or (not user[U_IS_PREMIUM] and user[U_ROLE] != "creator"):
        await query.edit_message_text("🔒 Смена имени доступна только в Премиум-версии.")
        return

    text = _build_menu_text(
        "Введите новое имя",
        [
            "Максимум 64 символа",
            "",
            "Напишите /cancel для отмены"
        ]
    )
    await query.edit_message_text(text, parse_mode="HTML")
    context.user_data["changing_name"] = True

async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    if not context.user_data.get("changing_name"):
        return
    new_name = update.message.text.strip()

    if new_name == "/cancel":
        context.user_data["changing_name"] = False
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
    if not user or (not user[U_IS_PREMIUM] and user[U_ROLE] != "creator"):
        await update.message.reply_text("🔒 Смена имени доступна только в Премиум-версии.")
        return

    update_user_name(user_id, new_name)
    context.user_data["changing_name"] = False
    await update.message.reply_text(f"✅ Имя изменено на <b>&quot;{new_name}&quot;</b>!", parse_mode="HTML")
    await show_main_menu(update, context)

async def change_gender_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not check_access(query.from_user.id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    keyboard = [[
        InlineKeyboardButton("👦 Мужской", callback_data="set_gender_male"),
        InlineKeyboardButton("👧 Женский", callback_data="set_gender_female")
    ]]
    await query.edit_message_text("⚧ <b>Выберите ваш пол:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def change_gender_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    gender = "male" if query.data == "set_gender_male" else "female"
    update_user_gender(user_id, gender)
    await query.edit_message_text(f"✅ Пол изменён на <b>{'Мужской' if gender == 'male' else 'Женский'}</b>!", parse_mode="HTML")
    await settings_menu(query)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM custom_actions")
    total_actions = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM action_logs")
    total_uses = c.fetchone()[0]
    c.execute("""SELECT action_name, COUNT(*) FROM action_logs
        GROUP BY action_name ORDER BY COUNT(*) DESC LIMIT 5""")
    top_actions = c.fetchall()
    conn.close()

    lines = [
        f"📦 <b>Всего действий:</b> {total_actions}",
        f"⚡ <b>Всего использований:</b> {total_uses}",
        "",
        "🏆 <b>Популярные действия:</b>"
    ]
    if top_actions:
        for i, (name, count) in enumerate(top_actions, 1):
            lines.append(f"{i}. {name.capitalize()} — {count} раз")
    else:
        lines.append("Пока нет данных.")

    text = _build_menu_text("Статистика", lines)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="settings")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def all_actions_menu(query):
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return

    lines = [f"🔹 <b>Встроенные ({len(DEFAULT_ACTIONS)} шт.):</b>"]
    for i, action in enumerate(DEFAULT_ACTIONS.keys(), 1):
        emoji = DEFAULT_ACTIONS[action]["emoji"]
        lines.append(f"{i}. {action.capitalize()} {emoji}")

    custom = get_custom_actions(user_id)
    if custom:
        lines.append("")
        lines.append(f"🔸 <b>Ваши кастомные ({len(custom)} шт.):</b>")
        for c in custom:
            lines.append(f"• {c[1].capitalize()}")
    else:
        lines.append("")
        lines.append("🔸 У вас нет кастомных действий.")

    lines.extend([
        "",
        "📌 <b>Как использовать:</b>",
        "В любом чате напишите:",
        "<code>Обнять @username</code>"
    ])

    text = _build_menu_text("Доступные действия", lines)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def my_actions_menu(query):
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return

    custom = get_custom_actions(user_id)
    if not custom:
        lines = [
            "У вас нет кастомных действий.",
            "",
            'Создайте первое через <b>➕ Создать действие</b>.'
        ]
    else:
        lines = []
        for i, c in enumerate(custom, 1):
            lines.append(f"{i}. {c[1].capitalize()} (использовано: {c[5]} раз)")

    text = _build_menu_text("Ваши действия", lines)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

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
    max_actions = 999 if user[U_ROLE] == "creator" else 25 if user[U_IS_PREMIUM] else 5
    current = get_user_actions_count(user_id)
    if current >= max_actions:
        limit_text = "безлимитный" if user[U_ROLE] == "creator" else str(max_actions)
        extra = "Оформите Премиум для доступа к 25 действиям." if not user[U_IS_PREMIUM] and user[U_ROLE] != "creator" else ""
        await query.edit_message_text(
            f"❌ Вы достигли лимита в <b>{limit_text}</b> кастомных действий.\n\n{extra}",
            parse_mode="HTML"
        )
        return

    text = _build_menu_text(
        "Создание нового действия",
        [
            "Введите название действия (триггер).",
            "Максимум 35 символов.",
            "",
            "Напишите /cancel для отмены"
        ]
    )
    await query.edit_message_text(text, parse_mode="HTML")
    context.user_data["creating_action"] = {"step": "trigger"}

async def create_action_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    if "creating_action" not in context.user_data:
        return
    data = context.user_data["creating_action"]
    text = update.message.text.strip()

    if text == "/cancel":
        context.user_data.pop("creating_action", None)
        await update.message.reply_text("❌ Создание действия отменено.")
        await show_main_menu(update, context)
        return

    if data["step"] == "trigger":
        if not text:
            await update.message.reply_text("❌ Название не может быть пустым.")
            return
        if len(text) > 35:
            await update.message.reply_text("❌ Название не может быть длиннее 35 символов.")
            return
        if text.lower() in DEFAULT_ACTIONS:
            await update.message.reply_text("⚠️ Действие с таким названием уже есть (встроенное).")
            return
        custom = get_custom_actions(user_id)
        for c in custom:
            if c[1].lower() == text.lower():
                await update.message.reply_text("⚠️ Действие с таким названием уже есть (кастомное).")
                return
        data["trigger"] = text
        data["step"] = "male_response"
        await update.message.reply_text(
            _build_menu_text(
                "Ответ для МУЖСКОГО пола",
                [
                    "Используйте шаблон: <code>Username1 [действие] Username2</code>",
                    "Можно добавлять свой текст после Username2.",
                    "",
                    "Пример: <code>Username1 чмокнул Username2 и убежал</code>"
                ]
            ),
            parse_mode="HTML"
        )

    elif data["step"] == "male_response":
        text = normalize_username_placeholders(text)
        if "Username1" not in text or "Username2" not in text:
            await update.message.reply_text("❌ В ответе должны быть <b>Username1</b> и <b>Username2</b>", parse_mode="HTML")
            return
        data["male_response"] = text
        data["step"] = "female_response"
        await update.message.reply_text(
            _build_menu_text(
                "Ответ для ЖЕНСКОГО пола",
                [
                    "Используйте шаблон: <code>Username1 [действие] Username2</code>",
                    "Можно добавлять свой текст после Username2.",
                    "",
                    "Пример: <code>Username1 чмокнула Username2 и убежала</code>"
                ]
            ),
            parse_mode="HTML"
        )

    elif data["step"] == "female_response":
        text = normalize_username_placeholders(text)
        if "Username1" not in text or "Username2" not in text:
            await update.message.reply_text("❌ В ответе должны быть <b>Username1</b> и <b>Username2</b>", parse_mode="HTML")
            return
        data["female_response"] = text
        data["step"] = "emoji"
        user = get_user(user_id)
        if user[U_IS_PREMIUM] or user[U_ROLE] == "creator":
            keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_emoji")]]
            await update.message.reply_text(
                _build_menu_text(
                    "Выбор эмодзи",
                    [
                        "Отправьте ОДИН эмодзи для этого действия.",
                        "Или нажмите кнопку 'Пропустить'."
                    ]
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            context.user_data["creating_action_emoji"] = True
        else:
            await update.message.reply_text("🔒 Эмодзи доступны только в Премиум-версии. Пропускаем...")
            add_custom_action(user_id, data["trigger"], data["male_response"], data["female_response"], "")
            context.user_data.pop("creating_action", None)
            await update.message.reply_text(
                f"✅ <b>Действие &quot;{data['trigger'].capitalize()}&quot; создано!</b>\n\n"
                f"Теперь вы можете использовать его в чате:\n"
                f"<code>@{update.effective_user.username or 'username'} {data['trigger'].capitalize()} @username</code>",
                parse_mode="HTML"
            )
            await show_main_menu(update, context)

    elif data["step"] == "emoji":
        try:
            import emoji
            if not emoji.is_emoji(text):
                await update.message.reply_text("❌ Это не эмодзи. Отправьте один эмодзи или нажмите 'Пропустить'.")
                return
        except ImportError:
            pass
        if len(text) > 2:
            await update.message.reply_text("❌ Нужно отправить ТОЛЬКО ОДИН эмодзи.")
            return
        data["emoji"] = text
        add_custom_action(user_id, data["trigger"], data["male_response"], data["female_response"], text)
        context.user_data.pop("creating_action", None)
        context.user_data.pop("creating_action_emoji", None)
        await update.message.reply_text(
            f"✅ <b>Действие &quot;{data['trigger'].capitalize()}&quot; создано!</b>\n\n"
            f"Теперь вы можете использовать его в чате:\n"
            f"<code>@{update.effective_user.username or 'username'} {data['trigger'].capitalize()} @username</code>",
            parse_mode="HTML"
        )
        await show_main_menu(update, context)

async def skip_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    if "creating_action" not in context.user_data:
        await query.edit_message_text("❌ Ошибка")
        return
    data = context.user_data["creating_action"]
    add_custom_action(user_id, data["trigger"], data["male_response"], data["female_response"], "")
    context.user_data.pop("creating_action", None)
    context.user_data.pop("creating_action_emoji", None)
    await query.edit_message_text(
        f"✅ <b>Действие &quot;{data['trigger'].capitalize()}&quot; создано!</b>\n\n"
        f"Теперь вы можете использовать его в чате:\n"
        f"<code>@{query.from_user.username or 'username'} {data['trigger'].capitalize()} @username</code>",
        parse_mode="HTML"
    )
    await show_main_menu_from_query(query)

async def delete_action_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    await show_delete_page(query, context, 1)

async def show_delete_page(query, context, page):
    user_id = query.from_user.id
    custom = get_custom_actions(user_id)
    if not custom:
        await query.edit_message_text("📋 У вас нет кастомных действий для удаления.")
        return

    total = len(custom)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_actions = custom[start:end]

    keyboard = []
    for c in page_actions:
        keyboard.append([InlineKeyboardButton(f"🗑️ {c[1].capitalize()}", callback_data=f"delete_{c[0]}")])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"delpage_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"delpage_{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])

    context.user_data["delete_page"] = page
    text = _build_menu_text(
        "Удаление действия",
        [
            f"Страница {page}/{total_pages}",
            "",
            "Выберите действие:"
        ]
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_action_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    action_id = int(query.data.split("_")[1])
    custom = get_custom_actions(user_id)
    action_name = None
    for c in custom:
        if c[0] == action_id:
            action_name = c[1]
            break
    delete_custom_action(action_id)
    page = context.user_data.get("delete_page", 1)
    await show_delete_page(query, context, page)

async def delete_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    page = int(query.data.split("_")[1])
    await show_delete_page(query, context, page)

async def users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    allowed = get_allowed_users()
    lines = ["👥 <b>Доверенные пользователи</b>"]
    if not allowed:
        lines.append("Список пуст.")
    else:
        for i, uid in enumerate(allowed[:10], 1):
            u = get_user(uid)
            name = u[U_FIRST_NAME] if u else str(uid)
            premium = "⭐ Премиум" if u and u[U_IS_PREMIUM] else "🔰 Бесплатный"
            lines.append(f"{i}. {name} (ID: {uid}) — {premium}")
        if len(allowed) > 10:
            lines.append(f"... и ещё {len(allowed) - 10} пользователей")

    text = _build_menu_text("Пользователи", lines)
    keyboard = [
        [InlineKeyboardButton("➕ Добавить", callback_data="add_user"),
         InlineKeyboardButton("➖ Удалить", callback_data="remove_user")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    text = _build_menu_text(
        "Добавление пользователя",
        [
            "Введите ID или @username пользователя.",
            "",
            "Напишите /cancel для отмены"
        ]
    )
    await query.edit_message_text(text, parse_mode="HTML")
    context.user_data["adding_user"] = True

async def add_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id) or not is_creator(user_id):
        return
    if not context.user_data.get("adding_user"):
        return
    text = update.message.text.strip()
    if text == "/cancel":
        context.user_data.pop("adding_user", None)
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
    except Exception:
        await update.message.reply_text("❌ Пользователь не найден.")
        return
    if target_id == CREATOR_ID:
        await update.message.reply_text("❌ Вы не можете добавить самого себя.")
        return
    if is_trusted(target_id):
        await update.message.reply_text("⚠️ Этот пользователь уже имеет доступ.")
        return
    add_allowed_user(target_id, user_id)
    context.user_data.pop("adding_user", None)
    await update.message.reply_text("✅ Пользователь добавлен в доверенные!")
    await show_main_menu(update, context)

async def remove_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
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
        name = u[U_FIRST_NAME] if u else str(uid)
        keyboard.append([InlineKeyboardButton(f"❌ {name}", callback_data=f"remove_{uid}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    text = _build_menu_text("Удаление пользователя", ["Выберите пользователя:"])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def remove_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    target_id = int(query.data.split("_")[1])
    remove_allowed_user(target_id)
    await query.edit_message_text("✅ Доступ отозван.")
    await remove_user_start(update, context)

async def premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    user = get_user(user_id)
    if not user:
        return
    if user[U_ROLE] == "creator":
        premium_users = get_premium_users()
        free_users = len(get_allowed_users()) - len(premium_users)
        lines = [
            "👑 <b>Ваш статус:</b> Создатель",
            f"📊 <b>Премиум-пользователей:</b> {len(premium_users)}",
            f"📊 <b>Бесплатных пользователей:</b> {free_users}",
            "",
            "<b>Управление:</b>"
        ]
        text = _build_menu_text("Премиум-система", lines)
        keyboard = [
            [InlineKeyboardButton("📋 Список премиум", callback_data="premium_list")],
            [InlineKeyboardButton("⭐ Выдать премиум", callback_data="give_premium")],
            [InlineKeyboardButton("❌ Забрать премиум", callback_data="remove_premium")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if user[U_IS_PREMIUM]:
        lines = [
            "👤 <b>Статус:</b> Премиум",
            f"📊 <b>Действий создано:</b> {get_user_actions_count(user_id)} из 25",
            "✨ <b>Эмодзи:</b> доступны",
            "✏️ <b>Смена имени:</b> доступна"
        ]
        if user[U_PREMIUM_UNTIL]:
            lines.append(f"📅 <b>Активен до:</b> {user[U_PREMIUM_UNTIL][:10]}")
        else:
            lines.append("📅 <b>Активен:</b> навсегда")
        lines.extend(["", "Спасибо, что поддерживаете проект! 💜"])
        text = _build_menu_text("Ваш Премиум активен!", lines)
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    else:
        lines = [
            "🔓 <b>Что вы получите:</b>",
            "✅ 25 кастомных действий (вместо 5)",
            "✅ Эмодзи в действиях",
            "✅ Смена имени в настройках",
            "✅ Приоритетная поддержка",
            "",
            "💳 <b>Тарифы:</b>",
            "• 199 ₽ / месяц",
            "• 1 490 ₽ / навсегда"
        ]
        text = _build_menu_text("DotBotRPG Премиум", lines)
        keyboard = [
            [InlineKeyboardButton("💳 Оплатить 199 ₽ (месяц)", callback_data="pay_month")],
            [InlineKeyboardButton("💳 Оплатить 1 490 ₽ (навсегда)", callback_data="pay_forever")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def premium_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    premium_users = get_premium_users()
    if not premium_users:
        await query.edit_message_text("📋 Премиум-пользователей нет.")
        return
    lines = []
    for uid, until in premium_users:
        u = get_user(uid)
        name = u[U_FIRST_NAME] if u else str(uid)
        status = "навсегда" if until is None else until[:10]
        lines.append(f"• {name} — {status}")
    text = _build_menu_text("Премиум-пользователи", lines)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="premium")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def give_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    text = _build_menu_text(
        "Выдача премиум",
        [
            "Введите ID или @username пользователя.",
            "",
            "Напишите /cancel для отмены"
        ]
    )
    await query.edit_message_text(text, parse_mode="HTML")
    context.user_data["giving_premium"] = True

async def give_premium_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id) or not is_creator(user_id):
        return
    if not context.user_data.get("giving_premium"):
        return
    text = update.message.text.strip()
    if text == "/cancel":
        context.user_data.pop("giving_premium", None)
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
    except Exception:
        await update.message.reply_text("❌ Пользователь не найден.")
        return
    keyboard = [
        [InlineKeyboardButton("📅 1 месяц", callback_data=f"premium_month_{target_id}")],
        [InlineKeyboardButton("♾️ Навсегда", callback_data=f"premium_forever_{target_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="premium")]
    ]
    await update.message.reply_text("⏳ <b>Выберите срок:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data.pop("giving_premium", None)

async def give_premium_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
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
    await query.edit_message_text(f"✅ <b>Премиум выдан!</b> {'1 месяц' if period == 'month' else 'Навсегда'}", parse_mode="HTML")
    await premium_menu(update, context)

async def remove_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    text = _build_menu_text(
        "Отзыв премиум",
        [
            "Введите ID или @username пользователя.",
            "",
            "Напишите /cancel для отмены"
        ]
    )
    await query.edit_message_text(text, parse_mode="HTML")
    context.user_data["removing_premium"] = True

async def remove_premium_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id) or not is_creator(user_id):
        return
    if not context.user_data.get("removing_premium"):
        return
    text = update.message.text.strip()
    if text == "/cancel":
        context.user_data.pop("removing_premium", None)
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
    except Exception:
        await update.message.reply_text("❌ Пользователь не найден.")
        return
    remove_premium(target_id)
    context.user_data.pop("removing_premium", None)
    await update.message.reply_text("✅ Премиум отозван!")
    await show_main_menu(update, context)

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
        await query.edit_message_text(f"✅ Пол установлен: <b>{'Мужской' if gender == 'male' else 'Женский'}</b>!", parse_mode="HTML")
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
    elif data.startswith("delpage_"):
        await delete_page_handler(update, context)
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
    elif data == "noop":
        pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    lines = [
        "📌 <b>Команды в ЛС:</b>",
        "/start — Главное меню",
        "/menu — Главное меню",
        "/settings — Настройки",
        "/custom — Создать кастомное действие",
        "/cancel — Отменить текущее действие",
        "/help — Помощь"
    ]
    if is_creator(user_id):
        lines.extend([
            "",
            "👑 <b>Команды Создателя:</b>",
            "/adduser — Добавить пользователя",
            "/removeuser — Удалить пользователя",
            "/userlist — Список доверенных",
            "/setpremium — Выдать премиум",
            "/removepremium — Забрать премиум",
            "/premiumlist — Список премиум"
        ])
    lines.extend([
        "",
        "📌 <b>Инлайн-режим (в чатах):</b>",
        "В ЛС: @DotBotRPG_bot <Действие>",
        "В группах: @DotBotRPG_bot <Действие> @username",
        "",
        "📌 <b>Встроенные действия (20 шт.):</b>",
        ", ".join([a.capitalize() for a in DEFAULT_ACTIONS.keys()])
    ])
    text = _build_menu_text("DotBotRPG — помощь", lines)
    await update.message.reply_text(text, parse_mode="HTML")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено")

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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    print("=" * 50)
    print("🌙 DotBotRPG запущен!")
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
