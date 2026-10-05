import sys
import os
import logging
import asyncio
import datetime
import threading
import aiosqlite
import requests
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))
TESTER_ID = int(os.environ.get("TESTER_ID", "123456789"))
DB_PATH = "bot_database.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Web Server for Health Checks ---
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- FSM States ---
class Form(StatesGroup):
    waiting_for_tag_search = State()
    waiting_for_snipe_tag = State()
    waiting_for_admin_give_perm = State()

# --- Database Setup ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                plan TEXT DEFAULT 'FREE',
                premium_until DATETIME,
                referrals INTEGER DEFAULT 0,
                referred_by INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                tag_name TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS snipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                status TEXT DEFAULT 'ACTIVE'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY,
                total_searches INTEGER DEFAULT 0,
                found_usernames INTEGER DEFAULT 0
            )
        """)
        await db.execute("INSERT OR IGNORE INTO stats (id, total_searches, found_usernames) VALUES (1, 0, 0)")
        await db.commit()
# --- Helper Functions ---
async def check_telegram_username(username: str) -> bool:
    username = username.lstrip("@").strip()
    url = f"https://t.me/{username}"
    try:
        resp = await asyncio.to_thread(requests.get, url, timeout=5)
        if resp.status_code == 200:
            if "If you have Telegram, you can contact" in resp.text or "Preview channel" in resp.text:
                return False
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking username {username}: {e}")
        return False

async def get_user_plan(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT plan, premium_until FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return "FREE"
            plan, until = row[0], row[1]
            if plan == "PREMIUM" and until:
                until_dt = datetime.datetime.fromisoformat(until)
                if datetime.datetime.now() > until_dt:
                    await db.execute("UPDATE users SET plan = 'FREE' WHERE user_id = ?", (user_id,))
                    await db.commit()
                    return "FREE"
            return plan

def get_main_keyboard(user_id: int, plan: str):
    buttons = [
        [InlineKeyboardButton(text="🔍 Search Username", callback_data="menu_search")],
        [InlineKeyboardButton(text="🎯 Username Sniper", callback_data="menu_sniper")],
        [InlineKeyboardButton(text="🏷 My Tags", callback_data="menu_tags")],
        [InlineKeyboardButton(text="⭐ Premium & Referrals", callback_data="menu_premium")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")])
    if user_id in (ADMIN_ID, TESTER_ID):
        buttons.append([InlineKeyboardButton(text="🧪 Tester Panel", callback_data="tester_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="main_menu")]
    ])
# --- Handlers: Start & Main Menu ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            exists = await cur.fetchone()

        if not exists:
            await db.execute(
                "INSERT INTO users (user_id, referred_by) VALUES (?, ?)",
                (user_id, referrer_id if referrer_id != user_id else None)
            )
            if referrer_id and referrer_id != user_id:
                await db.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (referrer_id,))
                async with db.execute("SELECT referrals FROM users WHERE user_id = ?", (referrer_id,)) as cur:
                    row = await cur.fetchone()
                    if row and row[0] >= 3:
                        until = datetime.datetime.now() + datetime.timedelta(days=7)
                        await db.execute("UPDATE users SET plan = 'PREMIUM', premium_until = ? WHERE user_id = ?", (until, referrer_id))
            await db.commit()

    plan = await get_user_plan(user_id)
    text = (
        f"👋 <b>Welcome to TagPulse Bot!</b>\n\n"
        f"• Your Plan: <b>{plan}</b>\n"
        f"Select an option from the menu below:"
    )
    await message.answer(text, reply_markup=get_main_keyboard(user_id, plan), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    plan = await get_user_plan(callback.from_user.id)
    text = (
        f"👋 <b>TagPulse Main Menu</b>\n\n"
        f"• Your Plan: <b>{plan}</b>\n"
        f"Select an option from the menu below:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(callback.from_user.id, plan), parse_mode="HTML")
    await callback.answer()
# --- Handlers: Search & Sniper ---

@dp.callback_query(F.data == "menu_search")
async def cb_menu_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_tag_search)
    await callback.message.edit_text(
        "🔍 Send me the username/tag you want to check (e.g. <code>@tag</code> or <code>tag</code>):",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(Form.waiting_for_tag_search)
async def process_tag_search(message: Message, state: FSMContext):
    tag = message.text.strip().lstrip("@")
    await message.answer(f"🔎 Checking status for <code>@{tag}</code>...", parse_mode="HTML")

    is_free = await check_telegram_username(tag)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE stats SET total_searches = total_searches + 1 WHERE id = 1")
        if is_free:
            await db.execute("UPDATE stats SET found_usernames = found_usernames + 1 WHERE id = 1")
            await db.execute("INSERT INTO user_tags (user_id, tag_name) VALUES (?, ?)", (message.from_user.id, tag))
        await db.commit()

    if is_free:
        res = f"✅ <b>Username @{tag} is AVAILABLE!</b>"
    else:
        res = f"❌ <b>Username @{tag} is TAKEN or UNAVAILABLE.</b>"

    await message.answer(res, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "menu_sniper")
async def cb_menu_sniper(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_snipe_tag)
    await callback.message.edit_text(
        "🎯 <b>Username Sniper</b>\n\nSend me the username you want to monitor:",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(Form.waiting_for_snipe_tag)
async def process_snipe_tag(message: Message, state: FSMContext):
    tag = message.text.strip().lstrip("@")
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO snipes (user_id, username, status) VALUES (?, ?, 'ACTIVE')", (message.from_user.id, tag))
        await db.commit()

    await message.answer(
        f"🎯 Added <code>@{tag}</code> to Sniper queue! We will notify you as soon as it becomes available.",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()

# --- Background Worker for Sniper ---
async def sniper_background_worker():
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT id, user_id, username FROM snipes WHERE status = 'ACTIVE'") as cur:
                    snipes = await cur.fetchall()

                for snipe_id, user_id, tag in snipes:
                    is_free = await check_telegram_username(tag)
                    if is_free:
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

        await asyncio.sleep(60)
# --- User Tags & Premium ---

@dp.callback_query(F.data == "menu_tags")
async def cb_menu_tags(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tag_name FROM user_tags WHERE user_id = ?", (callback.from_user.id,)) as cur:
            tags = await cur.fetchall()

    if not tags:
        await callback.message.edit_text("<b>🏷 My Tags:</b>\nYou have no assigned tags.", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return

    text = "<b>🏷 Your Tags:</b>\n\n"
    for t in tags:
        text += f"• <code>#{t[0]}</code>\n"

    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "menu_premium")
async def cb_menu_premium(callback: CallbackQuery):
    plan = await get_user_plan(callback.from_user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT referrals FROM users WHERE user_id = ?", (callback.from_user.id,)) as cur:
            row = await cur.fetchone()
            refs = row[0] if row else 0

    text = (
        f"<b>💎 Premium & Referral System</b>\n\n"
        f"• Your Plan: <b>{plan}</b>\n"
        f"• Total Referrals: <b>{refs}</b>\n\n"
        f"<b>Invite 3 friends to get FREE 7-Days Premium!</b>\n"
        f"Your Referral Link:\n<code>{ref_link}</code>"
    )

    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

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
        [InlineKeyboardButton(text="⬅️️ Back", callback_data="main_menu")]
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
        
    # Запуск Flask-сервера у фоновому потоці для Render
    threading.Thread(target=run_web, daemon=True).start()
    
    asyncio.run(main())
