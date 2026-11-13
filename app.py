import sys
import os
import logging
import asyncio
import datetime
import threading
import random
import string
import aiosqlite
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5619415334"))
HELPER_ID = int(os.environ.get("HELPER_ID", "8644168067"))
DB_PATH = "bot_database.db"

CHANNEL_ID = "@otxen"
CHANNEL_URL = "https://t.me/otxen"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Keep-Alive Web Server ---
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "UserScout Tactical Engine - ONLINE"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# --- FSM States ---
class Form(StatesGroup):
    waiting_for_snipe = State()

# --- Database Initialization ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                plan TEXT DEFAULT 'CLEARANCE 1',
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
                status TEXT DEFAULT 'SCANNING'
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

async def check_subscription(user_id: int) -> bool:
    if user_id in (ADMIN_ID, HELPER_ID):
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return True

async def get_user_clearance(user_id: int) -> str:
    if user_id == ADMIN_ID:
        return "COMMANDER [OWNER]"
    if user_id == HELPER_ID:
        return "TACTICAL OPERATOR"

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT plan, premium_until FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                return "RECON [FREE]"
            plan, until = row[0], row[1]
            if plan == "PRO [PREMIUM]" and until:
                if datetime.datetime.now() > datetime.datetime.fromisoformat(until):
                    await db.execute("UPDATE users SET plan = 'RECON [FREE]' WHERE user_id = ?", (user_id,))
                    await db.commit()
                    return "RECON [FREE]"
            return plan

async def check_limits(user_id: int, plan: str) -> tuple[bool, int]:
    if "PRO" in plan or "COMMANDER" in plan or "OPERATOR" in plan:
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

        if searches >= 5:
            return False, 0

        await db.execute("UPDATE users SET daily_searches = daily_searches + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
        return True, 5 - (searches + 1)

def generate_username(length: int, include_numbers: bool) -> str:
    chars = string.ascii_lowercase
    if include_numbers:
        chars += string.digits
    first_char = random.choice(string.ascii_lowercase)
    return first_char + ''.join(random.choice(chars) for _ in range(length - 1))

# --- Keyboards ---
def kb_sub_required():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📡 JOIN INTEL CHANNEL", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="🔄 VERIFY ACCESS", callback_data="check_sub")]
    ])

def kb_terminal_main(user_id: int):
    buttons = [
        [InlineKeyboardButton(text="🛰 RADAR SCOUT (Scan Tags)", callback_data="menu_scout")],
        [InlineKeyboardButton(text="🎯 TARGET LOCK 24/7 (Sniper)", callback_data="menu_sniper")],
        [InlineKeyboardButton(text="📂 INTEL VAULT (Saved Tags)", callback_data="menu_vault")],
        [InlineKeyboardButton(text="⚡ UPGRADE CLEARANCE (VIP)", callback_data="menu_clearance")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="👑 COMMAND HQ", callback_data="admin_panel")])
    elif user_id == HELPER_ID:
        buttons.append([InlineKeyboardButton(text="🛠 OPERATOR PANEL", callback_data="helper_panel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_return():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ TERMINAL MAIN", callback_data="main_menu")]
    ])

def kb_length_select():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▫️ 5 CHARS", callback_data="len_5"), InlineKeyboardButton(text="▫️ 6 CHARS", callback_data="len_6")],
        [InlineKeyboardButton(text="▫️ 7 CHARS", callback_data="len_7"), InlineKeyboardButton(text="▫️ 8 CHARS", callback_data="len_8")],
        [InlineKeyboardButton(text="◀️ ABORT SCAN", callback_data="main_menu")]
    ])

def kb_mode_select(length: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔤 LETTERS ONLY (a-z)", callback_data=f"scan_{length}_alpha")],
        [InlineKeyboardButton(text="🔢 ALPHA-NUMERIC (a-z, 0-9)", callback_data=f"scan_{length}_alnum")],
        [InlineKeyboardButton(text="◀️ RECONFIG LENGTH", callback_data="menu_scout")]
    ])

