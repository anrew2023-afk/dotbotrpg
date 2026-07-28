import logging
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta
import asyncio
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ApplicationBuilder, InlineQueryHandler, MessageHandler, filters

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.environ.get("BOT_TOKEN", "8765639328:AAEu7HrWbdaAHWyxu9yl94Qfc4K6HoagFyA")
CREATOR_ID = int(os.environ.get("CREATOR_ID", 8269156736))
TELEGRAM_API_PROXY = os.environ.get("TELEGRAM_API_PROXY", None)
DB_PATH = os.environ.get("DB_PATH", "/data/dotbot.db")
try:
    _db_dir = os.path.dirname(DB_PATH)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)
except Exception as _e:
    print(f"⚠️ Не удалось создать директорию для БД ({DB_PATH}): {_e}")
    DB_PATH = "dotbot.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== HTTP-СЕРВЕР ДЛЯ HEALTH CHECK (Railway) =====
class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    print(f"🩺 Health-check сервер запущен на порту {port}")
    server.serve_forever()

# ===== ВСТРОЕННЫЕ ДЕЙСТВИЯ (150 шт.) =====
# Новая логика: для каждого действия 4 варианта (пол sender + пол target)
DEFAULT_ACTIONS = {
    "скучаю": {
        "male": {"male": "скучает по {target}", "female": "скучает по {target}"},
        "female": {"male": "скучает по {target}", "female": "скучает по {target}"},
        "emoji": "💭"
    },
    "заебал": {
        "male": {"male": "заебал {target}", "female": "заебал {target}"},
        "female": {"male": "заебала {target}", "female": "заебала {target}"},
        "emoji": "😤"
    },
    "обнимаю": {
        "male": {"male": "обнимает {target}", "female": "обнимает {target}"},
        "female": {"male": "обнимает {target}", "female": "обнимает {target}"},
        "emoji": "🤗"
    },
    "отвали": {
        "male": {"male": "отвалил от {target}", "female": "отвалил от {target}"},
        "female": {"male": "отвалила от {target}", "female": "отвалила от {target}"},
        "emoji": "👋"
    },
    "люблю": {
        "male": {"male": "любит {target}", "female": "любит {target}"},
        "female": {"male": "любит {target}", "female": "любит {target}"},
        "emoji": "❤️"
    },
    "нахуй": {
        "male": {"male": "послал нахуй {target}", "female": "послал нахуй {target}"},
        "female": {"male": "послала нахуй {target}", "female": "послала нахуй {target}"},
        "emoji": "🖕"
    },
    "лучший": {
        "male": {"male": "назвал {target} лучшим", "female": "назвал {target} лучшей"},
        "female": {"male": "назвала {target} лучшим", "female": "назвала {target} лучшей"},
        "emoji": "⭐"
    },
    "бесишь": {
        "male": {"male": "бесится на {target}", "female": "бесится на {target}"},
        "female": {"male": "бесится на {target}", "female": "бесится на {target}"},
        "emoji": "😡"
    },
    "рядом": {
        "male": {"male": "рядом с {target}", "female": "рядом с {target}"},
        "female": {"male": "рядом с {target}", "female": "рядом с {target}"},
        "emoji": "👥"
    },
    "надоел": {
        "male": {"male": "надоел {target}", "female": "надоел {target}"},
        "female": {"male": "надоел {target}", "female": "надоел {target}"},
        "emoji": "😩"
    },
    "береги": {
        "male": {"male": "просит {target} беречь себя", "female": "просит {target} беречь себя"},
        "female": {"male": "просит {target} беречь себя", "female": "просит {target} беречь себя"},
        "emoji": "🛡️"
    },
    "заткнись": {
        "male": {"male": "заткнул {target}", "female": "заткнул {target}"},
        "female": {"male": "заткнула {target}", "female": "заткнула {target}"},
        "emoji": "🤫"
    },
    "целую": {
        "male": {"male": "целует {target}", "female": "целует {target}"},
        "female": {"male": "целует {target}", "female": "целует {target}"},
        "emoji": "💋"
    },
    "пошёл": {
        "male": {"male": "послал нахуй {target}", "female": "послал нахуй {target}"},
        "female": {"male": "послала нахуй {target}", "female": "послала нахуй {target}"},
        "emoji": "🚫"
    },
    "классный": {
        "male": {"male": "назвал {target} классным", "female": "назвал {target} классной"},
        "female": {"male": "назвала {target} классным", "female": "назвала {target} классной"},
        "emoji": "👍"
    },
    "задолбал": {
        "male": {"male": "задолбал {target}", "female": "задолбал {target}"},
        "female": {"male": "задолбала {target}", "female": "задолбала {target}"},
        "emoji": "💢"
    },
    "крутой": {
        "male": {"male": "назвал {target} крутым", "female": "назвал {target} крутой"},
        "female": {"male": "назвала {target} крутым", "female": "назвала {target} крутой"},
        "emoji": "🔥"
    },
    "отъебись": {
        "male": {"male": "отъебался от {target}", "female": "отъебался от {target}"},
        "female": {"male": "отъебалась от {target}", "female": "отъебалась от {target}"},
        "emoji": "✋"
    },
    "милый": {
        "male": {"male": "назвал {target} милым", "female": "назвал {target} милой"},
        "female": {"male": "назвала {target} милым", "female": "назвала {target} милой"},
        "emoji": "🥰"
    },
    "завали": {
        "male": {"male": "сказал {target} завалить", "female": "сказал {target} завалить"},
        "female": {"male": "сказала {target} завалить", "female": "сказала {target} завалить"},
        "emoji": "💀"
    },
    "соскучился": {
        "male": {"male": "соскучился по {target}", "female": "соскучился по {target}"},
        "female": {"male": "соскучилась по {target}", "female": "соскучилась по {target}"},
        "emoji": "😢"
    },
    "в рот": {
        "male": {"male": "послал в рот {target}", "female": "послал в рот {target}"},
        "female": {"male": "послала в рот {target}", "female": "послала в рот {target}"},
        "emoji": "👄"
    },
    "хочу": {
        "male": {"male": "хочет обнять {target}", "female": "хочет обнять {target}"},
        "female": {"male": "хочет обнять {target}", "female": "хочет обнять {target}"},
        "emoji": "🤲"
    },
    "оставь": {
        "male": {"male": "просит оставить его", "female": "просит оставить его"},
        "female": {"male": "просит оставить её", "female": "просит оставить её"},
        "emoji": "🚪"
    },
    "особенный": {
        "male": {"male": "назвал {target} особенным", "female": "назвал {target} особенной"},
        "female": {"male": "назвала {target} особенным", "female": "назвала {target} особенной"},
        "emoji": "💎"
    },
    "не беси": {
        "male": {"male": "просит {target} не бесить его", "female": "просит {target} не бесить его"},
        "female": {"male": "просит {target} не бесить её", "female": "просит {target} не бесить её"},
        "emoji": "😇"
    },
    "опора": {
        "male": {"male": "сказал, что {target} его опора", "female": "сказал, что {target} его опора"},
        "female": {"male": "сказала, что {target} её опора", "female": "сказала, что {target} её опора"},
        "emoji": "🏔️"
    },
    "хватит": {
        "male": {"male": "сказал {target} хватит", "female": "сказал {target} хватит"},
        "female": {"male": "сказала {target} хватит", "female": "сказала {target} хватит"},
        "emoji": "⛔"
    },
    "не могу": {
        "male": {"male": "не может без {target}", "female": "не может без {target}"},
        "female": {"male": "не может без {target}", "female": "не может без {target}"},
        "emoji": "💔"
    },
    "подожди": {
        "male": {"male": "просит {target} подождать", "female": "просит {target} подождать"},
        "female": {"male": "просит {target} подождать", "female": "просит {target} подождать"},
        "emoji": "⏳"
    },
    "вернись": {
        "male": {"male": "просит {target} вернуться", "female": "просит {target} вернуться"},
        "female": {"male": "просит {target} вернуться", "female": "просит {target} вернуться"},
        "emoji": "🔄"
    },
    "отстань": {
        "male": {"male": "просит {target} отстать", "female": "просит {target} отстать"},
        "female": {"male": "просит {target} отстать", "female": "просит {target} отстать"},
        "emoji": "🙅"
    },
    "помню": {
        "male": {"male": "помнит тот день с {target}", "female": "помнит тот день с {target}"},
        "female": {"male": "помнит тот день с {target}", "female": "помнит тот день с {target}"},
        "emoji": "📅"
    },
    "слушай": {
        "male": {"male": "сказал {target} слушать", "female": "сказал {target} слушать"},
        "female": {"male": "сказала {target} слушать", "female": "сказала {target} слушать"},
        "emoji": "👂"
    },
    "с тобой": {
        "male": {"male": "с {target}", "female": "с {target}"},
        "female": {"male": "с {target}", "female": "с {target}"},
        "emoji": "🤝"
    },
    "не заставляй": {
        "male": {"male": "просит {target} не заставлять его", "female": "просит {target} не заставлять его"},
        "female": {"male": "просит {target} не заставлять её", "female": "просит {target} не заставлять её"},
        "emoji": "🙏"
    },
    "офигенный": {
        "male": {"male": "назвал {target} офигенным", "female": "назвал {target} офигенной"},
        "female": {"male": "назвала {target} офигенным", "female": "назвала {target} офигенной"},
        "emoji": "🤩"
    },
    "устал": {
        "male": {"male": "устал от {target}", "female": "устал от {target}"},
        "female": {"male": "устала от {target}", "female": "устала от {target}"},
        "emoji": "😴"
    },
    "смех": {
        "male": {"male": "любит смех {target}", "female": "любит смех {target}"},
        "female": {"male": "любит смех {target}", "female": "любит смех {target}"},
        "emoji": "😂"
    },
    "не ори": {
        "male": {"male": "просит {target} не орать", "female": "просит {target} не орать"},
        "female": {"male": "просит {target} не орать", "female": "просит {target} не орать"},
        "emoji": "🔇"
    },
    "уважаю": {
        "male": {"male": "уважает {target}", "female": "уважает {target}"},
        "female": {"male": "уважает {target}", "female": "уважает {target}"},
        "emoji": "🤝"
    },
    "угомонись": {
        "male": {"male": "просит {target} угомониться", "female": "просит {target} угомониться"},
        "female": {"male": "просит {target} угомониться", "female": "просит {target} угомониться"},
        "emoji": "😌"
    },
    "голос": {
        "male": {"male": "голос {target} успокаивает", "female": "голос {target} успокаивает"},
        "female": {"male": "голос {target} успокаивает", "female": "голос {target} успокаивает"},
        "emoji": "🎵"
    },
    "зачем": {
        "male": {"male": "спросил {target}, зачем он это сделал", "female": "спросил {target}, зачем он это сделал"},
        "female": {"male": "спросила {target}, зачем он это сделал", "female": "спросила {target}, зачем он это сделал"},
        "emoji": "🤔"
    },
    "горжусь": {
        "male": {"male": "гордится {target}", "female": "гордится {target}"},
        "female": {"male": "гордится {target}", "female": "гордится {target}"},
        "emoji": "🏆"
    },
    "дай время": {
        "male": {"male": "просит {target} дать время", "female": "просит {target} дать время"},
        "female": {"male": "просит {target} дать время", "female": "просит {target} дать время"},
        "emoji": "⏰"
    },
    "прощу": {
        "male": {"male": "всё простит {target}", "female": "всё простит {target}"},
        "female": {"male": "всё простит {target}", "female": "всё простит {target}"},
        "emoji": "🕊️"
    },
    "завязывай": {
        "male": {"male": "сказал {target} завязывать", "female": "сказал {target} завязывать"},
        "female": {"male": "сказала {target} завязывать", "female": "сказала {target} завязывать"},
        "emoji": "✂️"
    },
    "прав": {
        "male": {"male": "сказал, что {target} всегда прав", "female": "сказал, что {target} всегда права"},
        "female": {"male": "сказала, что {target} всегда прав", "female": "сказала, что {target} всегда права"},
        "emoji": "✅"
    },
    "не лезь": {
        "male": {"male": "просит {target} не лезть", "female": "просит {target} не лезть"},
        "female": {"male": "просит {target} не лезть", "female": "просит {target} не лезть"},
        "emoji": "🚧"
    },
    "доверяю": {
        "male": {"male": "доверяет {target}", "female": "доверяет {target}"},
        "female": {"male": "доверяет {target}", "female": "доверяет {target}"},
        "emoji": "🤝"
    },
    "не могу так": {
        "male": {"male": "больше не может так с {target}", "female": "больше не может так с {target}"},
        "female": {"male": "больше не может так с {target}", "female": "больше не может так с {target}"},
        "emoji": "💔"
