import asyncio
import datetime
import logging
import os
import random
import string
import sqlite3
import sys
import threading
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")

# 👇 Твій ID (головний розробник) та ID твого помічника (тестувальник)
OWNER_ID = 5619415334       # Заміни на свій Telegram ID
TESTER_ID = 8644168067      # Заміни на Telegram ID помічника

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
    if user_id in (OWNER_ID, TESTER_ID):
        return True  # Власник та тестувальник завжди мають преміум для перевірки генерації на 3 слоти
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
def get_main_keyboard(user_id: int):
    keyboard = [
        [InlineKeyboardButton(text="🔍 Search Generator", callback_data="start_search")],
        [InlineKeyboardButton(text="⚡ Check Specific Tag", callback_data="start_check")],
        [InlineKeyboardButton(text="📜 History", callback_data="menu_history"),
         InlineKeyboardButton(text="💎 Premium", callback_data="menu_premium")]
    ]
    
    if user_id == TESTER_ID:
        keyboard.append([InlineKeyboardButton(text="🧪 Tester Menu", callback_data="tester_menu")])
    elif user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton(text="👑 Owner Menu", callback_data="tester_menu")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])

# --- ГОЛОВНЕ МЕНЮ ---
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

    badge = ""
    if user_id == TESTER_ID:
        badge = " <i>[🧪 Tester Mode]</i>"
    elif user_id == OWNER_ID:
        badge = " <i>[👑 Owner Mode]</i>"

    text = (
        f"<b>TagPulse</b>{badge}\n"
        "<i>Real-time username tracking & generator.</i>\n\n"
        "Choose an option below:"
    )
    await message.answer(text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")

@dp.callback_query(F.data == "menu_back")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    badge = ""
    if user_id == TESTER_ID:
        badge = " <i>[🧪 Tester Mode]</i>"
    elif user_id == OWNER_ID:
        badge = " <i>[👑 Owner Mode]</i>"

    text = (
        f"<b>TagPulse</b>{badge}\n"
        "<i>Real-time username tracking & generator.</i>\n\n"
        "Choose an option below:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

# --- МЕНЮ ТЕСТУВАЛЬНИКА ---
@dp.callback_query(F.data == "tester_menu")
async def tester_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in (OWNER_ID, TESTER_ID):
        await callback.answer("⛔ Access denied.", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Toggle / Refresh Test Premium", callback_data="test_add_prem")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    text = (
        "<b>🧪 Tester Panel</b>\n\n"
        "Here you can quickly test features and activate a 7-day test premium to check multi-slot generation."
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "test_add_prem")
async def test_add_prem(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in (OWNER_ID, TESTER_ID):
        return
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    new_prem = (datetime.datetime.now() + datetime.timedelta(days=7)).isoformat()
    cursor.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_prem, user_id))
    conn.commit()
    conn.close()
    
    await callback.answer("✅ Test Premium successfully activated for 7 days!", show_alert=True)

# --- ГЕНЕРАТОР ТА ПОШУК (ВИБІР ТОЧНОЇ ДОВЖИНИ) ---
@dp.callback_query(F.data == "start_search")
async def search_step_length(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.waiting_for_length)
    user_id = callback.from_user.id
    
    # Кнопки вибору конкретної довжини від 4 до 12 символів
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
         InlineKeyboardButton(text="5", callback_data="len_5"),
         InlineKeyboardButton(text="6", callback_data="len_6")],
        [InlineKeyboardButton(text="7", callback_data="len_7"),
         InlineKeyboardButton(text="8", callback_data="len_8"),
         InlineKeyboardButton(text="9", callback_data="len_9")],
        [InlineKeyboardButton(text="10", callback_data="len_10"),
         InlineKeyboardButton(text="11", callback_data="len_11"),
         InlineKeyboardButton(text="12", callback_data="len_12")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    text = "<b>[ Step 1/2 ]</b>\n\nSelect exact username length:"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("len_"))
async def search_step_digits(callback: CallbackQuery, state: FSMContext):
    length = int(callback.data.replace("len_", ""))
    await state.update_data(exact_len=length)
    
    await state.set_state(SearchStates.waiting_for_digits)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="With digits (e.g. user99)", callback_data="dig_yes")],
        [InlineKeyboardButton(text="Letters only (e.g. user)", callback_data="dig_no")],
        [InlineKeyboardButton(text="← Back", callback_data="start_search")]
    ])
    text = f"<b>[ Step 2/2 ]</b>\n\nLength: <b>{length} chars</b>.\nInclude numbers in usernames?"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("dig_"))
async def process_username_search(callback: CallbackQuery, state: FSMContext):
    use_digits = (callback.data == "dig_yes")
    data = await state.get_data()
    length = data.get("exact_len", 5)
    
    user_id = callback.from_user.id
    is_prem = is_user_premium(user_id)
    limit = 3 if is_prem else 1

    await callback.message.edit_text("🔍 Scanning Telegram network for available usernames...", parse_mode="HTML")
    
    found_usernames = []
    chars = string.ascii_lowercase + (string.digits if use_digits else "")
    
    attempts = 0
    while len(found_usernames) < limit and attempts < 45:
        attempts += 1
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
        text = "⚠️ <b>No free usernames found in this attempt.</b>\nTry changing length or parameters."
        await callback.message.edit_text(text, reply_markup=get_back_keyboard(user_id), parse_mode="HTML")
        return

    # Формуємо єдине повідомлення зі списком усіх знайдених тегів
    result_lines = []
    keyboard_buttons = []
    
    for uname in found_usernames:
        add_to_history(user_id, uname)
        result_lines.append(f"• <code>@{uname}</code> — <b>Free ✅</b>")
        keyboard_buttons.append([InlineKeyboardButton(text=f"📤 Share @{uname}", url=f"https://t.me/{uname}")])

    usernames_joined = "\n".join(result_lines)
    mode_text = 'Premium / Tester (3 slots)' if is_prem else 'Free (1 slot)'
    
    result_text = (
        f"<b>✨ Available Username(s) Found!</b>\n\n"
        f"{usernames_joined}\n\n"
        f"Mode: <code>{mode_text}</code>"
    )

    keyboard_buttons.append([InlineKeyboardButton(text="🔄 Repeat Search", callback_data="start_search")])
    keyboard_buttons.append([InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")])
    
    result_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await callback.message.edit_text(result_text, reply_markup=result_keyboard, parse_mode="HTML")
    await state.clear()
    await callback.answer()

# --- ПРЯМА ПЕРЕВІРКА ---
@dp.callback_query(F.data == "start_check")
async def start_custom_check(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckStates.waiting_for_username)
    user_id = callback.from_user.id
    text = (
        "<b>[ Direct Username Check ]</b>\n\n"
        "Send the username you want to check (e.g., <code>durov</code> or <code>@telegram</code>):"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(user_id), parse_mode="HTML")
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

    await processing_msg.edit_text(result_text, reply_markup=get_back_keyboard(user_id), parse_mode="HTML")
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
        
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "menu_premium")
async def show_premium_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_data = get_user(user_id)
    
    ref_count = user_data[2] if user_data else 0
    total_invited = user_data[3] if user_data else 0
    prem_until_str = user_data[4] if user_data else None
    
    prem_status = "Inactive ❌"
    if user_id in (OWNER_ID, TESTER_ID):
        prem_status = "Active (Tester / Owner 🧪) ✅"
    elif prem_until_str:
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
    
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

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
    
    # --- ДОДАЙТЕ ОЦЕЙ РЯДОК ---
    threading.Thread(target=run_web, daemon=True).start()
    
    asyncio.run(main())
