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
global_checked_usernames = set()

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "en",
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

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    
    if lang == "ua":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Авто-пошук", callback_data="menu:auto"),
                InlineKeyboardButton(text="⚙️ Префікс / Суфікс", callback_data="menu:prefix"),
            ],
            [
                InlineKeyboardButton(text="💡 Розумні варіації", callback_data="menu:smart"),
                InlineKeyboardButton(text="📁 Профіль та Збережені", callback_data="menu:profile"),
            ],
            [
                InlineKeyboardButton(text="🌐 Мова", callback_data="menu:settings"),
                InlineKeyboardButton(text="ℹ️ Довідка", callback_data="menu:help"),
            ]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡ Auto-Search", callback_data="menu:auto"),
                InlineKeyboardButton(text="⚙️ Prefix / Suffix", callback_data="menu:prefix"),
            ],
            [
                InlineKeyboardButton(text="💡 Smart Variations", callback_data="menu:smart"),
                InlineKeyboardButton(text="📁 Profile & Saved", callback_data="menu:profile"),
            ],
            [
                InlineKeyboardButton(text="🌐 Language", callback_data="menu:settings"),
                InlineKeyboardButton(text="ℹ️ Help", callback_data="menu:help"),
            ]
        ])

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(user_id)
    text = "‹ Назад" if profile.get("lang") == "ua" else "‹ Back"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data="menu:main")]])

