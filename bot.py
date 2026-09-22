import asyncio
import html
import logging
import os
import random
import re
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.error("BOT_TOKEN is missing!")

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher()

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

user_data_store = {}

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "saved": [],
            "history": [],
            "checks_count": 0,
        }
    return user_data_store[user_id]

def add_to_history(user_id: int, usernames: list):
    profile = get_user_profile(user_id)
    for u in usernames:
        if u not in profile["history"]:
            profile["history"].insert(0, u)
    profile["history"] = profile["history"][:20]

class BotStates(StatesGroup):
    auto_search = State()
    prefix_search = State()
    smart_variations = State()

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="↻ Auto-Search", callback_data="menu:auto"),
            InlineKeyboardButton(text="⎋ Prefix / Suffix", callback_data="menu:prefix"),
        ],
        [
            InlineKeyboardButton(text="💡 Smart Variations", callback_data="menu:smart"),
            InlineKeyboardButton(text="📁 Profile & Saved", callback_data="menu:profile"),
        ],
        [
            InlineKeyboardButton(text="ⓘ Help", callback_data="menu:help"),
        ]
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="‹ Back", callback_data="menu:main")]])

def length_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 12):
        row.append(InlineKeyboardButton(text=f"[{length}]", callback_data=f"len:{length}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="‹ Back", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def digits_choice_keyboard(length: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="[ Yes (with digits) ]", callback_data=f"digits:yes:{length}"),
            InlineKeyboardButton(text="[ No (letters/_) ]", callback_data=f"digits:no:{length}")
        ],
        [InlineKeyboardButton(text="‹ Back", callback_data="menu:auto")]
    ])

