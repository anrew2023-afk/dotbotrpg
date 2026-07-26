import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ApplicationBuilder, InlineQueryHandler
import sqlite3
from datetime import datetime
import asyncio

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

# ===== ИНЛАЙН-РЕЖИМ =====
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.inline_query.query.strip()
    user_id = update.effective_user.id
    
    if not query_text:
        results = [InlineQueryResultArticle(
            id="help",
            title="📖 DotBotRPG",
            description="Введите: trig. <действие> @username",
            input_message_content=InputTextMessageContent("📖 DotBotRPG\nВведите trig. <действие> @username")
        )]
        await update.inline_query.answer(results, cache_time=60)
        return
    
    if not query_text.lower().startswith("trig."):
        results = [InlineQueryResultArticle(
            id="hint",
            title="💡 Начните с trig.",
            description='Пример: trig. Обнять @username',
            input_message_content=InputTextMessageContent('💡 Напишите: trig. <действие> @username')
        )]
        await update.inline_query.answer(results, cache_time=60)
        return
    
    parts = query_text.split(" ", 2)
    if len(parts) < 3:
        results = []
        for action in ["обнять", "поцеловать", "ударить", "погладить"]:
            display = action.capitalize()
            results.append(InlineQueryResultArticle(
                id=action,
                title=display,
                description=f"trig. {display} @username",
                input_message_content=InputTextMessageContent(f"trig. {display} @username")
            ))
        await update.inline_query.answer(results[:5], cache_time=60)
        return
    
    action = parts[1].lower()
    target_input = parts[2].strip()
    if target_input.startswith("@"):
        target_input = target_input[1:]
    
    if target_input == update.effective_user.username:
        results = [InlineQueryResultArticle(
            id="self",
            title="😅 Нельзя на себя!",
            input_message_content=InputTextMessageContent("😅 Нельзя сделать это на самого себя!")
        )]
        await update.inline_query.answer(results, cache_time=0)
        return
    
    if target_input == "DotBotRPG_bot":
        results = [InlineQueryResultArticle(
            id="bot",
            title="🤖 Я бот!",
            input_message_content=InputTextMessageContent("🤖 Я всего лишь бот, но спасибо!")
        )]
        await update.inline_query.answer(results, cache_time=0)
        return
    
    user = get_user(user_id)
    if not user:
        results = [InlineQueryResultArticle(
            id="nouser",
            title="❌ Зарегистрируйтесь!",
            description="Напишите /start",
            input_message_content=InputTextMessageContent("❌ Вы не зарегистрированы! Напишите /start")
        )]
        await update.inline_query.answer(results, cache_time=60)
        return
    
    sender_gender = user[2] if user else 'male'
    sender_name = user[3] if user and user[3] else user[1] if user else update.effective_user.first_name
    
    target_name = target_input
    try:
        target_user = await context.bot.get_chat(f"@{target_input}")
        if target_user and target_user.first_name:
            target_name = target_user.first_name
    except:
        target_name = target_input
    
    if action in DEFAULT_ACTIONS:
        data = DEFAULT_ACTIONS[action]
        verb = data['male'] if sender_gender == 'male' else data['female']
        emoji = data['emoji']
        response = f"{sender_name} {verb} {target_name} {emoji}".strip()
        results = [InlineQueryResultArticle(
            id=action,
            title=f"{action.capitalize()} → {target_name}",
            description=response,
            input_message_content=InputTextMessageContent(response)
        )]
        await update.inline_query.answer(results, cache_time=0)
        return
    
    results = [InlineQueryResultArticle(
        id="notfound",
        title="🤖 Такого действия нет!",
        input_message_content=InputTextMessageContent("🤖 Такого действия нет!")
    )]
    await update.inline_query.answer(results, cache_time=60)

