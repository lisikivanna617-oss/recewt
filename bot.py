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
            "lang": "en",
        }
    return user_data_store[user_id]

def add_to_history(user_id: int, usernames: list):
    profile = get_user_profile(user_id)
    for u in usernames:
        if u not in profile["history"]:
            profile["history"].insert(0, u)
    profile["history"] = profile["history"][:20]

LANGS = {
    "en": {
        "welcome": "<b>Welcome, {name}</b>\n\nChoose the required section from the menu below:",
        "btn_auto": "ϟ Auto Search",
        "btn_prefix": "⌕ Prefix / Suffix",
        "btn_smart": "⎈ Smart Variations",
        "btn_profile": "ⓘ Profile & Settings",
        "btn_help": "✪ Help & Instructions",
        "back": "⎋ Go Back",
        "main_menu": "⎋ Main Menu",
        "auto_title": "ϟ <b>Auto Search</b>\n\nChoose desired username length (5 to 11 characters):",
        "prefix_title": "⌕ <b>Prefix Search</b>\n\nEnter the text or part of the name to start with:",
        "smart_title": "⎈ <b>Smart Variations</b>\n\nEnter a base word to generate unique combinations:",
        "profile_title": "ⓘ <b>Personal Profile</b>\n\n⏣ User ID: <code>{user_id}</code>\n⏣ Total checks: {checks}\n⏣ Saved tags: {saved_cnt}\n⏣ History items: {hist_cnt}\n⏣ Language: English",
        "btn_saved": "☆ Saved Tags",
        "btn_history": "⏱ History",
        "btn_lang": "⏣ Language: English",
        "saved_empty": "☆ <b>Saved Tags</b>\n\nYour saved list is empty.",
        "saved_title": "☆ <b>Saved Tags</b>\n\n",
        "history_empty": "⏱ <b>Search History</b>\n\nYour history is empty.",
        "history_title": "⏱ <b>Search History</b>\n\n",
        "help_text": "✪ <b>Help & Instructions</b>\n\n1. Select a mode in the main menu.\n2. Specify parameters or enter a keyword.\n3. Get a free username and save it to your profile.",
        "len_prompt": "ϟ <b>Auto Search</b>\n\nSelected length: {length} characters.\nDo you want to include digits?",
        "digits_yes": "☑ With Digits",
        "digits_no": "☒ Letters Only",
        "dcount_prompt": "ϟ <b>Auto Search</b>\n\nLength: {length} characters.\nHow many digits to include?",
        "scan_nodig": "⌕ Scanning {length}-char username (no digits)...",
        "scan_dig": "⌕ Scanning username ({length} chars, {d_count} digits)...",
        "scan_prefix": "⌕ Searching for prefix «{prefix}»...",
        "scan_smart": "⎈ Generating variations for «{base}»...",
        "err_not_found": "⚠ <b>Error</b>\n\nNo free usernames found with these parameters.",
        "err_prefix": "⚠ <b>Error</b>\n\nNothing found with this prefix.",
        "err_smart": "⚠ <b>Error</b>\n\nCould not find free variations for this word.",
        "res_title": "🜲 <b>SEARCH RESULT</b>\n\n◌ Username: <code>{username}</code>\n◌ Length: {length} characters\n◌ Readability: {readability} / 10\n◌ Category: {category}\n◌ Status: Available for registration\n",
        "cat_prem": "Premium",
        "cat_std": "Standard",
        "cat_reg": "Regular",
        "btn_open": "↗ Open Link",
        "btn_save": "☆ Save",
        "btn_retry": "↻ Try Again",
        "saved_success": "• Successfully saved: {uname}",
        "saved_already": "• This item is already in your saved list.",
        "lang_changed": "• Language changed to English."
    },
    "uk": {
        "welcome": "<b>Вітаю, {name}</b>\n\nОберіть необхідний розділ за допомогою меню нижче:",
        "btn_auto": "ϟ Автоматичний пошук",
        "btn_prefix": "⌕ Префікс / Суфікс",
        "btn_smart": "⎈ Розумні варіації",
        "btn_profile": "ⓘ Профіль та налаштування",
        "btn_help": "✪ Довідка та інструкція",
        "back": "⎋ Повернутися назад",
        "main_menu": "⎋ Головне меню",
        "auto_title": "ϟ <b>Автоматичний пошук</b>\n\nОберіть бажану довжину імені (від 5 до 11 символів):",
        "prefix_title": "⌕ <b>Пошук за префіксом</b>\n\nВведіть текст або частину імені, з якої має починатися результат:",
        "smart_title": "⎈ <b>Розумні варіації</b>\n\nВведіть базове слово для генерації унікальних комбінацій:",
        "profile_title": "ⓘ <b>Особистий профіль</b>\n\n⏣ ID користувача: <code>{user_id}</code>\n⏣ Загалом перевірок: {checks}\n⏣ Збережено імен: {saved_cnt}\n⏣ Історія запитів: {hist_cnt}\n⏣ Мова: Українська",
        "btn_saved": "☆ Збережені",
        "btn_history": "⏱ Історія",
        "btn_lang": "⏣ Мова: Українська",
        "saved_empty": "☆ <b>Збережені імена</b>\n\nСписок збережених поки що порожній.",
        "saved_title": "☆ <b>Збережені імена</b>\n\n",
        "history_empty": "⏱ <b>Історія перевірок</b>\n\nІсторія запитів порожня.",
        "history_title": "⏱ <b>Історія перевірок</b>\n\n",
        "help_text": "✪ <b>Довідка та інструкція</b>\n\n1. Виберіть потрібний режим у головному меню.\n2. Вкажіть параметри або введіть ключове слово.\n3. Отримайте вільне ім'я та збережіть його в профіль.",
        "len_prompt": "ϟ <b>Автоматичний пошук</b>\n\nОбрана довжина: {length} символів.\nЧи використовувати цифри у назві?",
        "digits_yes": "☑ З цифрами",
        "digits_no": "☒ Тільки букви",
        "dcount_prompt": "ϟ <b>Автоматичний пошук</b>\n\nДовжина: {length} символів.\nСкільки цифр додати?",
        "scan_nodig": "⌕ Сканування імені з {length} символів (без цифр)...",
        "scan_dig": "⌕ Сканування імені ({length} символів, {d_count} цифр)...",
        "scan_prefix": "⌕ Пошук за префіксом «{prefix}»...",
        "scan_smart": "⎈ Генерація варіацій для «{base}»...",
        "err_not_found": "⚠ <b>Помилка</b>\n\nВільних імен за вашими параметрами не знайдено.",
        "err_prefix": "⚠ <b>Помилка</b>\n\nНічого не знайдено за цим префіксом.",
        "err_smart": "⚠ <b>Помилка</b>\n\nНе вдалося знайти вільних варіацій для цього слова.",
        "res_title": "🜲 <b>РЕЗУЛЬТАТ ПОШУКУ</b>\n\n◌ Ім'я: <code>{username}</code>\n◌ Довжина: {length} символів\n◌ Читабельність: {readability} / 10\n◌ Категорія: {category}\n◌ Статус: Вільний для реєстрації\n",
        "cat_prem": "Преміум",
        "cat_std": "Стандартний",
        "cat_reg": "Звичайний",
        "btn_open": "↗ Відкрити посилання",
        "btn_save": "☆ Зберегти",
        "btn_retry": "↻ Повторити спробу",
        "saved_success": "• Успішно збережено: {uname}",
        "saved_already": "• Цей елемент вже є у вашому списку.",
        "lang_changed": "• Мову змінено на українську."
    }
}