def digits_count_keyboard(length: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    max_d = min(3, length - 1)
    for d in range(1, max_d + 1):
        row.append(InlineKeyboardButton(text=f"[{d} digit(s)]", callback_data=f"dcount:{length}:{d}"))
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="‹ Back", callback_data=f"len:{length}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def check_single_username(session: aiohttp.ClientSession, username: str) -> bool:
    username = username.lstrip("@").strip()
    if not USERNAME_PATTERN.match(username):
        return False
    url = f"https://t.me/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return False
            text = await resp.text()
            
            if "is available on Telegram" in text or "you can set up" in text or "username is not taken" in text:
                return True
                
            if "tgme_page" in text and "tgme_page_photo" not in text and "tgme_page_additional" not in text:
                if "is available" in text or not "tgme_page_title" in text:
                    return True
                    
            return False
    except Exception:
        return False

async def generate_and_find_free(message_to_edit, prefix: str = "", suffix: str = "", target_length: int = 6, use_digits: bool = True, digits_count: int = 1, count: int = 1) -> list:
    free_found = []
    attempts = 0
    max_attempts = 100
    
    steps = [
        ("┌ [ ⌬ ] connecting to t.me gateway...", 20),
        ("├ [ ⌕ ] bypassing filters & scanning...", 50),
        ("├ [ ↻ ] cross-checking availability...", 80),
        ("└ [ ✓ ] target acquired!", 100),
    ]

    step_index = 0
    timeout = aiohttp.ClientTimeout(total=2)
    
    letters = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"
    symbols_no_digits = "abcdefghijklmnopqrstuvwxyz_"
    symbols_with_digits = "abcdefghijklmnopqrstuvwxyz0123456789_"

    async with aiohttp.ClientSession(timeout=timeout) as session:
        while len(free_found) < count and attempts < max_attempts:
            attempts += 1
            
            if attempts % 25 == 0 and step_index < len(steps):
                try:
                    text, _ = steps[step_index]
                    await message_to_edit.edit_text(text, parse_mode="HTML")
                    step_index += 1
                except Exception:
                    pass

            if prefix or suffix:
                fixed_len = len(prefix) + len(suffix)
                if fixed_len >= target_length:
                    candidate = f"{prefix}{suffix}"[:target_length]
                else:
                    rand_len = target_length - fixed_len
                    pool = symbols_with_digits if use_digits else symbols_no_digits
                    rand_part = "".join(random.choice(pool) for _ in range(rand_len))
                    candidate = f"{prefix}{rand_part}{suffix}"
            else:
                first_char = random.choice(letters)
                if use_digits and digits_count > 0:
                    rest_len = target_length - 1
                    chosen_digits_count = min(digits_count, rest_len)
                    chosen_letters_count = rest_len - chosen_digits_count
                    
                    r_letters = "".join(random.choice(symbols_no_digits) for _ in range(chosen_letters_count))
                    r_digits = "".join(random.choice(digits) for _ in range(chosen_digits_count))
                    
                    rest_pool = list(r_letters + r_digits)
                    random.shuffle(rest_pool)
                    candidate = first_char + "".join(rest_pool)
                else:
                    rest_len = target_length - 1
                    rest_part = "".join(random.choice(symbols_no_digits) for _ in range(rest_len))
                    candidate = first_char + rest_part

            if len(candidate) != target_length:
                continue
            if not USERNAME_PATTERN.match(candidate):
                continue
            if f"@{candidate}" in free_found:
                continue
                
            if await check_single_username(session, candidate):
                free_found.append(f"@{candidate}")
                
            await asyncio.sleep(0.02)
            
    return free_found

def format_result_card(username: str) -> str:
    clean = username.lstrip("@")
    length = len(clean)
    
    readability = max(4, min(10, 11 - length))
    if "_" in clean or any(c.isdigit() for c in clean):
        readability = max(4, readability - 2)
        
    if length <= 5:
        price = "$15 - $30"
    elif length == 6:
        price = "$10 - $25"
    else:
        price = "$3 - $10"
        
    liquidity = max(4, min(9, readability - 1))
    
    return (
        f"┌─[ ☑ STATUS: AVAILABLE ]\n"
        f"│\n"
        f"├ target: <code>{username}</code> (tap to copy)\n"
        f"├ length: {length} chars\n"
        f"├ readability: {readability}/10\n"
        f"├ est. value: {price}\n"
        f"├ liquidity: {liquidity}/10\n"
        f"└ status: [ • FREE ]\n\n"
        f"◇ Powered by @tagtrack_core_bot"
    )

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    name = html.escape(message.from_user.first_name)
    text = (
        f"┌─[ ⌬ TAG TRACK SYSTEM v2.0 ]\n"
        f"│\n"
        f"├ welcome back, {name}!\n"
        f"├ status: [ 🟢 ONLINE ]\n"
        f"└ select an option below:"
    )
    await message.answer(text, reply_markup=main_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("menu:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    profile = get_user_profile(user_id)
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = (
            f"┌─[ ϟ TAG TRACK SYSTEM v2.0 ]\n"
            f"│\n"
            f"├ welcome back, {name}!\n"
            f"├ status: [ 🟢 ONLINE ]\n"
            f"└ select an option below:"
        )
        await callback.message.edit_text(text, reply_markup=main_keyboard(), parse_mode="HTML")
        
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        text = "┌─[ ϟ AUTO-SEARCH MODULE ]\n└ select exact length (5-11):"
        await callback.message.edit_text(text, reply_markup=length_keyboard(), parse_mode="HTML")
        
    elif action == "prefix":
        await state.set_state(BotStates.prefix_search)
        text = "┌─[ ⎋ PREFIX / SUFFIX MODULE ]\n└ enter custom prefix:"
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "smart":
        await state.set_state(BotStates.smart_variations)
        text = "┌─[ 💡 SMART VARIATIONS ]\n└ enter base name:"
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "profile":
        saved_count = len(profile["saved"])
        history_count = len(profile["history"])
        
        text = (
            f"┌─[ 📁 USER DASHBOARD ]\n"
            f"│\n"
            f"├ id: <code>{user_id}</code>\n"
            f"├ total checks: {profile['checks_count']}\n"
            f"├ saved tags: {saved_count}\n"
            f"└ history items: {history_count}"
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="[ 📂 Saved ]", callback_data="menu:view_saved"),
                InlineKeyboardButton(text="[ 📜 History ]", callback_data="menu:view_history")
            ],
            [InlineKeyboardButton(text="‹ Back", callback_data="menu:main")]
        ])
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        
    elif action == "view_saved":
        saved = profile["saved"]
        if not saved:
            text = "┌─[ 📂 SAVED TAGS ]\n└ folder is empty."
        else:
            items = [f"├ <code>{u}</code>" for u in saved]
            text = "┌─[ 📂 SAVED TAGS ]\n│\n" + "\n".join(items) + "\n└ —"
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "view_history":
        history = profile["history"]
        if not history:
            text = "┌─[ 📜 HISTORY ]\n└ no recent checks."
        else:
            items = [f"├ <code>{u}</code>" for u in history[:10]]
            text = "┌─[ 📜 RECENT HISTORY ]\n│\n" + "\n".join(items) + "\n└ —"
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "help":
        text = (
            f"┌─[ ⓘ SYSTEM GUIDE ]\n"
            f"│\n"
            f"├ select length or prefix\n"
            f"├ click tags to copy instantly\n"
            f"└ save cool finds to your profile\n"
            f"└ —"
        )
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    await callback.answer()

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    text = f"┌─[ ⚡ AUTO-SEARCH ]\n├ length: {length} chars\n└ include digits (0-9)?"
    await callback.message.edit_text(text, reply_markup=digits_choice_keyboard(length), parse_mode="HTML")

