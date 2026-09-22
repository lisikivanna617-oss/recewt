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

USERNAME_PATTERN = re.compile(f"^[A-Za-z][A-Za-z0-9_]{{4,31}}$")

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
            InlineKeyboardButton(text="‹ø› SCAN: AUTO", callback_data="nx:auto"),
            InlineKeyboardButton(text="‹ø› SCAN: PREFIX", callback_data="nx:prefix"),
        ],
        [
            InlineKeyboardButton(text="‹ø› MUTATE: SMART", callback_data="nx:smart"),
            InlineKeyboardButton(text="‹ø› VAULT: PROFILE", callback_data="nx:profile"),
        ],
        [
            InlineKeyboardButton(text="‹ø› MANIFEST: HELP", callback_data="nx:help"),
        ]
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« ABORT / RETURN", callback_data="nx:main")]])

def length_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 12):
        row.append(InlineKeyboardButton(text=f"[{length}L]", callback_data=f"len:{length}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="« ABORT / RETURN", callback_data="nx:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def digits_choice_keyboard(length: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="[+] WITH DIGITS", callback_data=f"dig:1:{length}"),
            InlineKeyboardButton(text="[-] LETTERS ONLY", callback_data=f"dig:0:{length}")
        ],
        [InlineKeyboardButton(text="« ABORT / RETURN", callback_data="nx:auto")]
    ])

def digits_count_keyboard(length: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    max_d = min(3, length - 1)
    for d in range(1, max_d + 1):
        row.append(InlineKeyboardButton(text=f"[{d} DIG]", callback_data=f"dc:{length}:{d}"))
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="« ABORT / RETURN", callback_data=f"len:{length}")])
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
        ("SYSTEM_LOG // INIT_SOCKET...", 20),
        ("SYSTEM_LOG // BYPASSING_FILTERS...", 50),
        ("SYSTEM_LOG // PROBING_NODES...", 80),
        ("SYSTEM_LOG // TARGET_LOCKED.", 100),
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
                    text = f"[#] {steps[step_index][0]}"
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
        tier = "ALPHA_TIER"
    elif length == 6:
        tier = "BETA_TIER"
    else:
        tier = "STANDARD_TIER"
        
    return (
        f"=== NODE_REPORT ===\n"
        f"[§] TARGET: <code>{username}</code>\n"
        f"[§] LENGTH: {length} bytes\n"
        f"[§] INDEX: {readability}/10\n"
        f"[§] CLASS: {tier}\n"
        f"[§] STATE: [UNCLAIMED]\n"
        f"==================="
    )

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    name = html.escape(message.from_user.first_name)
    text = (
        f"// SESSION_ACTIVE //\n"
        f"OPERATOR: {name}\n"
        f"HOST: SECURE_CORE_v9\n"
        f"---------------------\n"
        f"CHOOSE EXECUTION VECTOR:"
    )
    await message.answer(text, reply_markup=main_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("nx:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    profile = get_user_profile(user_id)
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = (
            f"// SESSION_ACTIVE //\n"
            f"OPERATOR: {name}\n"
            f"HOST: SECURE_CORE_v9\n"
            f"---------------------\n"
            f"CHOOSE EXECUTION VECTOR:"
        )
        await callback.message.edit_text(text, reply_markup=main_keyboard(), parse_mode="HTML")
        
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        text = ">> PROTOCOL: AUTO_SCAN\n[?] SELECT BYTE LENGTH (5-11):"
        await callback.message.edit_text(text, reply_markup=length_keyboard(), parse_mode="HTML")
        
    elif action == "prefix":
        await state.set_state(BotStates.prefix_search)
        text = ">> PROTOCOL: PREFIX_SCAN\n[?] INPUT STRING ANCHOR:"
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "smart":
        await state.set_state(BotStates.smart_variations)
        text = ">> PROTOCOL: SMART_MUTATE\n[?] INPUT BASE SEED:"
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "profile":
        saved_count = len(profile["saved"])
        history_count = len(profile["history"])
        
        text = (
            f"=== USER_VAULT ===\n"
            f"UID: {user_id}\n"
            f"QUERIES_RUN: {profile['checks_count']}\n"
            f"CACHED_ITEMS: {saved_count}\n"
            f"LOG_ENTRIES: {history_count}\n"
            f"=================="
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="[VIEW VAULT]", callback_data="nx:view_saved"),
                InlineKeyboardButton(text="[VIEW LOGS]", callback_data="nx:view_history")
            ],
            [InlineKeyboardButton(text="« ABORT / RETURN", callback_data="nx:main")]
        ])
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        
    elif action == "view_saved":
        saved = profile["saved"]
        if not saved:
            text = "=== VAULT ===\nSTATUS: EMPTY BUFFER."
        else:
            items = [f" > <code>{u}</code>" for u in saved]
            text = "=== STORED_ITEMS ===\n" + "\n".join(items)
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "view_history":
        history = profile["history"]
        if not history:
            text = "=== LOGS ===\nSTATUS: NO RECENT ACTIVITY."
        else:
            items = [f" ~ <code>{u}</code>" for u in history[:10]]
            text = "=== RECENT_LOGS ===\n" + "\n".join(items)
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "help":
        text = (
            "=== MANIFEST ===\n"
            "1. SELECT SCAN PARAMETERS\n"
            "2. EXECUTE THREAD POOL\n"
            "3. EXPORT TARGETS TO VAULT\n"
            "=================="
        )
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    await callback.answer()

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    text = f">> LENGTH_LOCKED: {length}\n[?] ALLOW NUMERIC DIGITS?"
    await callback.message.edit_text(text, reply_markup=digits_choice_keyboard(length), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dig:"))
async def digits_choice_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    use_dig = int(parts[1])
    length = int(parts[2])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    if use_dig == 1:
        text = f">> CONFIG: {length}L + DIGITS\n[?] SELECT DIGIT DENSITY (1-3):"
        await callback.message.edit_text(text, reply_markup=digits_count_keyboard(length), parse_mode="HTML")
    else:
        msg = await callback.message.edit_text(f"[#] INITIALIZING {length}L PURE-STRING SCAN...", parse_mode="HTML")
        results = await generate_and_find_free(message_to_edit=msg, target_length=length, use_digits=False, count=1)
        
        profile["checks_count"] += 1
        add_to_history(user_id, results)
        
        if not results:
            err_text = "=== ERROR ===\n[!] TIMEOUT: NO FREE NODES FOUND."
            await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
            return

        username = results[0]
        clean_u = username.lstrip('@')
        text = format_result_card(username)
        
        buttons = [
            [
                InlineKeyboardButton(text="[EXTERNAL LINK]", url=f"https://t.me/{clean_u}"),
                InlineKeyboardButton(text="[SAVE TO VAULT]", callback_data=f"save:{clean_u}")
            ],
            [
                InlineKeyboardButton(text="[RE-SCAN SAME]", callback_data=f"len:{length}")
            ],
            [InlineKeyboardButton(text="« ROOT MENU", callback_data="nx:main")]
        ]
        
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("dc:"))
async def digits_count_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    length = int(parts[1])
    d_count = int(parts[2])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    msg = await callback.message.edit_text(f"[#] SCANNING {length}L WITH {d_count} DIGIT(S)...", parse_mode="HTML")
    results = await generate_and_find_free(message_to_edit=msg, target_length=length, use_digits=True, digits_count=d_count, count=1)
    
    profile["checks_count"] += 1
    add_to_history(user_id, results)
    
    if not results:
        err_text = "=== ERROR ===\n[!] TIMEOUT: NO MATCHING NODES FOUND."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return

    username = results[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="[EXTERNAL LINK]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[SAVE TO VAULT]", callback_data=f"save:{clean_u}")
        ],
        [
            InlineKeyboardButton(text="[RE-SCAN SAME]", callback_data=f"len:{length}")
        ],
        [InlineKeyboardButton(text="« ROOT MENU", callback_data="nx:main")]
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
        await callback.answer(f"VAULT UPDATED: {uname}", show_alert=True)
    else:
        await callback.answer("TARGET ALREADY STORED.", show_alert=True)

