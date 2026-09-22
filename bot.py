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

# Впиши сюди свій числовий ID в Telegram для доступу до адмін-панелі
ADMIN_ID = YOUR_TELEGRAM_ID  # 5619415334

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
        "welcome": "<b>Welcome back, {name}!</b>\n\nSelect an option from the menu below:",
        "btn_auto": "⚡ Auto Search",
        "btn_saved": "☆ Saved Tags",
        "btn_history": "⏱ History",
        "btn_updates": "✨ Updates №04 (22.09.26)",
        "btn_lang": "🌐 Language: EN / UA",
        "btn_help": "🛡 Help & Info",
        "back": "‹ Back",
        "main_menu": "⌂ Main Menu",
        "auto_title": "⚡ <b>Auto Search</b>\n\nChoose the desired username length (5 to 11 characters):",
        "help_text": "🛡 <b>Help & Instructions</b>\n\n1. Use <b>Auto Search</b> to find random available usernames instantly.\n2. Save your favorite tags using the star button.\n3. Access your history and saved items anytime from the menu.",
        "updates_text": (
            "✨ <b>Changelog & Updates №04 (22.09.26)</b>\n\n"
            "• <b>Performance:</b> Implemented lightning-fast parallel username scanning using asynchronous routines.\n"
            "• <b>Admin Tools:</b> Added a secure administrative panel with real-time usage statistics.\n"
            "• <b>Interface:</b> Refreshed menu layout and improved localization handling.\n"
            "• <b>Stability:</b> Fixed connection timeouts and optimized memory management."
        ),
        "len_prompt": "⚡ <b>Auto Search</b>\n\nSelected length: <code>{length}</code> chars.\nDo you want to include digits?",
        "digits_yes": "☑ With Digits",
        "digits_no": "☒ Letters Only",
        "dcount_prompt": "⚡ <b>Auto Search</b>\n\nLength: <code>{length}</code> characters.\nHow many digits would you like to include?",
        "scan_nodig": "⌕ Scanning {length}-char username (letters only)...",
        "scan_dig": "⌕ Scanning username ({length} chars, {d_count} digits)...",
        "err_not_found": "⚠ <b>No Results Found</b>\n\nCould not find available usernames with these parameters right now. Please try again!",
        "res_title": "💎 <b>AVAILABLE USERNAME FOUND</b>\n\n◌ Username: <code>{username}</code>\n◌ Length: {length} characters\n◌ Readability: {readability} / 10\n◌ Category: {category}\n◌ Status: Free for registration\n",
        "cat_prem": "Premium",
        "cat_std": "Standard",
        "cat_reg": "Regular",
        "btn_open": "↗ Open Link",
        "btn_save": "☆ Save",
        "btn_retry": "↻ Try Again",
        "saved_success": "Successfully saved {uname}!",
        "saved_already": "This tag is already in your saved list.",
        "saved_empty": "☆ <b>Saved Tags</b>\n\nYour saved list is currently empty.",
        "saved_title": "☆ <b>Saved Tags</b>\n\n",
        "history_empty": "⏱ <b>Search History</b>\n\nYour history is currently empty.",
        "history_title": "⏱ <b>Search History</b>\n\n",
        "lang_changed": "Language successfully switched to English."
    },
    "uk": {
        "welcome": "<b>Вітаю, {name}!</b>\n\nОберіть потрібну дію в меню нижче:",
        "btn_auto": "⚡ Автоматичний пошук",
        "btn_saved": "☆ Збережені теги",
        "btn_history": "⏱ Історія",
        "btn_updates": "✨ Оновлення №04 (22.09.26)",
        "btn_lang": "🌐 Мова: UA / EN",
        "btn_help": "🛡 Довідка",
        "back": "‹ Назад",
        "main_menu": "⌂ Головне меню",
        "auto_title": "⚡ <b>Автоматичний пошук</b>\n\nОберіть бажану довжину нікнейма (від 5 до 11 символів):",
        "help_text": "🛡 <b>Довідка та інструкція</b>\n\n1. Використовуйте <b>Автопошук</b> для швидкого знаходження вільних імен.\n2. Зберігайте улюблені варіанти у списку обраних.\n3. Переглядайте історію попередніх запитів у будь-який момент.",
        "updates_text": (
            "✨ <b>Список оновлень №04 (22.09.26)</b>\n\n"
            "• <b>Швидкодія:</b> Інтегровано паралельний сканер для миттєвої перевірки десятків варіантів одночасно.\n"
            "• <b>Адміністрування:</b> Додано повноцінну панель управління з поточною статистикою бота.\n"
            "• <b>Інтерфейс:</b> Оновлено дизайн кнопок, покращено навігацію та локалізацію.\n"
            "• <b>Стабільність:</b> Усунуто затримки в мережі та оптимізовано роботу пам'яті."
        ),
        "len_prompt": "⚡ <b>Автоматичний пошук</b>\n\nОбрана довжина: <code>{length}</code> симв.\nЧи використовувати цифри у назві?",
        "digits_yes": "☑ З цифрами",
        "digits_no": "☒ Тільки букви",
        "dcount_prompt": "⚡ <b>Автоматичний пошук</b>\n\nДовжина: <code>{length}</code> символів.\nСкільки цифр бажаєте додати?",
        "scan_nodig": "⌕ Сканування імені з {length} символів (без цифр)...",
        "scan_dig": "⌕ Сканування імені ({length} символів, {d_count} цифр)...",
        "err_not_found": "⚠ <b>Нічого не знайдено</b>\n\nЗа заданими параметрами вільних імен зараз немає. Спробуйте ще раз!",
        "res_title": "💎 <b>ВІЛЬНИЙ ЮЗЕРНЕЙМ ЗНАЙДЕНО</b>\n\n◌ Ім'я: <code>{username}</code>\n◌ Довжина: {length} символів\n◌ Читабельність: {readability} / 10\n◌ Категорія: {category}\n◌ Статус: Вільний для реєстрації\n",
        "cat_prem": "Преміум",
        "cat_std": "Стандартний",
        "cat_reg": "Звичайний",
        "btn_open": "↗ Відкрити посилання",
        "btn_save": "☆ Зберегти",
        "btn_retry": "↻ Повторити спробу",
        "saved_success": "Успішно збережено {uname}!",
        "saved_already": "Цей тег вже є у вашому списку.",
        "saved_empty": "☆ <b>Збережені теги</b>\n\nВаш список збережених поки що порожній.",
        "saved_title": "☆ <b>Збережені теги</b>\n\n",
        "history_empty": "⏱ <b>Історія перевірок</b>\n\nІсторія запитів поки що порожня.",
        "history_title": "⏱ <b>Історія перевірок</b>\n\n",
        "lang_changed": "Мову успішно змінено на українську."
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

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id, "btn_auto"), callback_data="nav:auto")],
        [
            InlineKeyboardButton(text=t(user_id, "btn_saved"), callback_data="nav:view_saved"),
            InlineKeyboardButton(text=t(user_id, "btn_history"), callback_data="nav:view_history"),
        ],
        [InlineKeyboardButton(text=t(user_id, "btn_updates"), callback_data="nav:updates")],
        [
            InlineKeyboardButton(text=t(user_id, "btn_lang"), callback_data="nav:toggle_lang"),
            InlineKeyboardButton(text=t(user_id, "btn_help"), callback_data="nav:help"),
        ]
    ])

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "back"), callback_data="nav:main")]])