# --- Handlers ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if await is_user_banned(user_id):
        await message.answer("🚫 <b>ACCESS DENIED:</b> Your terminal has been blacklisted.")
        return

    if not await check_subscription(user_id):
        await message.answer(
            "⚠️ <b>AUTHENTICATION REQUIRED</b>\n\nTo access the UserScout Recon Network, you must join our intel channel first:",
            reply_markup=kb_sub_required(),
            parse_mode="HTML"
        )
        return

    args = message.text.split()
    ref_by = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            exists = await cur.fetchone()

        if not exists:
            await db.execute(
                "INSERT INTO users (user_id, referred_by, last_search_date) VALUES (?, ?, ?)",
                (user_id, ref_by if ref_by != user_id else None, datetime.date.today().isoformat())
            )
            if ref_by and ref_by != user_id:
                await db.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (ref_by,))
                async with db.execute("SELECT referrals FROM users WHERE user_id = ?", (ref_by,)) as cur:
                    r_row = await cur.fetchone()
                    if r_row and r_row[0] >= 3:
                        until = datetime.datetime.now() + datetime.timedelta(days=7)
                        await db.execute("UPDATE users SET plan = 'PRO [PREMIUM]', premium_until = ? WHERE user_id = ?", (until, ref_by))
            await db.commit()

    clearance = await get_user_clearance(user_id)
    text = (
        f"<b>[ USERSCOUT TACTICAL TERMINAL v2.0 ]</b>\n"
        f"────────────────────────\n"
        f"🟢 SYSTEM STATUS: <b>OPERATIONAL</b>\n"
        f"👤 USER CLEARANCE: <code>{clearance}</code>\n"
        f"────────────────────────\n"
        f"<i>Select an operation mode from the command module below:</i>"
    )
    await message.answer(text, reply_markup=kb_terminal_main(user_id), parse_mode="HTML")

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: CallbackQuery):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        await callback.answer("✅ ACCESS GRANTED!")
        clearance = await get_user_clearance(user_id)
        text = f"<b>[ TERMINAL MAIN ]</b>\n\nStatus: <b>ONLINE</b>\nClearance: <code>{clearance}</code>"
        await callback.message.edit_text(text, reply_markup=kb_terminal_main(user_id), parse_mode="HTML")
    else:
        await callback.answer("❌ AUTH FAILED: Channel membership not detected!", show_alert=True)

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    if await is_user_banned(user_id): return
    if not await check_subscription(user_id):
        await callback.message.edit_text("⚠️ Authorization required!", reply_markup=kb_sub_required())
        return

    clearance = await get_user_clearance(user_id)
    text = f"<b>[ TERMINAL MAIN ]</b>\n\nStatus: <b>ONLINE</b>\nClearance: <code>{clearance}</code>"
    await callback.message.edit_text(text, reply_markup=kb_terminal_main(user_id), parse_mode="HTML")

# --- Radar Scout Flow ---