def t(user_id: int, key: str, **kwargs) -> str:
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    text = LANGS.get(lang, LANGS["en"]).get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text

class BotStates(StatesGroup):
    auto_search = State()
    prefix_search = State()
    smart_variations = State()

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(user_id, "btn_auto"), callback_data="nav:auto"),
            InlineKeyboardButton(text=t(user_id, "btn_prefix"), callback_data="nav:prefix"),
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_smart"), callback_data="nav:smart"),
            InlineKeyboardButton(text=t(user_id, "btn_profile"), callback_data="nav:profile"),
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_help"), callback_data="nav:help"),
        ]
    ])

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "back"), callback_data="nav:main")]])

def length_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 12):
        row.append(InlineKeyboardButton(text=f"○ {length}", callback_data=f"len:{length}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text=t(user_id, "back"), callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def digits_choice_keyboard(user_id: int, length: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(user_id, "digits_yes"), callback_data=f"dig:yes:{length}"),
            InlineKeyboardButton(text=t(user_id, "digits_no"), callback_data=f"dig:no:{length}")
        ],
        [InlineKeyboardButton(text=t(user_id, "back"), callback_data="nav:auto")]
    ])

def digits_count_keyboard(user_id: int, length: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    max_d = min(3, length - 1)
    for d in range(1, max_d + 1):
        row.append(InlineKeyboardButton(text=f"○ {d}", callback_data=f"dcount:{length}:{d}"))
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text=t(user_id, "back"), callback_data=f"len:{length}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_result_keyboard(user_id: int, clean_u: str, retry_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(user_id, "btn_open"), url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text=t(user_id, "btn_save"), callback_data=f"save:{clean_u}")
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_retry"), callback_data=retry_callback)
        ],
        [
            InlineKeyboardButton(text=t(user_id, "main_menu"), callback_data="nav:main")
        ]
    ])

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
        async with session.get(url, headers=headers, allow_redirects=True) as resp:
            if resp.status != 200:
                return False
            text = await resp.text()
            
            if any(marker in text for marker in [
                "is available on Telegram",
                "you can set up",
                "username is not taken",
                "WebApp",
                "tgme_username_link"
            ]):
                if "tgme_page_title" in text and "is available" not in text:
                    return False
                return True
                
            return False
    except Exception:
        return False

