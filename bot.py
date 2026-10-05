import asyncio
import datetime
import logging
import os
import random
import sqlite3
import string
import sys
import threading
from flask import Flask

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# --- Flask Keep-Alive Server for Render ---
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- Environment Configuration ---
TOKEN = os.getenv("BOT_TOKEN")

OWNER_ID = 5619415334
TESTER_ID = 8644168067

bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# --- Database Initialization ---
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Table for bought usernames
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bought_usernames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            user_id INTEGER,
            bought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table for user stats / premium status
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_premium INTEGER DEFAULT 0,
            referrals INTEGER DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()

# --- Username Search Logic ---
def search_users(user_id, count=5):
    # Fetch already purchased usernames from the database
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM bought_usernames")
    bought = {row[0].lower() for row in cursor.fetchall()}
    conn.close()

    found = []
    chars = string.ascii_lowercase + string.digits

    while len(found) < count:
        # Generate base text and trim 4 characters from the end
        base = "".join(random.choices(chars, k=7))
        trimmed_base = base[:-4]
        candidate = f"{trimmed_base}_tag"

        # Check if the candidate is not bought and not already in the list
        if candidate.lower() not in bought and candidate not in found:
            found.append(candidate)

    return found

# --- Keyboards ---
def get_main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Search Tags", callback_data="search_tags")],
            [InlineKeyboardButton(text="⭐ Premium", callback_data="premium_info")]
        ]
    )

def get_back_keyboard(user_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
        ]
    )

# --- Bot Handlers ---
@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "<b>Welcome to TagPulse Bot!</b>\n\nChoose an option below:",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Welcome to TagPulse Bot!</b>\n\nChoose an option below:",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "search_tags")
async def search_tags_handler(callback: CallbackQuery):
    tags = search_users(callback.from_user.id)
    tags_text = "\n".join([f"• <code>@{tag}</code>" for tag in tags])
    
    text = f"<b>Generated Available Tags:</b>\n\n{tags_text}"
    await callback.message.edit_text(
        text,
        reply_markup=get_back_keyboard(callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Main Entry Point ---
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("TagPulse Bot is online and updated!")[span_1](start_span)[span_1](end_span)
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )
    
    # Start web server thread for Render HTTP Health Check
    threading.Thread(target=run_web, daemon=True).start()
    
    asyncio.run(main())