@dp.callback_query(F.data == "menu_scout")
async def cb_menu_scout(callback: CallbackQuery):
    if await is_user_banned(callback.from_user.id): return
    if not await check_subscription(callback.from_user.id):
        await callback.message.edit_text("⚠️️ Authorization required!", reply_markup=kb_sub_required())
        return

    text = "<b>[ RADAR SCOUT CONFIG ]</b>\n\nSelect target username length for deep scanning:"
    await callback.message.edit_text(text, reply_markup=kb_length_select(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("len_"))
async def cb_select_length(callback: CallbackQuery):
    length = int(callback.data.split("_")[1])
    text = f"<b>[ PARAMETER SET ]</b> Target Length: <b>{length} Characters</b>\n\nSelect character combination set:"
    await callback.message.edit_text(text, reply_markup=kb_mode_select(length), parse_mode="HTML")

@dp.callback_query(F.data.startswith("scan_"))
async def cb_process_scan(callback: CallbackQuery):
    user_id = callback.from_user.id
    if await is_user_banned(user_id): return

    clearance = await get_user_clearance(user_id)
    allowed, remaining = await check_limits(user_id, clearance)

    if not allowed:
        await callback.answer("⛔ DAILY RADAR QUOTA EXHAUSTED! Upgrade clearance for unlimited scans.", show_alert=True)
        return

    parts = callback.data.split("_")
    length = int(parts[1])
    include_nums = (parts[2] == "alnum")
    is_pro = ("PRO" in clearance or "COMMANDER" in clearance or "OPERATOR" in clearance)

    await callback.answer("🛰️ RADAR SWEEP INITIATED..." if is_pro else "🛰️ RADAR SWEEPING (STANDARD SPEED)...")

    target_count = 3 if is_pro else 1
    found_tags = []
    attempts = 0
    max_attempts = 45 if is_pro else 20

    async with aiosqlite.connect(DB_PATH) as db:
        while len(found_tags) < target_count and attempts < max_attempts:
            attempts += 1
            tag = generate_username(length, include_nums)
            await db.execute("UPDATE stats SET total_searches = total_searches + 1 WHERE id = 1")

            is_free = False
            try:
                await bot.get_chat(f"@{tag}")
            except Exception as e:
                err = str(e).lower()
                if "chat not found" in err or "user not found" in err:
                    is_free = True

            if is_free:
                await db.execute("UPDATE stats SET found_usernames = found_usernames + 1 WHERE id = 1")
                await db.execute("INSERT INTO user_tags (user_id, tag_name) VALUES (?, ?)", (user_id, tag))
                found_tags.append(f"🎯 <code>@{tag}</code> — <b>UNCLAIMED [AVAILABLE]</b>")

            await asyncio.sleep(0.12 if is_pro else 0.35)

        await db.commit()

    if found_tags:
        text = f"<b>[ RADAR INTEL REPORT ]</b>\n────────────────────────\n" + "\n".join(found_tags)
    else:
        text = f"<b>[ RADAR INTEL REPORT ]</b>\n────────────────────────\n❌ Evaluated {attempts} vectors. All targets currently occupied."

    if not is_pro:
        text += f"\n────────────────────────\n📊 <i>Daily quota remaining: {remaining}/5</i>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 RE-RUN RADAR SWEEP", callback_data=callback.data)],
        [InlineKeyboardButton(text="⚙️️ CHANGE LENGTH", callback_data="menu_scout")],
        [InlineKeyboardButton(text="◀️ TERMINAL MAIN", callback_data="main_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# --- Target Lock (Sniper) & Vault ---

@dp.callback_query(F.data == "menu_vault")
async def cb_vault(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tag_name FROM user_tags WHERE user_id = ?", (user_id,)) as cur:
            tags = await cur.fetchall()

    if not tags:
        text = "<b>[ INTEL VAULT ]</b>\n────────────────────────\nNo intel logged yet. Run a Radar Sweep to discover free tags."
    else:
        formatted_list = "\n".join([f"• <code>@{t[0]}</code>" for t in tags])
        text = f"<b>[ INTEL VAULT: SECURED TAGS ]</b>\n────────────────────────\n{formatted_list}"

    await callback.message.edit_text(text, reply_markup=kb_return(), parse_mode="HTML")

@dp.callback_query(F.data == "menu_sniper")
async def cb_sniper(callback: CallbackQuery, state: FSMContext):
    clearance = await get_user_clearance(callback.from_user.id)
    if "PRO" not in clearance and "COMMANDER" not in clearance and "OPERATOR" not in clearance:
        await callback.answer("🔒 TARGET LOCK REQUIRES PRO CLEARANCE!", show_alert=True)
        return

    await state.set_state(Form.waiting_for_snipe)
    await callback.message.edit_text(
        "<b>[ TARGET LOCK 24/7 ]</b>\n────────────────────────\n"
        "Input the exact username you wish to lock onto (e.g. <code>shadow</code>):",
        reply_markup=kb_return(),
        parse_mode="HTML"
    )

@dp.message(Form.waiting_for_snipe)
async def process_snipe(message: Message, state: FSMContext):
    tag = message.text.strip().lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO snipes (user_id, username) VALUES (?, ?)", (message.from_user.id, tag))
        await db.commit()

    await message.answer(
        f"🎯 <b>TARGET LOCKED:</b> <code>@{tag}</code>\nSystem is now monitoring availability 24/7.",
        reply_markup=kb_return(),
        parse_mode="HTML"
    )
    await state.clear()

async def sniper_worker():
    while True:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT id, user_id, username FROM snipes WHERE status = 'SCANNING'") as cur:
                    snipes = await cur.fetchall()

                for s_id, u_id, tag in snipes:
                    is_free = False
                    try:
                        await bot.get_chat(f"@{tag}")
                    except Exception as e:
                        if "chat not found" in str(e).lower() or "user not found" in str(e).lower():
                            is_free = True

                    if is_free:
                        try:
                            await bot.send_message(
                                u_id,
                                f"🚨 <b>TARGET UNLOCKED!</b>\n\nTarget username <code>@{tag}</code> is now <b>AVAILABLE FOR CLAIM</b>!",
                                parse_mode="HTML"
                            )
                        except Exception: pass
                        await db.execute("UPDATE snipes SET status = 'NEUTRALIZED' WHERE id = ?", (s_id,))
                        await db.commit()
        except Exception as e:
            logger.error(f"Sniper cycle error: {e}")
        await asyncio.sleep(60)

# --- Upgrade & HQ Panels ---

@dp.callback_query(F.data == "menu_clearance")
async def cb_clearance(callback: CallbackQuery):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT referrals FROM users WHERE user_id = ?", (callback.from_user.id,)) as cur:
            row = await cur.fetchone()
            refs = row[0] if row else 0

    text = (
        f"⚡ <b>PRO CLEARANCE UPGRADE</b>\n"
        f"────────────────────────\n"
        f"<b>PRO Tactical Capabilities:</b>\n"
        f"├ 🚀 250% Accelerated Scan Engine\n"
        f"├ ♾️ Unlimited Radar Sweeps 24/7\n"
        f"├ 📦 Multi-Target Scan (3 Tags per click)\n"
        f"└ 🎯 24/7 Automated Target Lock (Sniper)\n\n"
        f"🎁 <b>Recruitment Access Program:</b>\n"
        f"Recruit 3 operators via your tactical link to claim <b>7 Days PRO Access</b> for free!\n\n"
        f"🔗 <b>Your Tactical Link:</b>\n<code>{ref_link}</code>\n\n"
        f"👥 Operators Recruited: <b>{refs}/3</b>"
    )
    await callback.message.edit_text(text, reply_markup=kb_return(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            users = (await cur.fetchone())[0]
        async with db.execute("SELECT total_searches, found_usernames FROM stats WHERE id = 1") as cur:
            st = await cur.fetchone()
            searches, found = (st[0], st[1]) if st else (0, 0)

    text = (
        f"👑 <b>COMMAND HQ METRICS</b>\n"
        f"────────────────────────\n"
        f"• Total Operators: <code>{users}</code>\n"
        f"• Total Sweeps: <code>{searches}</code>\n"
        f"• Unclaimed Tags Discovered: <code>{found}</code>"
    )
    await callback.message.edit_text(text, reply_markup=kb_return(), parse_mode="HTML")

@dp.callback_query(F.data == "helper_panel")
async def cb_helper_panel(callback: CallbackQuery):
    if callback.from_user.id not in (ADMIN_ID, HELPER_ID): return
    await callback.message.edit_text("🛠 <b>OPERATOR CONSOLE:</b> Tactical systems operating at nominal status.", reply_markup=kb_return(), parse_mode="HTML")

# --- Main Entry Point ---

async def main():
    await init_db()
    asyncio.create_task(sniper_worker())

    # Purge old webhooks to ensure polling receives updates properly
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("UserScout Tactical Bot Successfully Launched!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(main())
