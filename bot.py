import logging
import os
import sqlite3
from datetime import datetime, timedelta
import asyncio
import re
from functools import lru_cache
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, InlineQueryHandler, MessageHandler, filters

# ===== КОНФИГУРАЦИЯ =====
# ТОКЕН ТОЛЬКО ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ!
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set in environment variables!")

CREATOR_ID = int(os.environ.get("CREATOR_ID", 8269156736))
TELEGRAM_API_PROXY = os.environ.get("TELEGRAM_API_PROXY", None)
DB_PATH = os.environ.get("DB_PATH", "/data/dotbot.db")

# Если файл БД не существует, создаём в локальной папке
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

# ===== КОНТЕКСТНЫЙ МЕНЕДЖЕР ДЛЯ БД =====
@contextmanager
def get_db_connection():
    """Контекстный менеджер для соединения с БД"""
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

# ===== БАЗА ДАННЫХ =====
def init_db():
    """Инициализация базы данных"""
    with get_db_connection() as conn:
        c = conn.cursor()
        
        # Таблица пользователей
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
        
        # Таблица доверенных пользователей
        c.execute("""CREATE TABLE IF NOT EXISTS allowed_users (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TIMESTAMP
        )""")
        
        # Таблица кастомных действий
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
        
        # Таблица логов действий
        c.execute("""CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_name TEXT,
            target_name TEXT,
            used_at TIMESTAMP
        )""")
        
        # Таблица имен пользователей
        c.execute("""CREATE TABLE IF NOT EXISTS user_names (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            custom_name TEXT,
            updated_at TIMESTAMP
        )""")
        
        # Таблица для ZAPOMNIT
        c.execute("""CREATE TABLE IF NOT EXISTS private_chat_partners (
            chat_id INTEGER,
            user_id INTEGER,
            partner_id INTEGER,
            partner_name TEXT,
            updated_at TIMESTAMP,
            PRIMARY KEY (chat_id, user_id)
        )""")
        
        # Добавляем создателя
        c.execute("""INSERT OR IGNORE INTO users (user_id, first_name, gender, role, registered_at)
            VALUES (?, ?, ?, ?, ?)""", (CREATOR_ID, "𝓜𝓪𝓭𝓪𝓶", "female", "creator", datetime.now()))
        
        c.execute("""INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at)
            VALUES (?, ?, ?)""", (CREATOR_ID, CREATOR_ID, datetime.now()))
    
    logger.info("✅ База данных инициализирована")

def get_user(user_id: int) -> Optional[tuple]:
    """Получение пользователя из БД"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone()

@lru_cache(maxsize=128)
def get_user_cached(user_id: int) -> Optional[tuple]:
    """Кешированное получение пользователя"""
    return get_user(user_id)

def register_user(user_id: int, first_name: str, gender: str = "male"):
    """Регистрация нового пользователя"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT OR IGNORE INTO users (user_id, first_name, gender, registered_at)
            VALUES (?, ?, ?, ?)""", (user_id, first_name, gender, datetime.now()))

def update_user_gender(user_id: int, gender: str):
    """Обновление пола пользователя"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET gender = ? WHERE user_id = ?", (gender, user_id))

def update_user_name(user_id: int, name: str):
    """Обновление имени пользователя"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET custom_name = ? WHERE user_id = ?", (name, user_id))
        get_user_cached.cache_clear()

def is_trusted(user_id: int) -> bool:
    """Проверка доверенного пользователя"""
    if user_id == CREATOR_ID:
        return True
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM allowed_users WHERE user_id = ?", (user_id,))
        return c.fetchone() is not None

def is_creator(user_id: int) -> bool:
    """Проверка создателя"""
    return user_id == CREATOR_ID

def get_custom_actions(user_id: Optional[int] = None) -> List[tuple]:
    """Получение кастомных действий"""
    with get_db_connection() as conn:
        c = conn.cursor()
        if user_id is not None:
            c.execute("SELECT id, trigger, response_male, response_female, emoji, uses FROM custom_actions WHERE owner_id = ? ORDER BY id", (user_id,))
        else:
            c.execute("SELECT id, trigger, response_male, response_female, emoji, uses FROM custom_actions ORDER BY id")
        return c.fetchall()

def add_custom_action(owner_id: int, trigger: str, response_male: str, response_female: str, emoji: str = ""):
    """Добавление кастомного действия"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO custom_actions (owner_id, trigger, response_male, response_female, emoji, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""", (owner_id, trigger.lower(), response_male, response_female, emoji, datetime.now()))

