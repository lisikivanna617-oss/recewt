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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bought_usernames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            user_id INTEGER,
            bought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
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
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM bought_usernames")
    bought = {row[0].lower() for row in cursor.fetchall()}
    conn.close()

    found = []
    chars = string.ascii_lowercase + string.digits

    while len(found) < count:
        # Генерация юзернеймов случайной длины от 5 до 12 символов
        length = random.randint(5, 12)
        base = "".join(random.choices(chars, k=length))
        candidate = base

        if candidate.lower() not in bought and candidate not in found:
            found.append(candidate)

    return found

# --- Keyboards ---
def get_main_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton(text="🔍 Search Tags", callback_data="search_tags")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium_info")]
    ]
    # Добавляем кнопку админки только для владельца и тестера
    if user_id in (OWNER_ID, TESTER_ID):
        buttons.append([InlineKeyboardButton(text="🛠 Admin Panel", callback_data="admin_panel")])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📜 Bought Tags", callback_data="admin_bought_list")],
            [InlineKeyboardButton(text="🧪 Test Add Bought Tag", callback_data="admin_test_add")],
            [InlineKeyboardButton(text="🗑 Clear Database", callback_data="admin_clear_db")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
        ]
    )

def get_back_keyboard():
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
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Welcome to TagPulse Bot!</b>\n\nChoose an option below:",
        reply_markup=get_main_keyboard(callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "search_tags")
async def search_tags_handler(callback: CallbackQuery):
    tags = search_users(callback.from_user.id)
    tags_text = "\n".join([f"• <code>@{tag}</code>" for tag in tags])
    
    text = f"<b>Generated Available Tags (5-12 chars):</b>\n\n{tags_text}"
    await callback.message.edit_text(
        text,
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Admin / Tester Handlers ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery):
    if callback.from_user.id not in (OWNER_ID, TESTER_ID):
        await callback.answer("Access denied!", show_alert=True)
        return

    await callback.message.edit_text(
        "<b>🛠 Admin / Tester Panel</b>\n\nSelect a developer tool:",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: CallbackQuery):
    if callback.from_user.id not in (OWNER_ID, TESTER_ID):
        return

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bought_usernames")
    bought_count = cursor.fetchone()[0]
    conn.close()

    text = (
        "<b>📊 System Statistics</b>\n\n"
        f"• Total Purchased Tags: <code>{bought_count}</code>\n"
        f"• Owner ID: <code>{OWNER_ID}</code>\n"
        f"• Tester ID: <code>{TESTER_ID}</code>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="admin_panel")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_bought_list")
async def admin_bought_list_handler(callback: CallbackQuery):
    if callback.from_user.id not in (OWNER_ID, TESTER_ID):
        return

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM bought_usernames LIMIT 20")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        text = "<b>📜 Bought Tags:</b>\n\nNo purchased tags found."
    else:
        tags_list = "\n".join([f"• <code>@{r[0]}</code>" for r in rows])
        text = f"<b>📜 Last Purchased Tags:</b>\n\n{tags_list}"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="admin_panel")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_test_add")
async def admin_test_add_handler(callback: CallbackQuery):
    if callback.from_user.id not in (OWNER_ID, TESTER_ID):
        return

    test_tag = "test_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO bought_usernames (username, user_id) VALUES (?, ?)", (test_tag, callback.from_user.id))
    conn.commit()
    conn.close()

    await callback.answer(f"Added test tag: @{test_tag}", show_alert=True)

@dp.callback_query(F.data == "admin_clear_db")
async def admin_clear_db_handler(callback: CallbackQuery):
    if callback.from_user.id not in (OWNER_ID, TESTER_ID):
        return

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bought_usernames")
    conn.commit()
    conn.close()

    await callback.answer("Database cleared successfully!", show_alert=True)

# --- Main Entry Point ---
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("TagPulse Bot is online and updated!")
    
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