def length_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 12):
        row.append(InlineKeyboardButton(text=f"[{length}]", callback_data=f"len:{length}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    profile = get_user_profile(user_id)
    back_text = "‹ Назад" if profile.get("lang") == "ua" else "‹ Back"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def check_single_username(session: aiohttp.ClientSession, username: str) -> bool | None:
    username = username.lstrip("@").strip()
    if not USERNAME_PATTERN.match(username):
        return None
    url = f"https://t.me/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return None
            text = await resp.text()
            
            if "tgme_action_button_new" in text or "If you have Telegram" in text or "View in Telegram" in text:
                return False
            
            if "tgme_page_extra" in text or "tgme_page_title" in text:
                if "is available on Telegram" in text or "you can set up" in text:
                    return True
                return False

            if "is available on Telegram" in text or "you can set up" in text or "username is not taken" in text:
                return True
                
            if "tgme_page" in text and "tgme_page_photo" not in text and "tgme_page_additional" not in text:
                return True
                
            return False
    except Exception:
        return None

async def generate_and_find_free(message_to_edit, lang: str, prefix: str = "", suffix: str = "", length: int = 5, count: int = 1) -> list:
    chars_letters = "abcdefghijklmnopqrstuvwxyz"
    free_found = []
    attempts = 0
    max_attempts = 150  # Обмежуємо для надшвидкого пошуку (до 30-40 секунд)
    
    if lang == "ua":
        steps = [
            ("┌ [ ⋯ ] ініціалізація пошуку... 25%", 25),
            ("├ [ ≡ ] сканування баз даних... 50%", 50),
            ("├ [ ⟳ ] перевірка статусів... 75%", 75),
            ("└ [ ✓ ] завершення... 95%", 95),
        ]
    else:
        steps = [
            ("┌ [ ⋯ ] initializing search... 25%", 25),
            ("├ [ ≡ ] scanning databases... 50%", 50),
            ("├ [ ⟳ ] checking statuses... 75%", 75),
            ("└ [ ✓ ] finalizing... 95%", 95),
        ]

    step_index = 0
    timeout = aiohttp.ClientTimeout(total=1.5)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while len(free_found) < count and attempts < max_attempts:
            attempts += 1
            
            if attempts % 35 == 0 and step_index < len(steps):
                try:
                    text, _ = steps[step_index]
                    await message_to_edit.edit_text(text, parse_mode="HTML")
                    step_index += 1
                except Exception:
                    pass

            needed_len = max(2, length - len(prefix) - len(suffix))
            
            if needed_len >= 4:
                rand_letters = "".join(random.choice(chars_letters) for _ in range(max(1, needed_len - 2)))
                rand_tail = random.choice(["_1", "_99", "x", "77", "_tg", "01", "_pro", "s", "io"])
                random_part = (rand_letters + rand_tail)[:needed_len]
            else:
                chars_all = "abcdefghijklmnopqrstuvwxyz0123456789_"
                random_part = "".join(random.choice(chars_all) for _ in range(needed_len))
                
            candidate = f"{prefix}{random_part}{suffix}".lower()
            if not candidate[0].isalpha():
                candidate = "a" + candidate[1:]
                
            if candidate in global_checked_usernames:
                continue
            global_checked_usernames.add(candidate)
            
            is_free = await check_single_username(session, candidate)
            if is_free is True:
                free_found.append(f"@{candidate}")
                
    return free_found

def format_result_card(username: str, lang: str) -> str:
    clean = username.lstrip("@")
    length = len(clean)
    
    readability = max(3, min(10, 11 - length))
    if "_" in clean or any(c.isdigit() for c in clean):
        readability = max(3, readability - 2)
        
    if length <= 5:
        price = "$25 - $60"
    elif length == 6:
        price = "$10 - $25"
    else:
        price = "$3 - $10"
        
    liquidity = max(3, min(9, readability - 1))
    
    if lang == "ua":
        return (
            f"┌─[ status: found ]\n"
            f"│\n"
            f"├ target: <code>{username}</code>\n"
            f"├ читабельність: {readability}/10\n"
            f"├ прибл. ціна: {price}\n"
            f"├ ліквідність: {liquidity}/10\n"
            f"└ стан: [ вільний ]\n\n"
            f"◇ @thetagtrackbot"
        )
    else:
        return (
            f"┌─[ status: found ]\n"
            f"│\n"
            f"├ target: <code>{username}</code>\n"
            f"├ readability: {readability}/10\n"
            f"├ approximate price: {price}\n"
            f"├ liquidity: {liquidity}/10\n"
            f"└ status: [ free ]\n\n"
            f"◇ @thetagtrackbot"
        )

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    profile = get_user_profile(user_id)
    name = html.escape(message.from_user.first_name)
    
    if profile["lang"] == "ua":
        text = f"┌─[ tag track system ]\n│\n├ вітаю, {name}!\n└ оберіть дію нижче:"
    else:
        text = f"┌─[ tag track system ]\n│\n├ welcome, {name}!\n└ choose an action below:"
        
    await message.answer(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")

@dp.callback_query(F.data.startswith("menu:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    profile = get_user_profile(user_id)
    lang = profile["lang"]
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = f"┌─[ tag track system ]\n│\n├ welcome, {name}!\n└ choose an action below:" if lang == "en" else f"┌─[ tag track system ]\n│\n├ вітаю, {name}!\n└ оберіть дію нижче:"
        await callback.message.edit_text(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
        
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        text = "┌─[ auto-search ]\n└ оберіть довжину (5-11):" if lang == "ua" else "┌─[ auto-search ]\n└ select length (5-11):"
        await callback.message.edit_text(text, reply_markup=length_keyboard(user_id), parse_mode="HTML")
        
    elif action == "prefix":
        await state.set_state(BotStates.prefix_search)
        text = "┌─[ prefix / suffix ]\n└ введіть текст:" if lang == "ua" else "┌─[ prefix / suffix ]\n└ enter text:"
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    elif action == "smart":
        await state.set_state(BotStates.smart_variations)
        text = "┌─[ smart variations ]\n└ введіть базове ім'я:" if lang == "ua" else "┌─[ smart variations ]\n└ enter base name:"
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    elif action == "profile":
        saved_count = len(profile["saved"])
        history_count = len(profile["history"])
        
        if lang == "ua":
            text = (
                f"┌─[ профіль користувача ]\n"
                f"│\n"
                f"├ id: <code>{user_id}</code>\n"
                f"├ перевірок: {profile['checks_count']}\n"
                f"├ збережено: {saved_count}\n"
                f"└ історія: {history_count}"
            )
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="[ збережені ]", callback_data="menu:view_saved"),
                    InlineKeyboardButton(text="[ історія ]", callback_data="menu:view_history")
                ],
                [InlineKeyboardButton(text="‹ назад", callback_data="menu:main")]
            ])
        else:
            text = (
                f"┌─[ user profile ]\n"
                f"│\n"
                f"├ id: <code>{user_id}</code>\n"
                f"├ checks: {profile['checks_count']}\n"
                f"├ saved: {saved_count}\n"
                f"└ history: {history_count}"
            )
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="[ saved ]", callback_data="menu:view_saved"),
                    InlineKeyboardButton(text="[ history ]", callback_data="menu:view_history")
                ],
                [InlineKeyboardButton(text="‹ back", callback_data="menu:main")]
            ])
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        
    elif action == "view_saved":
        saved = profile["saved"]
        if not saved:
            text = "┌─[ saved ]\n└ порожньо." if lang == "ua" else "┌─[ saved ]\n└ empty."
        else:
            items = [f"├ <code>{u}</code>" for u in saved]
            text = "┌─[ saved tags ]\n│\n" + "\n".join(items) + "\n└ —"
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    elif action == "view_history":
        history = profile["history"]
        if not history:
            text = "┌─[ history ]\n└ порожньо." if lang == "ua" else "┌─[ history ]\n└ empty."
        else:
            items = [f"├ <code>{u}</code>" for u in history[:10]]
            text = "┌─[ recent history ]\n│\n" + "\n".join(items) + "\n└ —"
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    elif action == "settings":
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="[ en ]", callback_data="setlang:en"),
                InlineKeyboardButton(text="[ ua ]", callback_data="setlang:ua"),
            ],
            [InlineKeyboardButton(text="‹ back", callback_data="menu:main")]
        ])
        await callback.message.edit_text("┌─[ language ]\n└ оберіть мову / select language:", reply_markup=markup, parse_mode="HTML")
        
    elif action == "help":
        text = "┌─[ help ]\n└ використовуйте авто-пошук або префікси для пошуку вільних тегів." if lang == "ua" else "┌─[ help ]\n└ use auto-search or prefixes to find available tags."
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    await callback.answer()