def delete_custom_action(action_id: int):
    """Удаление кастомного действия"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM custom_actions WHERE id = ?", (action_id,))

def get_user_actions_count(user_id: int) -> int:
    """Количество действий пользователя"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM custom_actions WHERE owner_id = ?", (user_id,))
        return c.fetchone()[0]

def get_allowed_users() -> List[int]:
    """Список доверенных пользователей"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM allowed_users")
        return [row[0] for row in c.fetchall()]

def add_allowed_user(user_id: int, added_by: int):
    """Добавление доверенного пользователя"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT OR IGNORE INTO allowed_users (user_id, added_by, added_at)
            VALUES (?, ?, ?)""", (user_id, added_by, datetime.now()))

def remove_allowed_user(user_id: int):
    """Удаление доверенного пользователя"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))

def get_premium_users() -> List[tuple]:
    """Список премиум-пользователей"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, premium_until FROM users WHERE is_premium = TRUE")
        return c.fetchall()

def set_premium(user_id: int, until: Optional[str] = None):
    """Выдача премиума"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""UPDATE users SET is_premium = TRUE, premium_until = ? WHERE user_id = ?""", (until, user_id))

def remove_premium(user_id: int):
    """Отзыв премиума"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""UPDATE users SET is_premium = FALSE, premium_until = NULL WHERE user_id = ?""", (user_id,))

def log_action(user_id: int, action_name: str, target_name: str):
    """Логирование действия"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO action_logs (user_id, action_name, target_name, used_at)
            VALUES (?, ?, ?, ?)""", (user_id, action_name, target_name, datetime.now()))

def check_access(user_id: int) -> bool:
    """Проверка доступа"""
    return is_creator(user_id) or is_trusted(user_id)

def save_user_name(user_id: int, username: str, first_name: str):
    """Сохранение имени пользователя"""
    if not username:
        return
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO user_names (user_id, username, first_name, updated_at)
            VALUES (?, ?, ?, ?)""", (user_id, username, first_name, datetime.now()))

def get_user_display_name(username: str) -> str:
    """Получение отображаемого имени пользователя"""
    if not username:
        return username
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, first_name, custom_name FROM user_names WHERE username = ?", (username,))
        result = c.fetchone()
        if result:
            user = get_user(result[0])
            if user and user[U_CUSTOM_NAME]:
                return user[U_CUSTOM_NAME]
            if result[1]:
                return result[1]
    return username

def save_private_chat_partner(chat_id: int, user_id: int, partner_id: int, partner_name: str):
    """Сохранение собеседника для ZAPOMNIT"""
    if not partner_name:
        return
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO private_chat_partners 
            (chat_id, user_id, partner_id, partner_name, updated_at)
            VALUES (?, ?, ?, ?, ?)""", 
            (chat_id, user_id, partner_id, partner_name, datetime.now()))

def get_private_chat_partner(chat_id: int, user_id: int) -> Tuple[Optional[str], Optional[int]]:
    """Получение сохраненного собеседника"""
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""SELECT partner_name, partner_id FROM private_chat_partners 
            WHERE chat_id = ? AND user_id = ?""", (chat_id, user_id))
        result = c.fetchone()
        if result:
            return result[0], result[1]
    return None, None

# ===== УТИЛИТЫ =====
def format_name(name: str) -> str:
    """Форматирование имени (жирный + подчеркнутый)"""
    return f"<b><u>{name}</u></b>"

def build_menu_text(title: str, lines: List[str]) -> str:
    """Построение текста меню"""
    text = f"🌙 <b>{title}</b>\n"
    text += "━" * 16 + "\n\n"
    for line in lines:
        text += line + "\n"
    return text.rstrip("\n") + "\n\n"

def normalize_username_placeholders(text: str) -> str:
    """Нормализация плейсхолдеров Username1 и Username2"""
    text = text.replace("Username1", "Username1")
    text = text.replace("Username2", "Username2")
    return text

def is_valid_emoji(char: str) -> bool:
    """Проверка, является ли символ эмодзи"""
    try:
        import emoji
        return emoji.is_emoji(char)
    except ImportError:
        # Простая проверка, если библиотека не установлена
        emoji_pattern = re.compile(
            "["
            u"\U0001F600-\U0001F64F"  # Смайлики
            u"\U0001F300-\U0001F5FF"  # Символы и пиктограммы
            u"\U0001F680-\U0001F6FF"  # Транспорт
            u"\U0001F700-\U0001F77F"  # Алхимические символы
            u"\U0001F780-\U0001F7FF"  # Геометрические фигуры
            u"\U0001F800-\U0001F8FF"  # Дополнительные стрелки
            u"\U0001F900-\U0001F9FF"  # Дополнительные символы
            u"\U0001FA00-\U0001FA6F"  # Шахматы
            u"\U0001FA70-\U0001FAFF"  # Дополнительные символы
            u"\u2600-\u26FF"          # Разные символы
            u"\u2700-\u27BF"          # Пиктограммы
            "]+",
            flags=re.UNICODE
        )
        return bool(emoji_pattern.fullmatch(char))
    except:
        return False

# ===== ПОИСК ПОЛЬЗОВАТЕЛЯ =====
async def resolve_user_identifier(context: ContextTypes.DEFAULT_TYPE, identifier: str) -> Optional[int]:
    """Разрешение идентификатора пользователя (ID или @username)"""
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
    """Отображение туториала"""
    text = """📚 <b>Добро пожаловать в DotBotRPG!</b>
