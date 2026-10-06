import sys
import os
import logging
import asyncio
import datetime
import threading
import random
import string
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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5619415334"))
TESTER_ID = int(os.environ.get("TESTER_ID", "8644168067"))
DB_PATH = "bot_database.db"

# --- Channel Configuration ---
CHANNEL_ID = "@otxen"
CHANNEL_URL = "https://t.me/otxen"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Web Server ---
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "TagPulse Bot is live!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# --- FSM States ---
class Form(StatesGroup):
    waiting_for_snipe_tag = State()
    waiting_for_admin_give_perm = State()
    waiting_for_ban_id = State()
    waiting_for_unban_id = State()
    waiting_for_broadcast = State()

# --- Database Setup ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                plan TEXT DEFAULT 'FREE',
                premium_until DATETIME,
                referrals INTEGER DEFAULT 0,
                referred_by INTEGER,
                is_banned INTEGER DEFAULT 0,
                daily_searches INTEGER DEFAULT 0,
                last_search_date TEXT
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
async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return bool(row[0]) if row and row[0] else False

async def check_telegram_username(username: str) -> bool:
    username = username.lstrip("@").strip()
    if len(username) < 5:
        return False

    try:
        await bot.get_chat(f"@{username}")
        return False
    except Exception as e:
        err_msg = str(e).lower()
        if "chat not found" not in err_msg and "user not found" not in err_msg:
            return False

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.get(
                f"https://t.me/{username}", 
                timeout=4, 
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
        )
        
        if response.status_code == 200:
            html = response.text
            
            is_taken_markers = [
                "tgme_page_title",
                "tgme_page_extra",
                "tgme_action_button_new",
                "fragment.com",
                "tgme_page_description",
                "tgme_icon_user"
            ]
            
            if any(marker in html for marker in is_taken_markers):
                return False

            if "If you have Telegram, you can contact" in html and "right away" in html:
                return True

        return False
    except Exception as e:
        logger.error(f"HTTP check error for @{username}: {e}")
        return False

def generate_username(length: int, include_numbers: bool) -> str:
    chars = string.ascii_lowercase
    if include_numbers:
        chars += string.digits
    first_char = random.choice(string.ascii_lowercase)
    rest_chars = ''.join(random.choice(chars) for _ in range(length - 1))
    return first_char + rest_chars

async def get_user_plan(user_id: int) -> str:
    if user_id == ADMIN_ID:
        return "PREMIUM (Owner)"

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

async def check_and_update_limits(user_id: int, plan: str) -> tuple[bool, int]:
    if "PREMIUM" in plan:
        return True, 999

    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT daily_searches, last_search_date FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            searches = row[0] if row and row[0] else 0
            last_date = row[1] if row else None

        if last_date != today:
            searches = 0
            await db.execute("UPDATE users SET daily_searches = 0, last_search_date = ? WHERE user_id = ?", (today, user_id))
            await db.commit()

        max_free_limit = 5
        if searches >= max_free_limit:
            return False, 0

        await db.execute("UPDATE users SET daily_searches = daily_searches + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
        return True, max_free_limit - (searches + 1)

def get_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join Our Channel", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ I Have Subscribed", callback_data="check_sub")]
    ])

def get_main_keyboard(user_id: int, plan: str):
    buttons = [
        [InlineKeyboardButton(text="⚡ Generate & Search Tags", callback_data="menu_search_gen")],
        [InlineKeyboardButton(text="🎯 Auto-Sniper 24/7", callback_data="menu_sniper")],
        [InlineKeyboardButton(text="🏷 My Saved Tags", callback_data="menu_tags")],
        [InlineKeyboardButton(text="⭐ Premium & Rewards", callback_data="menu_premium")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="⚙️️ Admin Panel", callback_data="admin_panel")])
    elif user_id == TESTER_ID:
        buttons.append([InlineKeyboardButton(text="🧪 Tester Panel", callback_data="tester_panel")])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Back to Menu", callback_data="main_menu")]
    ])

# --- Subscription Check Function ---
async def check_subscription(user_id: int) -> bool:
    if user_id in (ADMIN_ID, TESTER_ID):
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logger.error(f"Error checking subscription for {user_id}: {e}")
        return True