@dp.callback_query(F.data.startswith("setlang:"))
async def set_lang_callback(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    get_user_profile(user_id)["lang"] = lang
    
    text = "┌─[ language ]\n└ збережено!" if lang == "ua" else "┌─[ language ]\n└ saved!"
    await callback.message.edit_text(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    
    msg = await callback.message.edit_text("┌ [ ⋯ ] ініціалізація...", parse_mode="HTML")
    results = await generate_and_find_free(message_to_edit=msg, lang=lang, length=length, count=1)
    
    profile["checks_count"] += len(results)
    add_to_history(user_id, results)
    
    if not results:
        err_text = "┌─[ error ]\n└ вільних тегів не знайдено." if lang == "ua" else "┌─[ error ]\n└ no free tags found."
        await msg.edit_text(err_text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return

    username = results[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username, lang)
    
    buttons = [
        [
            InlineKeyboardButton(text="[ ↗ відкрити ]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[ ★ зберегти ]", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="‹ назад", callback_data="menu:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("save:"))
async def save_username_callback(callback: CallbackQuery):
    raw_uname = callback.data.split(":", 1)[1]
    uname = f"@{raw_uname.lstrip('@')}"
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    
    if uname not in profile["saved"]:
        profile["saved"].append(uname)
        msg_text = f"збережено: {uname}" if lang == "ua" else f"saved: {uname}"
        await callback.answer(msg_text, show_alert=True)
    else:
        msg_text = "вже в збережених" if lang == "ua" else "already saved"
        await callback.answer(msg_text, show_alert=True)

@dp.message(BotStates.prefix_search)
async def process_prefix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prefix = message.text.strip().lstrip("@")
    await state.clear()
    
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    
    msg = await message.answer("┌ [ ⋯ ] ініціалізація...", parse_mode="HTML")
    results = await generate_and_find_free(message_to_edit=msg, lang=lang, prefix=prefix, length=len(prefix) + 3, count=1)
    
    profile["checks_count"] += len(results)
    add_to_history(user_id, results)
    
    if not results:
        err_text = "┌─[ error ]\n└ нічого не знайдено." if lang == "ua" else "┌─[ error ]\n└ nothing found."
        await msg.edit_text(err_text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    username = results[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username, lang)
    
    buttons = [
        [
            InlineKeyboardButton(text="[ ↗ відкрити ]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[ ★ зберегти ]", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="‹ назад", callback_data="menu:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(BotStates.smart_variations)
async def process_smart_variations(message: Message, state: FSMContext):
    user_id = message.from_user.id
    base = message.text.strip().lstrip("@")
    await state.clear()
    
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    
    msg = await message.answer("┌ [ ⋯ ] аналіз варіацій...", parse_mode="HTML")
    variations = [f"the_{base}", f"{base}x", f"real_{base}", f"{base}hq", f"{base}_dev", f"{base}_tg", f"{base}_1", f"01_{base}"]
    
    free_found = []
    timeout = aiohttp.ClientTimeout(total=1.5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for var in variations:
            if await check_single_username(session, var):
                free_found.append(f"@{var}")
                break
                
    profile["checks_count"] += len(free_found)
    add_to_history(user_id, free_found)
            
    if not free_found:
        err_text = "┌─[ error ]\n└ вільних варіацій немає." if lang == "ua" else "┌─[ error ]\n└ no free variations."
        await msg.edit_text(err_text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    username = free_found[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username, lang)
    
    buttons = [
        [
            InlineKeyboardButton(text="[ ↗ відкрити ]", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="[ ★ зберегти ]", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="‹ назад", callback_data="menu:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