━━━━━━━━━━━━━━━━━━━

<b>🤖 Что такое DotBotRPG?</b>
Это бот для взаимодействия с другими пользователями через действия. Ты можешь обнимать, целовать, шутить и создавать свои собственные действия!

━━━━━━━━━━━━━━━━━━━
<b>📌 1. ИНЛАЙН-РЕЖИМ</b>

В любом чате напиши:
<code>@DotBotRPG_bot Обнять @username</code>

<b>В личных чатах (ЛС):</b>
<code>@DotBotRPG_bot Обнять</code>
Бот сам определит собеседника (если ты его запомнил через ZAPOMNIT).

<b>В группах:</b>
<code>@DotBotRPG_bot Обнять @petya</code>
Нужно указывать @username.

━━━━━━━━━━━━━━━━━━━
<b>📌 2. КАК ЗАПОМНИТЬ СОБЕСЕДНИКА (ZAPOMNIT)</b>

Хочешь, чтобы бот запомнил собеседника в ЛС?
Просто напиши в ЛС:

<code>@DotBotRPG_bot ZAPOMNIT Имя</code>

Например:
<code>@DotBotRPG_bot ZAPOMNIT Паша</code>

<b>После этого:</b>
Просто пиши <code>@DotBotRPG_bot обнять</code>
И бот сам поймёт, что обнять надо Пашу! ✅

<b>Важно!</b> Это работает ТОЛЬКО в этом ЛС и ТОЛЬКО для тебя.

━━━━━━━━━━━━━━━━━━━
<b>📌 3. КАК СОЗДАТЬ СВОЁ ДЕЙСТВИЕ</b>

1. Напиши /start
2. Нажми <b>➕ Создать действие</b>
3. Введи название (например, "Чмокнуть")
4. Введи ответ для МУЖСКОГО пола:
   <code>Username1 чмокнул Username2 и убежал</code>
5. Введи ответ для ЖЕНСКОГО пола:
   <code>Username1 чмокнула Username2 и убежала</code>
6. Добавь эмодзи (или пропусти)
7. Готово! ✅

<b>Теперь используй:</b>
<code>@DotBotRPG_bot Чмокнуть @username</code>

━━━━━━━━━━━━━━━━━━━
<b>📌 4. ВСТРОЕННЫЕ ДЕЙСТВИЯ (20 шт.)</b>

Обнять, Ударить, Погладить, Поцеловать, Сесть,
Успокоить, Поговорить, Пожениться, Завести отношения,
Укусить, Щекотка, Подарить цветы, Обнять крепко,
Потанцевать, Спеть, Приготовить еду, Сделать массаж,
Поздравить, Извиниться, Попросить прощения

━━━━━━━━━━━━━━━━━━━
<b>📌 5. ПРЕМИУМ</b>

• 25 кастомных действий (вместо 5)
• Эмодзи в действиях
• Смена имени в настройках

💳 199 ₽/месяц или 1 490 ₽ навсегда

━━━━━━━━━━━━━━━━━━━
<b>📌 6. КОМАНДЫ В ЛС</b>

/start — Главное меню
/menu — Главное меню
/settings — Настройки
/custom — Создать действие
/cancel — Отменить создание
/help — Помощь

━━━━━━━━━━━━━━━━━━━
<b>❓ Остались вопросы?</b>
Напиши /help