# --- Handlers: Start & Commands ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if await is_user_banned(user_id):
        await message.answer("❌ You are banned from using TagPulse.")
        return

    if not await check_subscription(user_id):
        text = (
            "⚠ <b>Access Restricted!</b>\n\n"
            "To use <b>TagPulse Bot</b>, please subscribe to our official channel where we publish all our projects and updates!"
        )
        await message.answer(text, reply_markup=get_sub_keyboard(), parse_mode="HTML")
        return

    args = message.text.split()
    referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            exists = await cur.fetchone()

        if not exists:
            await db.execute(
                "INSERT INTO users (user_id, referred_by, last_search_date) VALUES (?, ?, ?)",
                (user_id, referrer_id if referrer_id != user_id else None, datetime.date.today().isoformat())
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
        f"⚡ <b>Welcome to TagPulse Bot!</b>\n\n"
        f"Your ultimate tool for hunting rare Telegram usernames.\n\n"
        f"👤 <b>Plan Status:</b> <code>{plan}</code>\n"
        f"Choose an action from the menu below:"
    )
    await message.answer(text, reply_markup=get_main_keyboard(user_id, plan), parse_mode="HTML")

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        await callback.answer("✅ Thank you for subscribing!", show_alert=False)
        plan = await get_user_plan(user_id)
        text = (
            f"⚡ <b>TagPulse Main Menu</b>\n\n"
            f"👤 <b>Plan Status:</b> <code>{plan}</code>\n"
            f"Choose an option below:"
        )
        await callback.message.edit_text(text, reply_markup=get_main_keyboard(user_id, plan), parse_mode="HTML")
    else:
        await callback.answer("❌ You are still not subscribed to the channel!", show_alert=True)

@dp.message(Command("tags"))
async def cmd_tags(message: Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        return

    if not await check_subscription(user_id):
        await message.answer("⚠ Please subscribe to our channel first!", reply_markup=get_sub_keyboard(), parse_mode="HTML")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tag_name FROM user_tags WHERE user_id = ?", (user_id,)) as cur:
            tags = await cur.fetchall()

    if not tags:
        await message.answer("<b>🏷 Saved Tags:</b>\nYou haven't saved any available tags yet.", reply_markup=get_back_keyboard(), parse_mode="HTML")
        return

    text = "<b>🏷 Your Available Saved Tags:</b>\n\n"
    for t in tags:
        text += f"• <code>@{t[0]}</code>\n"

    await message.answer(text, reply_markup=get_back_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    
    if await is_user_banned(user_id):
        await callback.answer("❌ You are banned.", show_alert=True)
        return

    if not await check_subscription(user_id):
        await callback.message.edit_text("⚠ Please subscribe to our channel to access the bot!", reply_markup=get_sub_keyboard(), parse_mode="HTML")
        return

    plan = await get_user_plan(user_id)
    text = (
        f"⚡ <b>TagPulse Main Menu</b>\n\n"
        f"👤 <b>Plan Status:</b> <code>{plan}</code>\n"
        f"Choose an option below:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(user_id, plan), parse_mode="HTML")
    await callback.answer()

# --- Handlers: Search Generator ---

@dp.callback_query(F.data == "menu_search_gen")
async def cb_menu_search_gen(callback: CallbackQuery):
    if await is_user_banned(callback.from_user.id): return
    if not await check_subscription(callback.from_user.id):
        await callback.message.edit_text("⚠ Subscribe to channel first!", reply_markup=get_sub_keyboard())
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔤 5 Chars (Letters)", callback_data="gen_5_alpha"),
         InlineKeyboardButton(text="🔢 5 Chars (Mixed)", callback_data="gen_5_alnum")],
        [InlineKeyboardButton(text="🔤 6 Chars (Letters)", callback_data="gen_6_alpha"),
         InlineKeyboardButton(text="🔢 6 Chars (Mixed)", callback_data="gen_6_alnum")],
        [InlineKeyboardButton(text="🔤 7 Chars (Letters)", callback_data="gen_7_alpha"),
         InlineKeyboardButton(text="🔢 7 Chars (Mixed)", callback_data="gen_7_alnum")],
        [InlineKeyboardButton(text="🔤 8 Chars (Letters)", callback_data="gen_8_alpha"),
         InlineKeyboardButton(text="🔢 8 Chars (Mixed)", callback_data="gen_8_alnum")],
        [InlineKeyboardButton(text="⬅ Back", callback_data="main_menu")]
    ])
    text = "<b>🎲 Select username length and format to search:</b>"
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("gen_"))
async def cb_process_generate(callback: CallbackQuery):
    user_id = callback.from_user.id
    if await is_user_banned(user_id): return
    if not await check_subscription(user_id):
        await callback.message.edit_text("⚠ Subscribe to channel first!", reply_markup=get_sub_keyboard())
        return

    plan = await get_user_plan(user_id)
    allowed, remaining_attempts = await check_and_update_limits(user_id, plan)
    
    if not allowed:
        await callback.answer("❌ Limit reached! Upgrade to PREMIUM for unlimited searches.", show_alert=True)
        return

    parts = callback.data.split("_")
    length = int(parts[1])
    include_nums = (parts[2] == "alnum")

    is_premium = "PREMIUM" in plan
    target_count = 3 if is_premium else 1

    await callback.answer("⚡ Searching with 2.5x priority speed..." if is_premium else "Searching...", show_alert=False)

    found_results = []
    attempts = 0
    max_attempts = 25

    async with aiosqlite.connect(DB_PATH) as db:
        while len(found_results) < target_count and attempts < max_attempts:
            attempts += 1
            tag = generate_username(length, include_nums)
            
            await db.execute("UPDATE stats SET total_searches = total_searches + 1 WHERE id = 1")
            
            is_free = await check_telegram_username(tag)
            if is_free:
                await db.execute("UPDATE stats SET found_usernames = found_usernames + 1 WHERE id = 1")
                await db.execute("INSERT INTO user_tags (user_id, tag_name) VALUES (?, ?)", (user_id, tag))
                found_results.append(f"✅ <code>@{tag}</code> — <b>AVAILABLE!</b>")
            
            await asyncio.sleep(0.06 if is_premium else 0.15)
            
        await db.commit()

    if found_results:
        header = f"<b>🔎 Search Results ({plan}):</b>\n\n"
        body = "\n".join(found_results)
    else:
        header = "<b>🔎 Search Results:</b>\n\n"
        body = f"❌ Checked {attempts} generated tags, but none were free. Click below to try again!"

    if not is_premium:
        body += f"\n\n📊 <i>Remaining attempts today: {remaining_attempts}/5</i>\n💡 <i>Upgrade to PREMIUM for 2.5x faster search & 3 tags per click!</i>"
    else:
        body += f"\n\n⚡ <i>Priority 2.5x Fast Engine Active</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Search Again", callback_data=callback.data)],
        [InlineKeyboardButton(text="⚙️ Change Length", callback_data="menu_search_gen")],
        [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="main_menu")]
    ])

    await callback.message.edit_text(header + body, reply_markup=kb, parse_mode="HTML")