# ===== КОМАНДЫ И МЕНЮ =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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
    user = get_user(update.effective_user.id)
    if not user:
        return
    name = user[3] if user[3] else user[1]
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📋 Все действия", callback_data="all_actions")],
        [InlineKeyboardButton("⭐ Премиум", callback_data="premium")],
        [InlineKeyboardButton("🔄 Сменить пол", callback_data="change_gender")]
    ]
    
    await update.message.reply_text(
        f"📱 DotBotRPG — главное меню\n\n👋 Привет, {name}!\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_main_menu_from_query(query):
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("❌ Ошибка")
        return
    name = user[3] if user[3] else user[1]
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📋 Все действия", callback_data="all_actions")],
        [InlineKeyboardButton("⭐ Премиум", callback_data="premium")],
        [InlineKeyboardButton("🔄 Сменить пол", callback_data="change_gender")]
    ]
    
    await query.edit_message_text(
        f"📱 DotBotRPG — главное меню\n\n👋 Привет, {name}!\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def settings_menu(query):
    user = get_user(query.from_user.id)
    if not user:
        return
    gender = "Мужской" if user[2] == 'male' else "Женский"
    name = user[3] if user[3] else user[1]
    role = "Создатель" if user[5] == 'creator' else "Премиум" if user[6] else "Бесплатный"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Сменить пол", callback_data="change_gender")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    
    await query.edit_message_text(
        f"⚙️ Настройки DotBotRPG\n\n👤 Имя: {name}\n⚧ Пол: {gender}\n📊 Статус: {role}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def all_actions_menu(query):
    text = "📋 Все действия DotBotRPG:\n\n🔹 Встроенные действия (20 шт.):\n"
    for i, (action, data) in enumerate(DEFAULT_ACTIONS.items(), 1):
        text += f"{i}. {action.capitalize()} {data['emoji']}\n"
    
    text += "\n📌 Используй в инлайн-режиме:\n"
    text += "@DotBotRPG_bot trig. Обнять @username"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def premium_menu(query):
    user = get_user(query.from_user.id)
    if not user:
        return
    
    is_premium = user[6] if user else False
    name = user[3] if user[3] else user[1]
    
    if user[5] == 'creator':
        text = "⭐ Премиум-система\n\n👑 Ваш статус: Создатель\n📊 У вас безлимитный доступ ко всем функциям!"
    elif is_premium:
        text = f"⭐ Премиум активен!\n\n👤 {name}\n📊 Статус: Премиум\n✅ 25 кастомных действий\n✅ Эмодзи\n✅ Смена имени\n\nСпасибо, что поддерживаете проект! 💜"
    else:
        text = "⭐ DotBotRPG Премиум\n\n🔓 Что вы получите:\n✅ 25 кастомных действий (вместо 5)\n✅ Эмодзи в действиях\n✅ Смена имени\n✅ Приоритетная поддержка\n\n💳 Тарифы:\n• 199 ₽ / месяц\n• 1 490 ₽ / навсегда"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("gender_"):
        gender = "male" if data == "gender_male" else "female"
        register_user(query.from_user.id, query.from_user.first_name, gender)
        await query.edit_message_text(f"✅ Пол установлен: {'Мужской' if gender == 'male' else 'Женский'}!")
        await show_main_menu_from_query(query)
    
    elif data == "settings":
        await settings_menu(query)
    
    elif data == "all_actions":
        await all_actions_menu(query)
    
    elif data == "premium":
        await premium_menu(query)
    
    elif data == "back":
        await show_main_menu_from_query(query)
    
    elif data == "change_gender":
        keyboard = [[
            InlineKeyboardButton("👦 Мужской", callback_data="set_gender_male"),
            InlineKeyboardButton("👧 Женский", callback_data="set_gender_female")
        ]]
        await query.edit_message_text("Выберите ваш пол:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("set_gender_"):
        gender = "male" if data == "set_gender_male" else "female"
        update_user_gender(query.from_user.id, gender)
        await query.edit_message_text(f"✅ Пол изменён на {'Мужской' if gender == 'male' else 'Женский'}!")
        await settings_menu(query)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 DotBotRPG — помощь\n\n"
        "📌 Команды в ЛС:\n"
        "/start — Главное меню\n"
        "/menu — Главное меню\n"
        "/help — Помощь\n\n"
        "📌 Инлайн-режим (в чатах):\n"
        "@DotBotRPG_bot trig. Обнять @username\n\n"
        "Примеры:\n"
        "@DotBotRPG_bot trig. Обнять @petya\n"
        "@DotBotRPG_bot trig. Поцеловать @masha"
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")

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
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(InlineQueryHandler(inline_query))
    
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