🌙 <b>Приятной игры!</b>"""

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== ИНЛАЙН-РЕЖИМ =====
async def handle_zapomnit(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str, user_id: int, chat_type: str) -> bool:
    """Обработка команды ZAPOMNIT"""
    if query_text.lower().startswith("zapomnit") and chat_type == "private":
        parts = query_text.split(" ", 1)
        if len(parts) >= 2:
            name = parts[1].strip()
            chat_id = update.inline_query.chat_id
            if name:
                save_private_chat_partner(chat_id, user_id, 0, name)
                await update.inline_query.answer([
                    InlineQueryResultArticle(
                        id="zapomnit",
                        title="✅ Запомнил!",
                        description=f"Собеседник теперь: {name}",
                        input_message_content=InputTextMessageContent(
                            f"✅ <b>Запомнил!</b>\n\nТеперь я буду показывать <b>{name}</b> вместо 'Собеседник' в этом ЛС.",
                            parse_mode="HTML"
                        )
                    )
                ], cache_time=0)
                return True
    return False

def parse_inline_query(query_text: str) -> Tuple[str, str]:
    """Парсинг инлайн-запроса на действие и цель"""
    if not query_text:
        return "", ""
    
    # Ищем @username
    target_input = ""
    action = query_text
    
    # Проверяем кастомные действия
    custom = get_custom_actions()
    for c in custom:
        trigger = c[1]
        if query_text.lower().startswith(trigger.lower()):
            action = trigger
            rest = query_text[len(trigger):].strip()
            if rest.startswith("@"):
                target_input = rest[1:]
            else:
                target_input = rest
            return action, target_input
    
    # Проверяем встроенные действия
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
    
    # Если не нашли цель, ищем @ в любом месте
    if not target_input:
        words = query_text.split(" ")
        for i, w in enumerate(words):
            if w.startswith("@"):
                target_input = w[1:]
                action = " ".join(words[:i]).strip()
                if not action and i > 0:
                    action = " ".join(words[:i])
                break
    
    return action, target_input

async def get_sender_info(user_id: int, update: Update) -> Tuple[str, str]:
    """Получение информации об отправителе"""
    user = get_user(user_id)
    if not user:
        return "male", "Пользователь"
    
    gender = user[U_GENDER] if user else "male"
    name = user[U_CUSTOM_NAME] or user[U_FIRST_NAME] or update.effective_user.first_name or "Пользователь"
    return gender, name

async def get_target_info(target_input: str, chat_type: str, chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> Tuple[str, Optional[int]]:
    """Получение информации о цели"""
    target_display_name = None
    target_id = None
    
    if target_input:
        # Если указан @username
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
    elif chat_type == "private":
        # В ЛС без @username — берём из private_chat_partners
        partner_name, partner_id = get_private_chat_partner(chat_id, user_id)
        if partner_name:
            target_display_name = partner_name
            target_id = partner_id
        else:
            target_display_name = "Собеседник"
    
    if not target_display_name:
        target_display_name = target_input or "Собеседник"
    
    return target_display_name, target_id

def generate_action_response(action: str, sender_gender: str, sender_name: str, target_name: str, user_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Генерация ответа на действие"""
    # Проверяем кастомные действия
    custom = get_custom_actions(user_id)
    for c in custom:
        if c[1].lower() == action.lower():
            action_found = c[1]
            template = c[2] if sender_gender == "male" else c[3]
            emoji = c[4] or ""
            template = template.replace("Username1", sender_name)
            template = template.replace("Username2", target_name)
            response = f"{emoji} | <b>{template}</b>"
            
            # Увеличиваем счетчик использования
            with get_db_connection() as conn:
                conn.execute("UPDATE custom_actions SET uses = uses + 1 WHERE id = ?", (c[0],))
            
            return response, action_found
    
    # Проверяем встроенные действия
    if action.lower() in DEFAULT_ACTIONS:
        action_found = action.lower()
        data = DEFAULT_ACTIONS[action_found]
        verb = data["male"] if sender_gender == "male" else data["female"]
        emoji = data["emoji"]
        response = f"{emoji} | <b>{sender_name} {verb} {target_name}</b>"
        return response, action_found
    
    return None, None

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка инлайн-запросов"""
    query_text = update.inline_query.query.strip()
    user_id = update.effective_user.id
    chat_type = update.inline_query.chat_type
    chat_id = update.inline_query.chat_id
    
    # Проверка доступа
    if not check_access(user_id):
        await update.inline_query.answer([], cache_time=0)
        return
    
    # Пустой запрос - показываем помощь
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
    
    # Проверка регистрации пользователя
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
    
    # Обработка ZAPOMNIT
    if await handle_zapomnit(update, context, query_text, user_id, chat_type):
        return
    
    # Парсинг запроса
    action, target_input = parse_inline_query(query_text)
    
    # Получение информации об отправителе
    sender_gender, sender_name = await get_sender_info(user_id, update)
    sender_name_f = format_name(sender_name)
    
    # Получение информации о цели
    target_display_name, target_id = await get_target_info(
        target_input, chat_type, chat_id, user_id, context
    )
    target_name_f = format_name(target_display_name)
    
    # Генерация ответа
    response, action_found = generate_action_response(
        action, sender_gender, sender_name_f, target_name_f, user_id
    )
    
    if response:
        log_action(user_id, action_found, target_display_name)
        await update.inline_query.answer([
            InlineQueryResultArticle(
                id=action_found or "action",
                title=f"{action_found.capitalize() if action_found else action.capitalize()} → {target_display_name}",
                description=response.replace("<b>", "").replace("</b>", "").replace("<u>", "").replace("</u>", ""),
                input_message_content=InputTextMessageContent(response, parse_mode="HTML")
            )
        ], cache_time=0)
        return
    
    # Действие не найдено
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
    """Обработка текстового ввода"""
    user_id = update.effective_user.id
    if not check_access(user_id):
        return
    
    # Сохраняем информацию о пользователе
    if update.effective_user:
        username = update.effective_user.username
        first_name = update.effective_user.first_name
        if username and first_name:
            save_user_name(user_id, username, first_name)
    
    # Автоматическое сохранение собеседника при ответе на сообщение
    if update.message and update.message.reply_to_message:
        reply_user = update.message.reply_to_message.from_user
        if reply_user and reply_user.id != user_id:
            chat_id = update.effective_chat.id
            partner_name = reply_user.first_name
            if reply_user.last_name:
                partner_name += " " + reply_user.last_name
            save_private_chat_partner(chat_id, user_id, reply_user.id, partner_name)
            save_private_chat_partner(chat_id, reply_user.id, user_id, update.effective_user.first_name)
    
    # Обработка состояний
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
    """Команда /start"""
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
    """Показать главное меню"""
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
    """Показать главное меню из callback-запроса"""
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
    """Меню настроек"""
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
    
    text = build_menu_text("Настройки", lines)
    
    keyboard = []
    if is_prem or role == "creator":
        keyboard.append([InlineKeyboardButton("✏️ Изменить имя", callback_data="change_name")])
    keyboard.append([InlineKeyboardButton("🔄 Сменить пол", callback_data="change_gender")])
    keyboard.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def change_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало смены имени"""
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    user = get_user(user_id)
    if not user or (not user[U_IS_PREMIUM] and user[U_ROLE] != "creator"):
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
    """Обработка ввода нового имени"""
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
    get_user_cached.cache_clear()
    context.user_data["changing_name"] = False
    await update.message.reply_text(f"✅ Имя изменено на <b>&quot;{new_name}&quot;</b>!", parse_mode="HTML")
    await show_main_menu(update, context)