def length_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 12):
        row.append(InlineKeyboardButton(text=f"• {length}", callback_data=f"len:{length}"))
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
        row.append(InlineKeyboardButton(text=f"• {d}", callback_data=f"dcount:{length}:{d}"))
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

async def generate_and_find_free(user_id: int, target_length: int = 6, use_digits: bool = True, digits_count: int = 1) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"
    timeout = aiohttp.ClientTimeout(total=1.5)
    
    candidates = set()
    for _ in range(40):
        first = random.choice(letters)
        if use_digits and digits_count > 0:
            mid = "".join(random.choice(letters + "_") for _ in range(target_length - digits_count - 1))
            digs = "".join(random.choice(digits) for _ in range(digits_count))
            cand = first + mid + digs
        else:
            cand = first + "".join(random.choice(letters + "_") for _ in range(target_length - 1))
        
        if len(cand) == target_length and USERNAME_PATTERN.match(cand):
            candidates.add(cand)

    if not candidates:
        return ""

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [check_single_username(session, cand) for cand in candidates]
        results = await asyncio.gather(*tasks)
        
        candidates_list = list(candidates)
        for i, is_free in enumerate(results):
            if is_free:
                return f"@{candidates_list[i]}"
                
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

async def send_main_menu(message_or_callback, user_id: int, edit: bool = True):
    name = html.escape(message_or_callback.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    markup = main_keyboard(user_id)
    if edit:
        await message_or_callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message_or_callback.answer(text, reply_markup=markup, parse_mode="HTML")

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    get_user_profile(user_id)
    await send_main_menu(message, user_id, edit=False)

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⚠ У вас немає прав доступу до цієї панелі.")
        return
    
    total_users = len(user_data_store)
    total_checks = sum(p["checks_count"] for p in user_data_store.values())
    total_saved = sum(len(p["saved"]) for p in user_data_store.values())
    
    admin_text = (
        "🛡 <b>Панель адміністратора</b>\n\n"
        f"👥 Унікальних користувачів: <code>{total_users}</code>\n"
        f"📊 Всього перевірок виконано: <code>{total_checks}</code>\n"
        f"💾 Всього збережено тегів: <code>{total_saved}</code>"
    )
    await message.answer(admin_text, parse_mode="HTML", reply_markup=back_keyboard(message.from_user.id))

@dp.callback_query(F.data.startswith("nav:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    profile = get_user_profile(user_id)
    
    if action == "main":
        await send_main_menu(callback, user_id, edit=True)
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        text = t(user_id, "auto_title")
        await callback.message.edit_text(text, reply_markup=length_keyboard(user_id), parse_mode="HTML")
    elif action == "toggle_lang":
        profile["lang"] = "uk" if profile["lang"] == "en" else "en"
        await send_main_menu(callback, user_id, edit=True)
        await callback.answer(t(user_id, "lang_changed"), show_alert=True)
        return
    elif action == "updates":
        text = t(user_id, "updates_text")
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
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

@dp.callback_query(F.data.startswith("dcount:"))
async def digits_count_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    length = int(parts[1])
    d_count = int(parts[2])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    msg = await callback.message.edit_text(t(user_id, "scan_dig", length=length, d_count=d_count), parse_mode="HTML")
    username = await generate_and_find_free(user_id=user_id, target_length=length, use_digits=True, digits_count=d_count)
    
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
    if uname in profile["saved"]:
        await callback.answer(t(user_id, "saved_already"), show_alert=True)
        return
        
    profile["saved"].append(uname)
    await callback.answer(t(user_id, "saved_success", uname=uname), show_alert=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot is starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