# --- Handlers: Sniper ---

@dp.callback_query(F.data == "menu_sniper")
async def cb_menu_sniper(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if await is_user_banned(user_id): return
    if not await check_subscription(user_id):
        await callback.message.edit_text("⚠ Subscribe to channel first!", reply_markup=get_sub_keyboard())
        return

    plan = await get_user_plan(user_id)
    if "PREMIUM" not in plan:
        await callback.answer("🔒 Auto-Sniper is for PREMIUM users only!", show_alert=True)
        return

    await state.set_state(Form.waiting_for_snipe_tag)
    await callback.message.edit_text(
        "🎯 <b>Auto-Sniper 24/7</b>\n\nSend me the taken username you want to monitor (e.g. <code>my_tag</code>):",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(Form.waiting_for_snipe_tag)
async def process_snipe_tag(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if await is_user_banned(user_id): return

    tag = message.text.strip().lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO snipes (user_id, username, status) VALUES (?, ?, 'ACTIVE')", (user_id, tag))
        await db.commit()

    await message.answer(
        f"🎯 Added <code>@{tag}</code> to 24/7 Sniper Queue!",
        reply_markup=get_back_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()

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
                        except Exception:
                            pass
                        await db.execute("UPDATE snipes SET status = 'FOUND' WHERE id = ?", (snipe_id,))
                        await db.commit()
        except Exception as e:
            logger.error(f"Error in sniper: {e}")

        await asyncio.sleep(45)

# --- Premium & Admin Handlers ---

@dp.callback_query(F.data == "menu_tags")
async def cb_menu_tags(callback: CallbackQuery):
    await cmd_tags(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "menu_premium")
async def cb_menu_premium(callback: CallbackQuery):
    if await is_user_banned(callback.from_user.id): return
    if not await check_subscription(callback.from_user.id):
        await callback.message.edit_text("⚠ Subscribe to channel first!", reply_markup=get_sub_keyboard())
        return

    plan = await get_user_plan(callback.from_user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT referrals FROM users WHERE user_id = ?", (callback.from_user.id,)) as cur:
            row = await cur.fetchone()
            refs = row[0] if row else 0

    text = (
        f"⚡ <b>TagPulse Premium</b>\n\n"
        f"Your ultimate tool for hunting rare usernames 🎯\n\n"
        f"🌟 <b>PREMIUM:</b>\n"
        f"└ ⚡ <b>2.5x Faster Search Speed</b>\n"
        f"└ ♾️ <b>Unlimited Daily Searches</b>\n"
        f"└ 📦 <b>3 Available Tags</b> per click\n"
        f"└ 🎯 <b>Auto-Sniper 24/7</b>\n\n"
        f"💳 <b>How to Get Premium:</b>\n"
        f"• <b>5 ⭐</b> / month\n"
        f"• 🤝 Invite <b>3 friends</b> to get 7 days free!\n\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{ref_link}</code>\n"
        f"👥 Invites Progress: <b>{refs}/3</b>"
    )

    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- ADMIN PANEL ---

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Access Denied!", show_alert=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT total_searches, found_usernames FROM stats WHERE id = 1") as cur:
            st = await cur.fetchone()
            searches, found = (st[0], st[1]) if st else (0, 0)

    text = (
        "<b>⚙️ Owner Admin Panel</b>\n\n"
        f"• Total Users: <code>{total_users}</code>\n"
        f"• Total Searches: <code>{searches}</code>\n"
        f"• Found Tags: <code>{found}</code>\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Give Premium", callback_data="admin_give_prem")],
        [InlineKeyboardButton(text="🚫 Ban", callback_data="admin_ban"), InlineKeyboardButton(text="✅ Unban", callback_data="admin_unban")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_give_prem")
async def cb_admin_give_prem(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.set_state(Form.waiting_for_admin_give_perm)
    await callback.message.edit_text("Enter User ID and Days (e.g. <code>123456789 30</code>):", reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(Form.waiting_for_admin_give_perm)
async def process_admin_give_prem(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.strip().split()
        target_id = int(parts[0])
        days = int(parts[1]) if len(parts) > 1 else 30

        until = datetime.datetime.now() + datetime.timedelta(days=days)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET plan = 'PREMIUM', premium_until = ? WHERE user_id = ?", (until, target_id))
            await db.commit()
        await message.answer(f"✅ Granted {days} days Premium to <code>{target_id}</code>!", parse_mode="HTML")
    except Exception:
        await message.answer("❌ Use format: <code>USER_ID DAYS</code>")
    await state.clear()

@dp.callback_query(F.data == "admin_ban")
async def cb_admin_ban(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.set_state(Form.waiting_for_ban_id)
    await callback.message.edit_text("Send User ID to BAN:", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.message(Form.waiting_for_ban_id)
async def process_admin_ban(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.strip())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_id,))
            await db.commit()
        await message.answer(f"🚫 User <code>{target_id}</code> banned.", parse_mode="HTML")
    except ValueError:
        await message.answer("Invalid User ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_unban")
async def cb_admin_unban(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.set_state(Form.waiting_for_unban_id)
    await callback.message.edit_text("Send User ID to UNBAN:", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.message(Form.waiting_for_unban_id)
async def process_admin_unban(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.strip())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target_id,))
            await db.commit()
        await message.answer(f"✅ User <code>{target_id}</code> unbanned.", parse_mode="HTML")
    except ValueError:
        await message.answer("Invalid User ID.")
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.set_state(Form.waiting_for_broadcast)
    await callback.message.edit_text("Send broadcast text:", reply_markup=get_back_keyboard())
    await callback.answer()

@dp.message(Form.waiting_for_broadcast)
async def process_admin_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_banned = 0") as cur:
            users = await cur.fetchall()

    success, failed = 0, 0
    for u in users:
        try:
            await message.copy_to(chat_id=u[0])
            success += 1
        except Exception:
            failed += 1

    await message.answer(f"📢 <b>Broadcast Finished!</b>\n\n✅ Delivered: {success}\n❌ Failed: {failed}", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "tester_panel")
async def cb_tester_panel(callback: CallbackQuery):
    if callback.from_user.id not in (ADMIN_ID, TESTER_ID): return
    await callback.message.edit_text("🧪 <b>Tester Panel:</b> All systems operational.", reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- Entry Point ---

async def main():
    await init_db()
    asyncio.create_task(sniper_background_worker())
    
    logger.info("TagPulse Bot fully operational...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(main())
            
