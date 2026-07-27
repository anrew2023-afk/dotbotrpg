import logging
import os
import sqlite3
from datetime import datetime, timedelta
import asyncio
import re
from functools import lru_cache
from contextlib import contextmanager
from typing import Optional, Tuple, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, InlineQueryHandler, MessageHandler, filters

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables!")

CREATOR_ID = int(os.environ.get("CREATOR_ID", 8269156736))
DB_PATH = os.environ.get("DB_PATH", "/data/dotbot.db")

if not os.path.exists(os.path.dirname(DB_PATH)):
    DB_PATH = "dotbot.db"

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

U_ID = 0
U_FIRST_NAME = 1
U_GENDER = 2
U_CUSTOM_NAME = 3
U_ROLE = 4
U_IS_PREMIUM = 5
U_PREMIUM_UNTIL = 6
U_REGISTERED_AT = 7
PAGE_SIZE = 4

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
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
        c.execute("""INSERT OR IGNORE INTO users (user_id, first_name, gender, role, registered_at)
            VALUES (?, ?, ?, ?, ?)""", (CREATOR_ID, "𝓜𝓪𝓭𝓪𝓶", "female", "creator", datetime.now()))
        c.execute("""INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at)
            VALUES (?, ?, ?)""", (CREATOR_ID, CREATOR_ID, datetime.now()))
    logger.info("✅ База данных инициализирована")

def get_user(user_id: int):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone()

@lru_cache(maxsize=128)
def get_user_cached(user_id: int):
    return get_user(user_id)

def register_user(user_id: int, first_name: str, gender: str = "male"):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT OR IGNORE INTO users (user_id, first_name, gender, registered_at)
            VALUES (?, ?, ?, ?)""", (user_id, first_name, gender, datetime.now()))

def update_user_gender(user_id: int, gender: str):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET gender = ? WHERE user_id = ?", (gender, user_id))

def update_user_name(user_id: int, name: str):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET custom_name = ? WHERE user_id = ?", (name, user_id))
        get_user_cached.cache_clear()

def is_trusted(user_id: int) -> bool:
    if user_id == CREATOR_ID:
        return True
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM allowed_users WHERE user_id = ?", (user_id,))
        return c.fetchone() is not None

def is_creator(user_id: int) -> bool:
    return user_id == CREATOR_ID

def get_custom_actions(user_id: Optional[int] = None):
    with get_db_connection() as conn:
        c = conn.cursor()
        if user_id is not None:
            c.execute("SELECT id, trigger, response_male, response_female, emoji, uses FROM custom_actions WHERE owner_id = ? ORDER BY id", (user_id,))
        else:
            c.execute("SELECT id, trigger, response_male, response_female, emoji, uses FROM custom_actions ORDER BY id")
        return c.fetchall()

def add_custom_action(owner_id: int, trigger: str, response_male: str, response_female: str, emoji: str = ""):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO custom_actions (owner_id, trigger, response_male, response_female, emoji, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""", (owner_id, trigger.lower(), response_male, response_female, emoji, datetime.now()))

def delete_custom_action(action_id: int):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM custom_actions WHERE id = ?", (action_id,))

def get_user_actions_count(user_id: int) -> int:
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM custom_actions WHERE owner_id = ?", (user_id,))
        return c.fetchone()[0]

def get_allowed_users():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM allowed_users")
        return [row[0] for row in c.fetchall()]

def add_allowed_user(user_id: int, added_by: int):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at)
            VALUES (?, ?, ?)""", (user_id, added_by, datetime.now()))

def remove_allowed_user(user_id: int):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))

def get_premium_users():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, premium_until FROM users WHERE is_premium = TRUE")
        return c.fetchall()

def set_premium(user_id: int, until: Optional[str] = None):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""UPDATE users SET is_premium = TRUE, premium_until = ? WHERE user_id = ?""", (until, user_id))

