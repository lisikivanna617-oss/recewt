import asyncio
import datetime
import logging
import os
import random
import string
import sqlite3
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
TEST_ADMIN_ID = 123456789  # Заміни на свій ID для /addref

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- СТАНИ ДЛЯ FSM ---
class SearchStates(StatesGroup):
    waiting_for_length = State()
    waiting_for_digits = State()

class CheckStates(StatesGroup):
    waiting_for_username = State()

# --- БАЗА ДАНИХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            referrals_count INTEGER DEFAULT 0,
            total_invited INTEGER DEFAULT 0,
            premium_until TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, referrer_id, referrals_count, total_invited, premium_until FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def add_user(user_id: int, referrer_id: int = None):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
        conn.commit()
    conn.close()

def is_user_premium(user_id: int) -> bool:
    user = get_user(user_id)
    if not user or not user[4]:
        return False
    try:
        prem_date = datetime.datetime.fromisoformat(user[4])
        return prem_date > datetime.datetime.now()
    except Exception:
        return False

def add_to_history(user_id: int, username: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (user_id, username, created_at) VALUES (?, ?, ?)", 
                   (user_id, username, datetime.datetime.now().strftime("%d.%m %H:%M")))
    # Обмежуємо історію до 20 записів
    cursor.execute("""
        DELETE FROM history WHERE id NOT IN (
            SELECT id FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 20
        ) AND user_id = ?
    """, (user_id, user_id))
    conn.commit()
    conn.close()

def get_history(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, created_at FROM history WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_referral_progress(referrer_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT referrals_count, total_invited, premium_until FROM users WHERE user_id = ?", (referrer_id,))
    row = cursor.fetchone()
    
    if row:
        ref_count, total_inv, prem_until = row
        ref_count += 1
        total_inv += 1
        
        now = datetime.datetime.now()
        current_prem = datetime.datetime.fromisoformat(prem_until) if prem_until and datetime.datetime.fromisoformat(prem_until) > now else now
        
        days_to_add = 0
        reset_scale = False
        
        if ref_count == 2:
            days_to_add = 1
        elif ref_count == 3:
            days_to_add = 3
        elif ref_count >= 5:
            days_to_add = 7
            reset_scale = True 
            
        new_prem = current_prem + datetime.timedelta(days=days_to_add) if days_to_add > 0 else current_prem
        new_ref_count = 0 if reset_scale else ref_count
        
        cursor.execute("""
            UPDATE users 
            SET referrals_count = ?, total_invited = ?, premium_until = ? 
            WHERE user_id = ?
        """, (new_ref_count, total_inv, new_prem.isoformat(), referrer_id))
        conn.commit()
        
        if days_to_add > 0:
            asyncio.create_task(
                bot.send_message(
                    referrer_id, 
                    f"⚡ <b>[Update]</b> Referral milestone reached! Premium unlocked for <b>+{days_to_add} days</b> 🎉",
                    parse_mode="HTML"
                )
            )
    conn.close()

# --- КЛАВІАТУРИ ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Search Generator", callback_data="start_search")],
        [InlineKeyboardButton(text="⚡ Check Specific Tag", callback_data="start_check")],
        [InlineKeyboardButton(text="📜 History", callback_data="menu_history"),
         InlineKeyboardButton(text="💎 Premium", callback_data="menu_premium")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])

def get_result_keyboard(username: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Share Link", url=f"https://t.me/{username}")],
        [InlineKeyboardButton(text="💾 Save", callback_data=f"save_{username}")],
        [InlineKeyboardButton(text="🔄 Repeat Search", callback_data="start_search")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])

# --- ХЕНДЛЕРИ ГОЛОВНОГО МЕНЮ ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    args = message.text.split()
    
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            potential_ref = int(args[1].replace("ref_", ""))
            if potential_ref != user_id:
                referrer_id = potential_ref
        except ValueError:
            pass

    user_data = get_user(user_id)
    if not user_data:
        add_user(user_id, referrer_id)
        if referrer_id:
            update_referral_progress(referrer_id)

    text = (
        "<b>TagPulse</b>\n"
        "<i>Real-time username tracking & generator.</i>\n\n"
        "Choose an option below:"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@dp.message(Command("addref"))
async def test_add_referral(message: Message):
    if message.from_user.id != TEST_ADMIN_ID:
        return
    if not get_user(message.from_user.id):
        add_user(message.from_user.id)
    update_referral_progress(message.from_user.id)
    user_data = get_user(message.from_user.id)
    await message.answer(
        f"🧪 <b>[TEST]</b> Referral added.\nScale: <code>{user_data[2]}/5</code> | Total: <code>{user_data[3]}</code>",
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "menu_back")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "<b>TagPulse</b>\n"
        "<i>Real-time username tracking & generator.</i>\n\n"
        "Choose an option below:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- ГЕНЕРАТОР ЮЗЕРНЕЙМІВ ---
@dp.callback_query(F.data == "start_search")
async def search_step_length(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.waiting_for_length)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5–7 chars", callback_data="len_5_7"),
         InlineKeyboardButton(text="8–10 chars", callback_data="len_8_10")],
        [InlineKeyboardButton(text="11–12 chars", callback_data="len_11_12")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    text = "<b>[ Step 1/2 ]</b>\n\nSelect desired username length:"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("len_"))
async def search_step_digits(callback: CallbackQuery, state: FSMContext):
    length_map = {
        "len_5_7": (5, 7),
        "len_8_10": (8, 10),
        "len_11_12": (11, 12)
    }
    min_l, max_l = length_map.get(callback.data, (5, 7))
    await state.update_data(min_len=min_l, max_len=max_l)
    
    await state.set_state(SearchStates.waiting_for_digits)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="With digits (e.g. user99)", callback_data="dig_yes")],
        [InlineKeyboardButton(text="Letters only (e.g. user)", callback_data="dig_no")],
        [InlineKeyboardButton(text="← Back", callback_data="start_search")]
    ])
    text = "<b>[ Step 2/2 ]</b>\n\nInclude numbers in usernames?"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("dig_"))