async def generate_and_find_free(user_id: int, prefix: str = "", suffix: str = "", target_length: int = 6, use_digits: bool = True, digits_count: int = 1) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"
    
    timeout = aiohttp.ClientTimeout(total=1.5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        candidates = set()
        
        if prefix:
            prefix = prefix.lstrip("@").lower()
            candidates.add(f"{prefix}bot")
            candidates.add(f"{prefix}_chat")
            candidates.add(f"{prefix}_channel")
            candidates.add(f"the_{prefix}")
            candidates.add(f"{prefix}_2026")
            for _ in range(15):
                rand_suffix = "".join(random.choice(letters + digits) for _ in range(target_length - len(prefix)))
                candidates.add(f"{prefix}{rand_suffix}"[:target_length])
        else:
            for _ in range(30):
                first = random.choice(letters)
                if use_digits and digits_count > 0:
                    mid = "".join(random.choice(letters + "_") for _ in range(target_length - digits_count - 1))
                    digs = "".join(random.choice(digits) for _ in range(digits_count))
                    cand = first + mid + digs
                else:
                    cand = first + "".join(random.choice(letters + "_") for _ in range(target_length - 1))
                
                if len(cand) == target_length:
                    candidates.add(cand)

        for candidate in candidates:
            if USERNAME_PATTERN.match(candidate):
                if await check_single_username(session, candidate):
                    return f"@{candidate}"
                    
    return ""

def format_result_card(user_id: int, username: str) -> str:
    clean = username.lstrip("@")
    length = len(clean)
    
    readability = max(4, min(10, 11 - length))
    if "_" in clean or any(c.isdigit() for c in clean):
        readability = max(4, readability - 2)
        
    if length <= 5:
        category = t(user_id, "cat_prem")
    elif length == 6:
        category = t(user_id, "cat_std")
    else:
        category = t(user_id, "cat_reg")
        
    return t(user_id, "res_title", username=username, length=length, readability=readability, category=category)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    name = html.escape(message.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await message.answer(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")

@dp.callback_query(F.data.startswith("nav:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    profile = get_user_profile(user_id)
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = t(user_id, "welcome", name=name)
        await callback.message.edit_text(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
        
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        text = t(user_id, "auto_title")
        await callback.message.edit_text(text, reply_markup=length_keyboard(user_id), parse_mode="HTML")
        
    elif action == "prefix":
        await state.set_state(BotStates.prefix_search)
        text = t(user_id, "prefix_title")
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    elif action == "smart":
        await state.set_state(BotStates.smart_variations)
        text = t(user_id, "smart_title")
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    elif action == "profile":
        saved_count = len(profile["saved"])
        history_count = len(profile["history"])
        
        text = t(user_id, "profile_title", user_id=user_id, checks=profile['checks_count'], saved_cnt=saved_count, hist_cnt=history_count)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=t(user_id, "btn_saved"), callback_data="nav:view_saved"),
                InlineKeyboardButton(text=t(user_id, "btn_history"), callback_data="nav:view_history")
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_lang"), callback_data="nav:toggle_lang")
            ],
            [InlineKeyboardButton(text=t(user_id, "back"), callback_data="nav:main")]
        ])
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        
    elif action == "toggle_lang":
        profile["lang"] = "uk" if profile["lang"] == "en" else "en"
        
        saved_count = len(profile["saved"])
        history_count = len(profile["history"])
        text = t(user_id, "profile_title", user_id=user_id, checks=profile['checks_count'], saved_cnt=saved_count, hist_cnt=history_count)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=t(user_id, "btn_saved"), callback_data="nav:view_saved"),
                InlineKeyboardButton(text=t(user_id, "btn_history"), callback_data="nav:view_history")
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_lang"), callback_data="nav:toggle_lang")
            ],
            [InlineKeyboardButton(text=t(user_id, "back"), callback_data="nav:main")]
        ])
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await callback.answer(t(user_id, "lang_changed"), show_alert=True)
        return
        
    elif action == "view_saved":
        saved = profile["saved"]
        if not saved:
            text = t(user_id, "saved_empty")
        else:
            items = [f"• <code>{u}</code>" for u in saved]
            text = t(user_id, "saved_title") + "\n".join(items)
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    elif action == "view_history":
        history = profile["history"]
        if not history:
            text = t(user_id, "history_empty")
        else:
            items = [f"• <code>{u}</code>" for u in history[:10]]
            text = t(user_id, "history_title") + "\n".join(items)
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    elif action == "help":
        text = t(user_id, "help_text")
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    await callback.answer()

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    length = int(callback.data.split(":")[1])
    text = t(user_id, "len_prompt", length=length)
    await callback.message.edit_text(text, reply_markup=digits_choice_keyboard(user_id, length), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dig:"))
async def digits_choice_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    choice = parts[1]
    length = int(parts[2])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    if choice == "yes":
        text = t(user_id, "dcount_prompt", length=length)
        await callback.message.edit_text(text, reply_markup=digits_count_keyboard(user_id, length), parse_mode="HTML")
    else:
        msg = await callback.message.edit_text(t(user_id, "scan_nodig", length=length), parse_mode="HTML")
        username = await generate_and_find_free(user_id=user_id, target_length=length, use_digits=False)
        
        profile["checks_count"] += 1
        if username:
            add_to_history(user_id, [username])
        
        if not username:
            err_text = t(user_id, "err_not_found")
            await msg.edit_text(err_text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
            return

        clean_u = username.lstrip('@')
        text = format_result_card(user_id, username)
        markup = get_result_keyboard(user_id, clean_u, retry_callback=f"len:{length}")
        
        await msg.edit_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("save:"))
async def save_username_callback(callback: CallbackQuery):
    raw_uname = callback.data.split(":", 1)[1]
    uname = f"@{raw_uname.lstrip('@')}"
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    if uname not in profile["saved"]:
        profile["saved"].append(uname)
        await callback.answer(t(user_id, "saved_success", uname=uname), show_alert=True)
    else:
        await callback.answer(t(user_id, "saved_already"), show_alert=True)

@dp.message(BotStates.prefix_search)
async def process_prefix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prefix = message.text.strip().lstrip("@")
    await state.clear()
    
    target_len = max(5, len(prefix) + 2)
    if target_len > 32:
        target_len = 32
        
    profile = get_user_profile(user_id)
    msg = await message.answer(t(user_id, "scan_prefix", prefix=prefix), parse_mode="HTML")
    username = await generate_and_find_free(user_id=user_id, prefix=prefix, target_length=target_len)
    
    profile["checks_count"] += 1
    if username:
        add_to_history(user_id, [username])
    
    if not username:
        err_text = t(user_id, "err_prefix")
        await msg.edit_text(err_text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    clean_u = username.lstrip('@')
    text = format_result_card(user_id, username)
    markup = get_result_keyboard(user_id, clean_u, retry_callback="nav:prefix")
    
    await msg.edit_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

@dp.message(BotStates.smart_variations)
async def process_smart_variations(message: Message, state: FSMContext):
    user_id = message.from_user.id
    base = message.text.strip().lstrip("@").lower()
    await state.clear()
    
    profile = get_user_profile(user_id)
    msg = await message.answer(t(user_id, "scan_smart", base=base), parse_mode="HTML")
    
    variations = [
        f"{base}_app", f"{base}_bot", f"the_{base}", f"{base}_hq", 
        f"{base}_chat", f"{base}_hub", f"{base}_club", f"real_{base}",
        f"{base}_dev", f"{base}_24", f"{base}news", f"get_{base}"
    ]
    
    free_found = ""
    timeout = aiohttp.ClientTimeout(total=1.5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for var in variations:
            if len(var) >= 5 and len(var) <= 32 and USERNAME_PATTERN.match(var):
                if await check_single_username(session, var):
                    free_found = f"@{var}"
                    break
                    
    profile["checks_count"] += 1
    if free_found:
        add_to_history(user_id, [free_found])
            
    if not free_found:
        err_text = t(user_id, "err_smart")
        await msg.edit_text(err_text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    clean_u = free_found.lstrip('@')
    text = format_result_card(user_id, free_found)
    markup = get_result_keyboard(user_id, clean_u, retry_callback="nav:smart")
    
    await msg.edit_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