def remove_premium(user_id: int):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""UPDATE users SET is_premium = FALSE, premium_until = NULL WHERE user_id = ?""", (user_id,))

def log_action(user_id: int, action_name: str, target_name: str):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO action_logs (user_id, action_name, target_name, used_at)
            VALUES (?, ?, ?, ?)""", (user_id, action_name, target_name, datetime.now()))

def check_access(user_id: int) -> bool:
    return is_creator(user_id) or is_trusted(user_id)

def format_name(name: str) -> str:
    return f"<b><u>{name}</u></b>"

def build_menu_text(title: str, lines: List[str]) -> str:
    text = f"🌙 <b>{title}</b>\n"
    text += "━" * 16 + "\n\n"
    for line in lines:
        text += line + "\n"
    return text.rstrip("\n") + "\n\n"

def normalize_username_placeholders(text: str) -> str:
    text = text.replace("Username1", "Username1")
    text = text.replace("Username2", "Username2")
    return text

async def resolve_user_identifier(context: ContextTypes.DEFAULT_TYPE, identifier: str) -> Optional[int]:
    if not identifier:
        return None
    identifier = identifier.strip()
    if identifier.startswith("@"):
        identifier = identifier[1:]
    try:
        if identifier.isdigit():
            return int(identifier)
        else:
            chat = await context.bot.get_chat(f"@{identifier}")
            return chat.id
    except Exception as e:
        logger.warning(f"Failed to resolve user {identifier}: {e}")
        return None