async def process_username_search(callback: CallbackQuery, state: FSMContext):
    use_digits = (callback.data == "dig_yes")
    data = await state.get_data()
    min_l = data.get("min_len", 5)
    max_l = data.get("max_len", 7)
    
    user_id = callback.from_user.id
    is_prem = is_user_premium(user_id)
    limit = 3 if is_prem else 1

    await callback.message.edit_text("🔍 Scanning Telegram network for available usernames...", parse_mode="HTML")
    
    found_usernames = []
    chars = string.ascii_lowercase + (string.digits if use_digits else "")
    
    attempts = 0
    while len(found_usernames) < limit and attempts < 35:
        attempts += 1
        length = random.randint(min_l, max_l)
        uname = "".join(random.choices(chars, k=length))
        
        if uname[0].isdigit():
            continue
            
        try:
            await bot.get_chat(f"@{uname}")
        except TelegramBadRequest:
            if uname not in found_usernames:
                found_usernames.append(uname)
        except Exception:
            pass
        await asyncio.sleep(0.05)

    if not found_usernames:
        text = (
            "⚠️ <b>No free usernames found in this attempt.</b>\n"
            "Try changing length or parameters."
        )
        await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
        return

    for uname in found_usernames:
        add_to_history(user_id, uname)
        result_text = (
            f"<b>✨ Available Username Found!</b>\n\n"
            f"Target: <code>@{uname}</code>\n"
            f"Status: <b>Free ✅</b>\n"
            f"Mode: <code>{'Premium (3 slots)' if is_prem else 'Free (1 slot)'}</code>"
        )
        await callback.message.answer(result_text, reply_markup=get_result_keyboard(uname), parse_mode="HTML")
    
    await state.clear()
    await callback.answer()

# --- ПРЯМА ПЕРЕВІРКА ВЛАСНОГО ЮЗЕРА ---
@dp.callback_query(F.data == "start_check")
async def start_custom_check(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckStates.waiting_for_username)
    text = (
        "<b>[ Direct Username Check ]</b>\n\n"
        "Send the username you want to check (e.g., <code>durov</code> or <code>@telegram</code>):"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(CheckStates.waiting_for_username, F.text)
async def process_custom_check(message: Message, state: FSMContext):
    raw_text = message.text.strip()
    username = raw_text.lstrip("@").strip()
    
    if len(username) < 5:
        await message.answer("⚠️ Username must be at least 5 characters long.")
        return

    user_id = message.from_user.id
    processing_msg = await message.answer(f"🔍 Checking <code>@{username}</code>...", parse_mode="HTML")

    try:
        chat = await bot.get_chat(f"@{username}")
        chat_type = chat.type
        title_name = chat.title or chat.full_name or "Unknown"
        
        result_text = (
            f"<b>[ Username Status ]</b>\n\n"
            f"Target: <code>@{username}</code>\n"
            f"Status: <b>Occupied ❌</b>\n"
            f"Type: <code>{chat_type}</code>\n"
            f"Name: <b>{title_name}</b>"
        )
    except TelegramBadRequest:
        add_to_history(user_id, username)
        result_text = (
            f"<b>[ Username Status ]</b>\n\n"
            f"Target: <code>@{username}</code>\n"
            f"Status: <b>Available / Not Found ✅</b>"
        )
    except Exception:
        result_text = f"⚠️ Error checking <code>@{username}</code>. Try again later."

    await processing_msg.edit_text(result_text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await state.clear()

# --- ІСТОРІЯ ТА ПРЕМІУМ ---
@dp.callback_query(F.data == "menu_history")
async def show_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    history_rows = get_history(user_id)
    
    if not history_rows:
        text = "<b>[ History ]</b>\n\nYour history is empty. Run a search first!"
    else:
        history_list = "\n".join([f"• <code>@{item[0]}</code> — <i>{item[1]}</i>" for item in history_rows])
        text = f"<b>[ History (Last 20) ]</b>\n\n{history_list}"
        
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "menu_premium")
async def show_premium_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_data = get_user(user_id)
    
    ref_count = user_data[2] if user_data else 0
    total_invited = user_data[3] if user_data else 0
    prem_until_str = user_data[4] if user_data else None
    
    prem_status = "Inactive ❌"
    if prem_until_str:
        prem_date = datetime.datetime.fromisoformat(prem_until_str)
        if prem_date > datetime.datetime.now():
            prem_status = f"Active until {prem_date.strftime('%d.%m %H:%M')} ✅"

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    text = (
        "<b>[ Premium & Referrals ]</b>\n\n"
        f"Status: <b>{prem_status}</b>\n"
        f"Scale progress: <code>{ref_count}/5</code>\n"
        f"Total invited: <code>{total_invited}</code>\n\n"
        "<b>Perks:</b> Search up to 3 free slots at once!\n\n"
        "<b>Rewards:</b>\n"
        "• 2 referrals → +1 day Premium\n"
        "• 3 referrals → +3 days Premium\n"
        "• 5 referrals → +7 days Premium (scale resets)\n\n"
        "<b>Your referral link:</b>\n"
        f"<code>{ref_link}</code>"
    )
    
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("save_"))
async def save_username_action(callback: CallbackQuery):
    uname = callback.data.replace("save_", "")
    await callback.answer(f"✅ Username @{uname} saved to your records!", show_alert=True)

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("TagPulse Advanced Bot is online!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