@dp.message(BotStates.prefix_search)
async def process_prefix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prefix = message.text.strip().lstrip("@")
    await state.clear()
    
    target_len = max(5, len(prefix) + 2)
    if target_len > 32:
        target_len = 32
        
    profile = get_user_profile(user_id)
    msg = await message.answer(f"[#] COMPILING PREFIX ANCHOR: {prefix}...", parse_mode="HTML")
    results = await generate_and_find_free(message_to_edit=msg, prefix=prefix, target_length=target_len, use_digits=True, digits_count=1, count=1)
    
    profile["checks_count"] += 1
    add_to_history(user_id, results)
    
    if not results:
        err_text = "=== ERROR ===\n[!] ANCHOR RESOLUTION FAILED."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return
        
    username = results[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="[EXTERNAL LINK]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[SAVE TO VAULT]", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="« ROOT MENU", callback_data="nx:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(BotStates.smart_variations)
async def process_smart_variations(message: Message, state: FSMContext):
    user_id = message.from_user.id
    base = message.text.strip().lstrip("@")
    await state.clear()
    
    profile = get_user_profile(user_id)
    msg = await message.answer(f"[#] MUTATING SEED: {base}...", parse_mode="HTML")
    
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
        err_text = "=== ERROR ===\n[!] NO MUTATIONS AVAILABLE."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return
        
    username = free_found[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="[EXTERNAL LINK]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[SAVE TO VAULT]", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="« ROOT MENU", callback_data="nx:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                    
