import asyncio
import datetime
import logging
import os
import sqlite3
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")

# 👇 Enter your Telegram ID here to test referral rewards via /addref
TEST_ADMIN_ID = 5619415334  # Replace with your ID

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- DATABASE (SQLite) ---
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

# --- MINIMALIST KEYBOARDS ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Premium & Referrals", callback_data="menu_premium")],
        [InlineKeyboardButton(text="🔍 Pulse Monitor", callback_data="menu_monitor")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])

# --- HANDLERS ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
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
        "<i>Real-time username tracking & analytics.</i>\n\n"
        "Select an option below or send a username to check it:"
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
        f"🧪 <b>[TEST]</b> Referral processed successfully.\n"
        f"Scale: <code>{user_data[2]}/5</code> | Total: <code>{user_data[3]}</code>",
        parse_mode="HTML"
    )

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
        "<b>Rewards:</b>\n"
        "• 2 referrals → +1 day Premium\n"
        "• 3 referrals → +3 days Premium\n"
        "• 5 referrals → +7 days Premium (scale resets)\n\n"
        "<b>Your referral link:</b>\n"
        f"<code>{ref_link}</code>"
    )
    
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "menu_monitor")
async def show_monitor_menu(callback: CallbackQuery):
    text = (
        "<b>[ Pulse Monitor ]</b>\n\n"
        "Send any username (e.g. <code>durov</code> or <code>@username</code>) to check its availability status right now.\n\n"
        "<i>Free: 1 slot | Premium: 5–10 slots + instant alerts</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "menu_back")
async def back_to_main(callback: CallbackQuery):
    text = (
        "<b>TagPulse</b>\n"
        "<i>Real-time username tracking & analytics.</i>\n\n"
        "Select an option below or send a username to check it:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- USERNAME CHECKER HANDLER ---
@dp.message(F.text & ~F.text.startswith("/"))
async def check_username(message: Message):
    raw_text = message.text.strip()
    username = raw_text.lstrip("@").strip()
    
    if len(username) < 5:
        await message.answer("⚠️ Username must be at least 5 characters long according to Telegram rules.")
        return

    processing_msg = await message.answer(f"🔍 Checking <code>@{username}</code>...", parse_mode="HTML")

    try:
        chat = await bot.get_chat(f"@{username}")
        
        # Determine account type
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
        # If chat is not found, the username is likely available (or banned/restricted)
        result_text = (
            f"<b>[ Username Status ]</b>\n\n"
            f"Target: <code>@{username}</code>\n"
            f"Status: <b>Available / Not Found ✅</b>\n"
            f"<i>(Tip: Verify directly in Telegram search)</i>"
        )
    except Exception:
        result_text = f"⚠️ Error checking <code>@{username}</code>. Try again later."

    await processing_msg.edit_text(result_text, reply_markup=get_back_keyboard(), parse_mode="HTML")

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("TagPulse Bot with Username Checker is online!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