async def change_gender_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало смены пола"""
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
    """Установка пола"""
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
    """Показ статистики"""
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
    """Меню всех действий"""
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
    
    text = build_menu_text("Доступные действия", lines)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def my_actions_menu(query):
    """Меню моих действий"""
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
    
    text = build_menu_text("Ваши действия", lines)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== СОЗДАНИЕ ДЕЙСТВИЙ =====
async def create_action_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания действия"""
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
    """Обработка ввода при создании действия"""
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
        if user and (user[U_IS_PREMIUM] or user[U_ROLE] == "creator"):
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
        # Обработка эмодзи через отдельную функцию
        pass

async def handle_emoji_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода эмодзи"""
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
    
    if not is_valid_emoji(text):
        await update.message.reply_text("❌ Это не эмодзи. Отправьте один эмодзи или нажмите 'Пропустить'.")
        return
    
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
    """Пропуск эмодзи"""
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
    """Начало удаления действия"""
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    await show_delete_page(query, context, 1)

async def show_delete_page(query, context, page):
    """Показать страницу удаления"""
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
    """Подтверждение удаления действия"""
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
    """Обработчик смены страницы удаления"""
    query = update.callback_query
    user_id = query.from_user.id
    if not check_access(user_id) or not is_creator(user_id):
        await query.edit_message_text("❌ Доступ запрещён")
        return
    
    page = int(query.data.split("_")[1])
    await show_delete_page(query, context, page)

# ===== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ =====
async def users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления пользователями"""
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
    
    text = build_menu_text("Пользователи", lines)
    keyboard = [
        [InlineKeyboardButton("➕ Добавить", callback_data="add_user"),
         InlineKeyboardButton("➖ Удалить", callback_data="remove_user")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления пользователя"""
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
    """Обработка ввода при добавлении пользователя"""
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
    """Начало удаления пользователя"""
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
    
    text = build_menu_text("Удаление пользователя", ["Выберите пользователя:"])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def remove_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления пользователя"""
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
    """Меню премиума"""
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
        text = build_menu_text("Премиум-система", lines)
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
            "• 199
