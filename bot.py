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

# ===== СМЕНА ИМЕНИ =====
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

# ===== СТАТИСТИКА =====
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

# ===== ВСЕ ДЕЙСТВИЯ =====
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

# ===== МОИ ДЕЙСТВИЯ =====
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

# ===== ПОЛЬЗОВАТЕЛИ =====
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

# ===== HELP =====
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
        "@DotBotRPG_bot <Действие> @username",
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