# ===== ТУТОРИАЛ =====
async def tutorial_menu(query):
    text = """📚 <b>Добро пожаловать в DotBotRPG!</b>
━━━━━━━━━━━━━━━━━━━

<b>🤖 Что такое DotBotRPG?</b>
Это бот для взаимодействия с другими пользователями через действия.

━━━━━━━━━━━━━━━━━━━
<b>📌 ИНЛАЙН-РЕЖИМ</b>

В любом чате напиши:
<code>@Dot_bbot Обнять @username</code>

В ЛС:
<code>@Dot_bbot Обнять</code>

━━━━━━━━━━━━━━━━━━━
<b>📌 КАК СОЗДАТЬ СВОЁ ДЕЙСТВИЕ</b>

1. /start → Создать действие
2. Введи название
3. Введи ответ для мужского пола (Username1 и Username2)
4. Введи ответ для женского пола
5. Готово!

━━━━━━━━━━━━━━━━━━━
<b>📌 ПРЕМИУМ</b>

• 25 кастомных действий (вместо 5)
• Эмодзи в действиях
• Смена имени

💳 199 ₽/месяц или 1 490 ₽ навсегда

━━━━━━━━━━━━━━━━━━━
🌙 <b>Приятной игры!</b>"""
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== ИНЛАЙН-РЕЖИМ =====
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.strip()
    user_id = update.effective_user.id
    chat_type = update.inline_query.chat_type
    chat_id = update.inline_query.chat_id
    
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
    
    user = get_user(user_id)
    if not user:
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
    
    # ===== ПАРСИНГ ЗАПРОСА =====
    action = query_text
    target_name = None
    target_id = None
    
    # 1. Ищем @username
    for word in query_text.split():
        if word.startswith("@"):
            target_name = word[1:]
            action = query_text.replace(word, "").strip()
            break
    
    # Если есть @username — пробуем получить имя пользователя
    if target_name:
        try:
            target_user = await context.bot.get_chat(f"@{target_name}")
            if target_user and target_user.first_name:
                target_name = target_user.first_name
                if target_user.last_name:
                    target_name += " " + target_user.last_name
                target_id = target_user.id
        except Exception:
            pass
    
    # 2. Если нет @username и это ЛС
    if not target_name and chat_type == "private":
        target_name = "Собеседник"
    
    # 3. Если нет цели
    if not target_name:
        target_name = "Собеседник"
    
    # ===== ГЕНЕРАЦИЯ ОТВЕТА =====
    sender_name = user["custom_name"] or user["first_name"] or "Пользователь"
    sender_gender = user["gender"] or "male"
    sender_f = format_name(sender_name)
    target_f = format_name(target_name)
    
    response = None
    action_found = None
    emoji = ""
    
    # Кастомные действия
    custom = get_custom_actions(user_id)
    for c in custom:
        if c["trigger"].lower() == action.lower():
            action_found = c["trigger"]
            template = c["response_male"] if sender_gender == "male" else c["response_female"]
            emoji = c["emoji"] or ""
            template = template.replace("Username1", sender_f).replace("Username2", target_f)
            response = f"{emoji} | <b>{template}</b>"
            with get_db_connection() as conn:
                conn.execute("UPDATE custom_actions SET uses = uses + 1 WHERE id = ?", (c["id"],))
            break
    
    # Встроенные действия
    if not response and action.lower() in DEFAULT_ACTIONS:
        action_found = action.lower()
        data = DEFAULT_ACTIONS[action_found]
        verb = data["male"] if sender_gender == "male" else data["female"]
        emoji = data["emoji"]
        response = f"{emoji} | <b>{sender_f} {verb} {target_f}</b>"
    
    if response:
        log_action(user_id, action_found or action, target_name)
        await update.inline_query.answer([
            InlineQueryResultArticle(
                id=action_found or "action",
                title=f"{action.capitalize()} → {target_name}",
                description=re.sub(r"<[^>]+>", "", response),
                input_message_content=InputTextMessageContent(response, parse_mode="HTML")
            )
        ], cache_time=0)
        return
    
    await update.inline_query.answer([
        InlineQueryResultArticle(
            id="notfound",
            title="🤖 Такого действия нет!",
            description="Попробуйте: обнять, поцеловать, ударить",
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
    
    user = get_user(user_id)
    if user is None:
        keyboard = [[
            InlineKeyboardButton("👦 Мужской", callback_data="gender_male"),
            InlineKeyboardButton("👧 Женский", callback_data="gender_female")
        ]]
        text = build_menu_text(
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
    
    name = user["custom_name"] or user["first_name"]
    role = user["role"]
    
    if role == "creator":
        keyboard = [
            [InlineKeyboardButton("📋 Мои действия", callback_data="my_actions"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action"),
             InlineKeyboardButton("🗑️ Удалить действие", callback_data="delete_action")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="users"),
             InlineKeyboardButton("📚 Туториал", callback_data="tutorial")],
            [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Все действия", callback_data="all_actions"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action"),
             InlineKeyboardButton("📚 Туториал", callback_data="tutorial")],
            [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    
    text = build_menu_text(
        "DotBotRPG — Главное меню",
        [
            f"👋 Привет, <b>{name}</b>!",
            "",
            "⬇️ Выберите действие:"
        ]
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
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
    
    name = user["custom_name"] or user["first_name"]
    role = user["role"]
    
    if role == "creator":
        keyboard = [
            [InlineKeyboardButton("📋 Мои действия", callback_data="my_actions"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action"),
             InlineKeyboardButton("🗑️ Удалить действие", callback_data="delete_action")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="users"),
             InlineKeyboardButton("📚 Туториал", callback_data="tutorial")],
            [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("📋 Все действия", callback_data="all_actions"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("➕ Создать действие", callback_data="create_action"),
             InlineKeyboardButton("📚 Туториал", callback_data="tutorial")],
            [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
        ]
    
    text = build_menu_text(
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
    
    gender = "Мужской" if user["gender"] == "male" else "Женский"
    name = user["custom_name"] or user["first_name"]
    role = user["role"]
    is_prem = user["is_premium"]
    prem_until = user["premium_until"]
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
    
    text = build_menu_text("Настройки", lines)
    
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
    if not user or (not user["is_premium"] and user["role"] != "creator"):
        await query.edit_message_text("🔒 Смена имени доступна только в Премиум-версии.")
        return
    
    text = build_menu_text(
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
    if not user or (not user["is_premium"] and user["role"] != "creator"):
        await update.message.reply_text("🔒 Смена имени доступна только в Премиум-версии.")
        return
    
    update_user_name(user_id, new_name)
    get_user_cached.cache_clear()
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
    get_user_cached.cache_clear()
    await query.edit_message_text(f"✅ Пол изменён на <b>{'Мужской' if gender == 'male' else 'Женский'}</b>!", parse_mode="HTML")
    await settings_menu(query)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM custom_actions")
        total_actions = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM action_logs")
        total_uses = c.fetchone()[0]
        c.execute("""SELECT action_name, COUNT(*) FROM action_logs
            GROUP BY action_name ORDER BY COUNT(*) DESC LIMIT 5""")
        top_actions = c.fetchall()
    
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
    
    text = build_menu_text("Статистика", lines)
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
            lines.append(f"• {c['trigger'].capitalize()}")
    else:
        lines.append("")
        lines.append("🔸 У вас нет кастомных действий.")
    
    lines.extend([
        "",
        "📌 <b>Как использовать:</b>",
        "В любом чате напишите:",
        "<code>Обнять @username</code>"
    ])
    
    text = build_menu_text("Доступные действия", lines)
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
            lines.append(f"{i}. {c['trigger'].capitalize()} (использовано: {c['uses']} раз)")
    
    text = build_menu_text("Ваши действия", lines)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== СОЗДАНИЕ ДЕЙСТВИЙ =====
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
    
    max_actions = 999 if user["role"] == "creator" else 25 if user["is_premium"] else 5
    current = get_user_actions_count(user_id)
    if current >= max_actions:
        limit_text = "безлимитный" if user["role"] == "creator" else str(max_actions)
        extra = "Оформите Премиум для доступа к 25 действиям." if not user["is_premium"] and user["role"] != "creator" else ""
        await query.edit_message_text(
            f"❌ Вы достигли лимита в <b>{limit_text}</b> кастомных действий.\n\n{extra}",
            parse_mode="HTML"
        )
        return
    
    text = build_menu_text(
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
            if c["trigger"].lower() == text.lower():
                await update.message.reply_text("⚠️ Действие с таким названием уже есть (кастомное).")
                return
        
        data["trigger"] = text
        data["step"] = "male_response"
        await update.message.reply_text(
            build_menu_text(
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
            build_menu_text(
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
        if user and (user["is_premium"] or user["role"] == "creator"):
            keyboard = [[InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_emoji")]]
            await update.message.reply_text(
                build_menu_text(
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
        pass

async def handle_emoji_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    if "creating_action" not in context.user_data:
        return
    
    data = context.user_data["creating_action"]
    text = update.message.text.strip()
    
    if text == "/cancel":
        context.user_data.pop("creating_action", None)
        context.user_data.pop("creating_action_emoji", None)
        await update.message.reply_text("❌ Создание действия отменено.")
        await show_main_menu(update, context)
        return
    
    if len(text) > 2:
        await update.message.reply_text("❌ Отправьте ОДИН эмодзи или нажмите 'Пропустить'.")
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
    if not check_access(user_id):
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

# ===== УДАЛЕНИЕ ДЕЙСТВИЙ =====
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
        keyboard.append([InlineKeyboardButton(f"🗑️ {c['trigger'].capitalize()}", callback_data=f"delete_{c['id']}")])
    
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
    text = build_menu_text(
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

# ===== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ =====
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
            name = u["first_name"] if u else str(uid)
            premium = "⭐ Премиум" if u and u["is_premium"] else "🔰 Бесплатный"
            lines.append(f"{i}. {name} (ID: {uid}) — {premium}")
        if len(allowed) > 10:
            lines.append(f"... и ещё {len(allowed) - 10} пользователей")
    
    text = build_menu_text("Пользователи", lines)
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
    
    text = build_menu_text(
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
    
    target_id = await resolve_user_identifier(context, text)
    if target_id is None:
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
        name = u["first_name"] if u else str(uid)
        keyboard.append([InlineKeyboardButton(f"❌ {name}", callback_data=f"remove_{uid}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    
    text = build_menu_text("Удаление пользователя", ["Выберите пользователя:"])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def remove_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    target_id = int(query.data.split("_")[1])
    remove_allowed_user(target_id)
    get_user_cached.cache_clear()
    await query.edit_message_text("✅ Доступ отозван.")
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
    
    if user["role"] == "creator":
        premium_users = get_premium_users()
        free_users = len(get_allowed_users()) - len(premium_users)
        lines = [
            "👑 <b>Ваш статус:</b> Создатель",
            f"📊 <b>Премиум-пользователей:</b> {len(premium_users)}",
            f"📊 <b>Бесплатных пользователей:</b> {free_users}",
            "",
            "<b>Управление:</b>"
        ]
        text = build_menu_text("Премиум-система", lines)
        keyboard = [
            [InlineKeyboardButton("📋 Список премиум", callback_data="premium_list")],
            [InlineKeyboardButton("⭐ Выдать премиум", callback_data="give_premium")],
            [InlineKeyboardButton("❌ Забрать премиум", callback_data="remove_premium")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    if user["is_premium"]:
        lines = [
            "👤 <b>Статус:</b> Премиум",
            f"📊 <b>Действий создано:</b> {get_user_actions_count(user_id)} из 25",
            "✨ <b>Эмодзи:</b> доступны",
            "✏️ <b>Смена имени:</b> доступна"
        ]
        if user["premium_until"]:
            lines.append(f"📅 <b>Активен до:</b> {user['premium_until'][:10]}")
        else:
            lines.append("📅 <b>Активен:</b> навсегда")
        lines.extend(["", "Спасибо, что поддерживаете проект! 💜"])
        text = build_menu_text("Ваш Премиум активен!", lines)
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
        text = build_menu_text("DotBotRPG Премиум", lines)
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
        name = u["first_name"] if u else str(uid)
        status = "навсегда" if until is None else until[:10]
        lines.append(f"• {name} — {status}")
    
    text = build_menu_text("Премиум-пользователи", lines)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="premium")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def give_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    text = build_menu_text(
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
    
    target_id = await resolve_user_identifier(context, text)
    if target_id is None:
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
    get_user_cached.cache_clear()
    await query.edit_message_text(f"✅ <b>Премиум выдан!</b> {'1 месяц' if period == 'month' else 'Навсегда'}", parse_mode="HTML")
    await premium_menu(update, context)

async def remove_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    text = build_menu_text(
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
    
    target_id = await resolve_user_identifier(context, text)
    if target_id is None:
        await update.message.reply_text("❌ Пользователь не найден.")
        return
    
    remove_premium(target_id)
    get_user_cached.cache_clear()
    context.user_data.pop("removing_premium", None)
    await update.message.reply_text("✅ Премиум отозван!")
    await show_main_menu(update, context)

# ===== ОБРАБОТЧИК КНОПОК =====
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
        get_user_cached.cache_clear()
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
    
    elif data == "tutorial":
        await tutorial_menu(query)
    
    elif data == "noop":
        pass

# ===== КОМАНДЫ ПОМОЩИ И ОТМЕНЫ =====
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
        "В ЛС: @Dot_bbot <Действие>",
        "В группах: @Dot_bbot <Действие> @username",
        "",
        "📌 <b>Встроенные действия (20 шт.):</b>",
        ", ".join([a.capitalize() for a in DEFAULT_ACTIONS.keys()])
    ])
    
    text = build_menu_text("DotBotRPG — помощь", lines)
    await update.message.reply_text(text, parse_mode="HTML")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено")
    await show_main_menu(update, context)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ===== ОСНОВНОЙ ЗАПУСК =====
async def main():
    print("🚀 Инициализация базы данных...")
    init_db()
    
    print("🔧 Создание приложения...")
    print(f"🔑 Токен: {TOKEN[:10]}...")  # Отладка
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    print("=" * 50)
    print("🌙 DotBotRPG запущен!")
    print(f"👑 Создатель: {CREATOR_ID}")
    print(f"📋 Действий: {len(DEFAULT_ACTIONS)}")
    print(f"💾 База данных: {DB_PATH}")
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
