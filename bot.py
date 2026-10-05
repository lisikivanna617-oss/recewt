import asyncio
import datetime
import logging
import os
import random
import re
import string
import sys
import threading
from typing import Optional

import aiohttp
import aiosqlite
from dotenv import load_dotenv
from flask import Flask

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# Завантаження змінних оточення
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TESTER_ID = int(os.getenv("TESTER_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "database.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("TagPulse")

# --- Flask Keep-Alive Server для Render ---
app = Flask(__name__)

@app.route("/")
def home():
    return "TagPulse Bot is alive and running!"

def run_web():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- FSM States ---
class Form(StatesGroup):
    waiting_for_smart_input = State()
    waiting_for_pattern = State()
    waiting_for_custom_filter = State()
    waiting_for_snipe_username = State()
    waiting_for_admin_give_perm = State()
    waiting_for_admin_tag = State()

# --- Database Initialization ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                plan TEXT DEFAULT 'FREE',
                premium_until TIMESTAMP,
                referrals INTEGER DEFAULT 0,
                referred_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS saved_usernames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, username)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                status TEXT,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS snipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                status TEXT DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, username)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tag_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, tag_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bought_usernames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                user_id INTEGER,
                bought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_searches INTEGER DEFAULT 0,
                found_usernames INTEGER DEFAULT 0
            )
        """)
        # Ініціалізація лічильника статистики
        async with db.execute("SELECT COUNT(*) FROM stats") as cursor:
            count = (await cursor.fetchone())[0]
            if count == 0:
                await db.execute("INSERT INTO stats (total_searches, found_usernames) VALUES (0, 0)")
        
        await db.commit()

# --- Logic & Helper Functions ---

async def register_user(user_id: int, username: Optional[str], referrer_id: Optional[int] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                ref_id = referrer_id if referrer_id and referrer_id != user_id else None
                await db.execute(
                    "INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                    (user_id, username, ref_id)
                )
                if ref_id:
                    await db.execute(
                        "UPDATE users SET referrals = referrals + 1 WHERE user_id = ?",
                        (ref_id,)
                    )
                    # Нагорода за 3 рефералів — Premium на 7 днів
                    async with db.execute("SELECT referrals FROM users WHERE user_id = ?", (ref_id,)) as ref_cur:
                        refs = (await ref_cur.fetchone())[0]
                        if refs >= 3:
                            until = datetime.datetime.now() + datetime.timedelta(days=7)
                            await db.execute(
                                "UPDATE users SET plan = 'PREMIUM', premium_until = ? WHERE user_id = ?",
                                (until, ref_id)
                            )
                await db.commit()

async def get_user_plan(user_id: int) -> str:
    if user_id in (ADMIN_ID, TESTER_ID):
        return "PREMIUM_PLUS"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT plan, premium_until FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return "FREE"
            plan, until_str = row[0], row[1]
            if until_str:
                until = datetime.datetime.fromisoformat(until_str)
                if datetime.datetime.now() > until:
                    await db.execute("UPDATE users SET plan = 'FREE', premium_until = NULL WHERE user_id = ?", (user_id,))
                    await db.commit()
                    return "FREE"
            return plan

def calculate_username_score(username: str) -> dict:
    clean = username.lstrip("@").lower()
    length = len(clean)
    score = 0
    
    # Довжина
    if length == 5:
        score += 40
    elif length == 6:
        score += 30
    elif length == 7:
        score += 20
    elif length == 8:
        score += 10
    else:
        score += 5
        
    # Цифри
    has_digits = any(c.isdigit() for c in clean)
    if not has_digits:
        score += 25
        
    # Underscores
    has_underscore = "_" in clean
    if not has_underscore:
        score += 20
        
    # Паліндром (симетрія)
    is_palindrome = clean == clean[::-1]
    if is_palindrome:
        score += 15
        
    score = min(score, 100)
    
    if score >= 85:
        rarity = "🔥 Very Rare"
    elif score >= 65:
        rarity = "💎 Rare"
    elif score >= 45:
        rarity = "✨ Medium"
    else:
        rarity = "⚙️ Common"
        
    return {
        "score": score,
        "length": length,
        "has_digits": "No" if not has_digits else "Yes",
        "has_underscore": "No" if not has_underscore else "Yes",
        "rarity": rarity
    }

async def check_telegram_username(username: str) -> bool:
    """
    Перевіряє доступність username через публічний HTTP запит t.me.
    Повертає True, якщо username ВІЛЬНИЙ, і False, якщо ЗАЙНЯТИЙ.
    """
    clean = username.lstrip("@")
    url = f"https://t.me/{clean}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                text = await resp.text()
                # Якщо є елементи каналу/профілю або метатеги, юзернейм зайнятий
                if 'tgme_page_title' in text or 'extra_bold' in text:
                    return False
                return True
    except Exception as e:
        logger.error(f"Error checking username {username}: {e}")
        return False

# --- Keyboards ---

def get_main_keyboard(user_id: int):
    buttons = [
        [InlineKeyboardButton(text="🔎 Search Usernames", callback_data="menu_search")],
        [InlineKeyboardButton(text="⭐ Saved", callback_data="menu_saved"), InlineKeyboardButton(text="📜 History", callback_data="menu_history")],
        [InlineKeyboardButton(text="🎯 My Snipes", callback_data="menu_snipes"), InlineKeyboardButton(text="🏷 My Tags", callback_data="menu_tags")],
        [InlineKeyboardButton(text="💎 Premium & Ref", callback_data="menu_premium")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")])
    if user_id in (ADMIN_ID, TESTER_ID):
        buttons.append([InlineKeyboardButton(text="🧪 Test Panel", callback_data="tester_panel")])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_search_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Random Length (5-12)", callback_data="search_random")],
        [InlineKeyboardButton(text="💡 Smart Generator", callback_data="search_smart")],
        [InlineKeyboardButton(text="🧩 Pattern Search", callback_data="search_pattern")],
        [InlineKeyboardButton(text="⚙️ Custom Filters", callback_data="search_custom")],
        [InlineKeyboardButton(text="💎 Rare Collector Mode", callback_data="search_rare")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Main Menu", callback_data="main_menu")]
    ])

# --- Handlers ---

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    await register_user(message.from_user.id, message.from_user.username, ref_id)
    
    await message.answer(
        "<b>Welcome to TagPulse Bot!</b>\n"
        "Advanced Telegram Username Hunter, Generator & Sniper.\n\n"
        "Select an action from the menu below:",
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "<b>Main Menu</b>\nChoose an option:",
        reply_markup=get_main_keyboard(callback.from_user.id),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Search Section ---

@dp.callback_query(F.data == "menu_search")
async def cb_menu_search(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>🔎 Username Search & Generation</b>\nSelect search mode:",
        reply_markup=get_search_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "search_random")
async def cb_search_random(callback: CallbackQuery):
    plan = await get_user_plan(callback.from_user.id)
    count = 1 if plan == "FREE" else (3 if plan == "PREMIUM" else 5)
    
    found_list = []
    chars = string.ascii_lowercase + string.digits
    
    async with aiosqlite.connect(DB_PATH) as db:
        while len(found_list) < count:
            length = random.randint(5, 12)
            candidate = "".join(random.choices(chars, k=length))
            
            # Перевірка в локальній БД куплених
            async with db.execute("SELECT id FROM bought_usernames WHERE username = ?", (candidate,)) as cur:
                if await cur.fetchone():
                    continue
                    
            is_free = await check_telegram_username(candidate)
            status = "FREE" if is_free else "TAKEN"
            
            # Запис в історію
            await db.execute(
                "INSERT INTO search_history (user_id, username, status) VALUES (?, ?, ?)",
                (callback.from_user.id, candidate, status)
            )
            await db.execute("UPDATE stats SET total_searches = total_searches + 1 WHERE id = 1")
            
            if is_free:
                found_list.append(candidate)
                await db.execute("UPDATE stats SET found_usernames = found_usernames + 1 WHERE id = 1")
        
        await db.commit()

    text = f"<b>🔎 Random Search Results ({plan} Plan):</b>\n\n"
    for tag in found_list:
        score_info = calculate_username_score(tag)
        text += (
            f"• <code>@{tag}</code>\n"
            f"  └ Score: <b>{score_info['score']}/100</b> ({score_info['rarity']})\n"
        )
        
    await callback.message.edit_text(
        text,
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "search_smart")
async def cb_search_smart(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_smart_input)
    await callback.message.edit_text(
        "<b>💡 Smart Generator</b>\n\nEnter base keyword (e.g., <code>neo</code>):",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(Form.waiting_for_smart_input)
async def process_smart_input(message: Message, state: FSMContext):
    base = message.text.strip().lower()
    plan = await get_user_plan(message.from_user.id)
    count = 1 if plan == "FREE" else (3 if plan == "PREMIUM" else 5)
    
    variations = [
        f"{base}1", f"{base}_x", f"{base}x", f"{base}7", f"{base}_bot",
        f"the_{base}", f"{base}_official", f"real_{base}", f"{base}2026"
    ]
    random.shuffle(variations)
    
    found = []
    async with aiosqlite.connect(DB_PATH) as db:
        for candidate in variations:
            if len(found) >= count:
                break
            is_free = await check_telegram_username(candidate)
            status = "FREE" if is_free else "TAKEN"
            await db.execute(
                "INSERT INTO search_history (user_id, username, status) VALUES (?, ?, ?)",
                (message.from_user.id, candidate, status)
            )
            if is_free:
                found.append(candidate)
        await db.commit()

    await state.clear()
    
    if not found:
        await message.answer("No free variants found for this keyword.", reply_markup=get_back_keyboard())
        return

    text = f"<b>💡 Smart Generated Usernames ({plan}):</b>\n\n"
    for tag in found:
        score_info = calculate_username_score(tag)
        text += f"• <code>@{tag}</code> | Score: {score_info['score']}/100 ({score_info['rarity']})\n"

    await message.answer(text, reply_markup=get_back_keyboard(), parse_mode="HTML")

# --- Saved Usernames & History ---

@dp.callback_query(F.data == "menu_saved")
async def cb_menu_saved(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT username FROM saved_usernames WHERE user_id = ?", (callback.from_user.id,)) as cur:
            rows = await cur.fetchall()

    if not rows:
        await callback.message.edit_text("<b>⭐ Saved Usernames:</b>\nList is empty.", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return

    text = "<b>⭐ Saved Usernames:</b>\n\n"
    for r in rows:
        text += f"• <code>@{r[0]}</code>\n"

    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "menu_history")
async def cb_menu_history(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, status, searched_at FROM search_history WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (callback.from_user.id,)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await callback.message.edit_text("<b>📜 Search History:</b>\nNo recent searches.", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return

    text = "<b>📜 Search History (Last 10):</b>\n\n"
    for r in rows:
        icon = "✅" if r[1] == "FREE" else "❌"
        text += f"{icon} <code>@{r[0]}</code> ({r[1]})\n"

    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- Sniper System ---

@dp.callback_query(F.data == "menu_snipes")
async def cb_menu_snipes(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT username, status FROM snipes WHERE user_id = ?", (callback.from_user.id,)) as cur:
            rows = await cur.fetchall()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Add New Snipe", callback_data="snipe_add")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
    ])

    if not rows:
        await callback.message.edit_text("<b>🎯 Active Snipes:</b>\nYou have no active snipes.", reply_markup=kb, parse_mode="HTML")
        return

    text = "<b>🎯 Your Target Snipes:</b>\n\n"
    for r in rows:
        text += f"• <code>@{r[0]}</code> - Status: <b>{r[1]}</b>\n"

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "snipe_add")
async def cb_snipe_add(callback: CallbackQuery, state: FSMContext):
    plan = await get_user_plan(callback.from_user.id)
    max_snipes = 1 if plan == "FREE" else (5 if plan == "PREMIUM" else 15)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM snipes WHERE user_id = ?", (callback.from_user.id,)) as cur:
            current_count = (await cur.fetchone())[0]

    if current_count >= max_snipes:
        await callback.answer(f"Limit reached! Your plan allows max {max_snipes} active snipes.", show_alert=True)
        return

    await state.set_state(Form.waiting_for_snipe_username)
    await callback.message.edit_text("<b>🎯 Add Snipe</b>\nEnter target username:", reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(Form.waiting_for_snipe_username)
async def process_snipe_username(message: Message, state: FSMContext):
    target = message.text.strip().lstrip("@").lower()
    
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO snipes (user_id, username) VALUES (?, ?)", (message.from_user.id, target))
            await db.commit()
            await message.answer(f"🎯 Target <code>@{target}</code> added to sniper!", reply_markup=get_back_keyboard(), parse_mode="HTML")
        except aiosqlite.IntegrityError:
            await message.answer("This target is already in your snipe list.", reply_markup=get_back_keyboard())

    await state.clear()

async def sniper_background_worker():
    """Фоновий процес для періодичної перевірки зайнятих юзернеймів."""
    while True:
        try:
            await asyncio.sleep(60) # Перевірка кожну хвилину
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT id, user_id, username FROM snipes WHERE status = 'ACTIVE'") as cur:
                    snipes = await cur.fetchall()

                for snipe_id, user_id, tag in snipes:
                    is_free = await check_telegram_username(tag)
                    if is_free:
                               if is_free:
                        # Сповіщаємо користувача
                        try:
                            await bot.send_message(
                                user_id,
                                f"🔥 <b>SNIPER ALERT!</b>\n\nUsername <code>@{tag}</code> is now AVAILABLE!",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Failed to send alert to {user_id}: {e}")
                            
                        await db.execute("UPDATE snipes SET status = 'FOUND' WHERE id = ?", (snipe_id,))
                        await db.commit()
        except Exception as e:
            logger.error(f"Error in sniper worker: {e}")
# --- Admin & Tester Panels ---

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Access Denied: Admin only!", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT total_searches, found_usernames FROM stats WHERE id = 1") as cur:
            st = await cur.fetchone()
            searches, found = (st[0], st[1]) if st else (0, 0)

    text = (
        "<b>⚙️ Admin Panel</b>\n\n"
        f"• Total Users: <code>{total_users}</code>\n"
        f"• Total Searches: <code>{searches}</code>\n"
        f"• Found Tags: <code>{found}</code>\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Give Premium", callback_data="admin_give_prem")],
        [InlineKeyboardButton(text="🗑 Clear DB", callback_data="admin_clear_db")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_give_prem")
async def cb_admin_give_prem(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(Form.waiting_for_admin_give_perm)
    await callback.message.edit_text("Enter User ID to give Premium:", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.message(Form.waiting_for_admin_give_perm)
async def process_admin_give_prem(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.strip())
        until = datetime.datetime.now() + datetime.timedelta(days=30)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET plan = 'PREMIUM', premium_until = ? WHERE user_id = ?", (until, target_id))
            await db.commit()
        await message.answer(f"Granted 30 days Premium to user {target_id}!")
    except ValueError:
        await message.answer("Invalid User ID.")
    await state.clear()

@dp.callback_query(F.data == "tester_panel")
async def cb_tester_panel(callback: CallbackQuery):
    if callback.from_user.id not in (ADMIN_ID, TESTER_ID):
        await callback.answer("Access Denied: Testers only!", show_alert=True)
        return

    text = "<b>🧪 Tester Panel</b>\nChoose a test function:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Test Notification", callback_data="test_notify")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "test_notify")
async def cb_test_notify(callback: CallbackQuery):
    await callback.answer("Test Notification Triggered!", show_alert=True)# --- Admin & Tester Panels ---

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Access Denied: Admin only!", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT total_searches, found_usernames FROM stats WHERE id = 1") as cur:
            st = await cur.fetchone()
            searches, found = (st[0], st[1]) if st else (0, 0)

    text = (
        "<b>⚙️ Admin Panel</b>\n\n"
        f"• Total Users: <code>{total_users}</code>\n"
        f"• Total Searches: <code>{searches}</code>\n"
        f"• Found Tags: <code>{found}</code>\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Give Premium", callback_data="admin_give_prem")],
        [InlineKeyboardButton(text="🗑 Clear DB", callback_data="admin_clear_db")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_give_prem")
async def cb_admin_give_prem(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(Form.waiting_for_admin_give_perm)
    await callback.message.edit_text("Enter User ID to give Premium:", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.message(Form.waiting_for_admin_give_perm)
async def process_admin_give_prem(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text.strip())
        until = datetime.datetime.now() + datetime.timedelta(days=30)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET plan = 'PREMIUM', premium_until = ? WHERE user_id = ?", (until, target_id))
            await db.commit()
        await message.answer(f"Granted 30 days Premium to user {target_id}!")
    except ValueError:
        await message.answer("Invalid User ID.")
    await state.clear()

@dp.callback_query(F.data == "tester_panel")
async def cb_tester_panel(callback: CallbackQuery):
    if callback.from_user.id not in (ADMIN_ID, TESTER_ID):
        await callback.answer("Access Denied: Testers only!", show_alert=True)
        return

    text = "<b>🧪 Tester Panel</b>\nChoose a test function:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Test Notification", callback_data="test_notify")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "test_notify")
async def cb_test_notify(callback: CallbackQuery):
    await callback.answer("Test Notification Triggered!", show_alert=True)
# --- Entry Point ---

async def main():
    await init_db()
    
    # Запуск фонового снайпера
    asyncio.create_task(sniper_background_worker())
    
    logger.info("TagPulse Bot initialized and starting polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    # Запуск Flask-сервера у фоновому потоці для Render Health Checks
    threading.Thread(target=run_web, daemon=True).start()
    
    asyncio.run(main())