@dp.callback_query(F.data.startswith("digits:"))
async def digits_choice_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    choice = parts[1]
    length = int(parts[2])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    if choice == "yes":
        text = f"┌─[ ↻ AUTO-SEARCH ]\n├ length: {length} chars\n└ select digits count (1-3):"
        await callback.message.edit_text(text, reply_markup=digits_count_keyboard(length), parse_mode="HTML")
    else:
        msg = await callback.message.edit_text(f"┌ [ ⌬ ] scanning {length}-char tag (no digits)...", parse_mode="HTML")
        results = await generate_and_find_free(message_to_edit=msg, target_length=length, use_digits=False, count=1)
        
        profile["checks_count"] += 1
        add_to_history(user_id, results)
        
        if not results:
            err_text = "┌─[ ❌ ERROR ]\n└ no free tags found, try again."
            await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
            return

        username = results[0]
        clean_u = username.lstrip('@')
        text = format_result_card(username)
        
        buttons = [
            [
                InlineKeyboardButton(text="[ ↗ Open Link ]", url=f"https://t.me/{clean_u}"),
                InlineKeyboardButton(text="[ ★ Save Tag ]", callback_data=f"save:{clean_u}")
            ],
            [
                InlineKeyboardButton(text="[ ↻ Generate Another ]", callback_data=f"len:{length}")
            ],
            [InlineKeyboardButton(text="‹ Main Menu", callback_data="menu:main")]
        ]
        
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("dcount:"))
async def digits_count_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    length = int(parts[1])
    d_count = int(parts[2])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    msg = await callback.message.edit_text(f"┌ [ ϟ ] scanning {length}-char tag with {d_count} digit(s)...", parse_mode="HTML")
    results = await generate_and_find_free(message_to_edit=msg, target_length=length, use_digits=True, digits_count=d_count, count=1)
    
    profile["checks_count"] += 1
    add_to_history(user_id, results)
    
    if not results:
        err_text = "┌─[ ❌ ERROR ]\n└ no free tags found with these parameters."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return

    username = results[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="[ ↗ Open Link ]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[ ★ Save Tag ]", callback_data=f"save:{clean_u}")
        ],
        [
            InlineKeyboardButton(text="[ 🔄 Generate Another ]", callback_data=f"len:{length}")
        ],
        [InlineKeyboardButton(text="‹ Main Menu", callback_data="menu:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("save:"))
async def save_username_callback(callback: CallbackQuery):
    raw_uname = callback.data.split(":", 1)[1]
    uname = f"@{raw_uname.lstrip('@')}"
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    if uname not in profile["saved"]:
        profile["saved"].append(uname)
        await callback.answer(f"Successfully saved: {uname}", show_alert=True)
    else:
        await callback.answer("Already in your saved list!", show_alert=True)

@dp.message(BotStates.prefix_search)
async def process_prefix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prefix = message.text.strip().lstrip("@")
    await state.clear()
    
    target_len = max(5, len(prefix) + 2)
    if target_len > 32:
        target_len = 32
        
    profile = get_user_profile(user_id)
    msg = await message.answer("┌ [ ϟ ] searching with prefix...", parse_mode="HTML")
    results = await generate_and_find_free(message_to_edit=msg, prefix=prefix, target_length=target_len, use_digits=True, digits_count=1, count=1)
    
    profile["checks_count"] += 1
    add_to_history(user_id, results)
    
    if not results:
        err_text = "┌─[ ❌ ERROR ]\n└ nothing found with this prefix."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return
        
    username = results[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="[ ↗ Open Link ]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[ ★ Save Tag ]", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="‹ Main Menu", callback_data="menu:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(BotStates.smart_variations)
async def process_smart_variations(message: Message, state: FSMContext):
    user_id = message.from_user.id
    base = message.text.strip().lstrip("@")
    await state.clear()
    
    profile = get_user_profile(user_id)
    msg = await message.answer("┌ [ ϟ ] analyzing smart variations...", parse_mode="HTML")
    
    raw_variations = [f"the_{base}", f"{base}x", f"real_{base}", f"{base}hq", f"{base}_dev", f"{base}_tg", f"{base}_1", f"01_{base}"]
    variations = []
    for v in raw_variations:
        if len(v) < 5:
            v = v + "x" * (5 - len(v))
        if len(v) <= 32 and v not in variations:
            variations.append(v)
    
    free_found = []
    timeout = aiohttp.ClientTimeout(total=2)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for var in variations:
            if USERNAME_PATTERN.match(var) and await check_single_username(session, var):
                free_found.append(f"@{var}")
                break
                
    profile["checks_count"] += 1
    add_to_history(user_id, free_found)
            
    if not free_found:
        err_text = "┌─[ ❌ ERROR ]\n└ no free variations for this name."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return
        
    username = free_found[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="[ ↗ Open Link ]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[ ★ Save Tag ]", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="‹ Main Menu", callback_data="menu:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.s
