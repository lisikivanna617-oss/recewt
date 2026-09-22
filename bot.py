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
            InlineKeyboardButton(text="✦ Автоматичний пошук", callback_data="nav:auto"),
            InlineKeyboardButton(text="✦ Префікс / Суфікс", callback_data="nav:prefix"),
        ],
        [
            InlineKeyboardButton(text="✦ Розумні варіації", callback_data="nav:smart"),
            InlineKeyboardButton(text="✦ Особистий профіль", callback_data="nav:profile"),
        ],
        [
            InlineKeyboardButton(text="▫ Довідка та інструкція", callback_data="nav:help"),
        ]
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Повернутися назад", callback_data="nav:main")]])

def length_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 12):
        row.append(InlineKeyboardButton(text=f"• {length} символів", callback_data=f"len:{length}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="« Повернутися назад", callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def digits_choice_keyboard(length: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✓ З цифрами", callback_data=f"dig:yes:{length}"),
            InlineKeyboardButton(text="✕ Тільки букви", callback_data=f"dig:no:{length}")
        ],
        [InlineKeyboardButton(text="« Повернутися назад", callback_data="nav:auto")]
    ])

def digits_count_keyboard(length: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    max_d = min(3, length - 1)
    for d in range(1, max_d + 1):
        row.append(InlineKeyboardButton(text=f"• {d} цифр(и)", callback_data=f"dcount:{length}:{d}"))
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="« Повернутися назад", callback_data=f"len:{length}")])
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
        ("✧ Підключення до мережі...", 20),
        ("✧ Сканування вільних адрес...", 50),
        ("✧ Перевірка доступності...", 80),
        ("✧ Пошук успішно завершено", 100),
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
        category = "Преміум"
    elif length == 6:
        category = "Стандартний"
    else:
        category = "Звичайний"
        
    return (
        f"✦ <b>РЕЗУЛЬТАТ ПОШУКУ</b>\n\n"
        f"▫ Ім'я: <code>{username}</code>\n"
        f"▫ Довжина: {length} символів\n"
        f"▫ Читабельність: {readability} / 10\n"
        f"▫ Категорія: {category}\n"
        f"▫ Статус: Вільний для реєстрації\n"
    )

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    name = html.escape(message.from_user.first_name)
    text = (
        f"<b>Вітаю, {name}</b>\n\n"
        f"Оберіть необхідний розділ за допомогою меню нижче:"
    )
    await message.answer(text, reply_markup=main_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("nav:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    profile = get_user_profile(user_id)
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = (
            f"<b>Вітаю, {name}</b>\n\n"
            f"Оберіть необхідний розділ за допомогою меню нижче:"
        )
        await callback.message.edit_text(text, reply_markup=main_keyboard(), parse_mode="HTML")
        
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        text = "✦ <b>Автоматичний пошук</b>\n\nОберіть бажану довжину імені (від 5 до 11 символів):"
        await callback.message.edit_text(text, reply_markup=length_keyboard(), parse_mode="HTML")
        
    elif action == "prefix":
        await state.set_state(BotStates.prefix_search)
        text = "✦ <b>Пошук за префіксом</b>\n\nВведіть текст або частину імені, з якої має починатися результат:"
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "smart":
        await state.set_state(BotStates.smart_variations)
        text = "✦ <b>Розумні варіації</b>\n\nВведіть базове слово для генерації унікальних комбінацій:"
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "profile":
        saved_count = len(profile["saved"])
        history_count = len(profile["history"])
        
        text = (
            f"✦ <b>Особистий профіль</b>\n\n"
            f"▫ ID користувача: <code>{user_id}</code>\n"
            f"▫ Загалом перевірок: {profile['checks_count']}\n"
            f"▫ Збережено імен: {saved_count}\n"
            f"▫ Історія запитів: {history_count}\n"
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="▫ Збережені", callback_data="nav:view_saved"),
                InlineKeyboardButton(text="▫ Історія", callback_data="nav:view_history")
            ],
            [InlineKeyboardButton(text="« Повернутися назад", callback_data="nav:main")]
        ])
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        
    elif action == "view_saved":
        saved = profile["saved"]
        if not saved:
            text = "✦ <b>Збережені імена</b>\n\nСписок збережених поки що порожній."
        else:
            items = [f"• <code>{u}</code>" for u in saved]
            text = "✦ <b>Збережені імена</b>\n\n" + "\n".join(items)
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "view_history":
        history = profile["history"]
        if not history:
            text = "✦ <b>Історія перевірок</b>\n\nІсторія запитів порожня."
        else:
            items = [f"• <code>{u}</code>" for u in history[:10]]
            text = "✦ <b>Історія перевірок</b>\n\n" + "\n".join(items)
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    elif action == "help":
        text = (
            "✦ <b>Довідка</b>\n\n"
            "1. Виберіть потрібний режим у головному меню.\n"
            "2. Вкажіть параметри або введіть ключове слово.\n"
            "3. Отримайте вільне ім'я та збережіть його в профіль.\n"
        )
        await callback.message.edit_text(text, reply_markup=back_keyboard(), parse_mode="HTML")
        
    await callback.answer()

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    text = f"✦ <b>Автоматичний пошук</b>\n\nОбрана довжина: {length} символів.\nЧи використовувати цифри у назві?"
    await callback.message.edit_text(text, reply_markup=digits_choice_keyboard(length), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dig:"))
async def digits_choice_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    choice = parts[1]
    length = int(parts[2])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    if choice == "yes":
        text = f"✦ <b>Автоматичний пошук</b>\n\nДовжина: {length} символів.\nСкільки цифр додати?"
        await callback.message.edit_text(text, reply_markup=digits_count_keyboard(length), parse_mode="HTML")
    else:
        msg = await callback.message.edit_text(f"✧ Сканування імені з {length} символів (без цифр)...", parse_mode="HTML")
        results = await generate_and_find_free(message_to_edit=msg, target_length=length, use_digits=False, count=1)
        
        profile["checks_count"] += 1
        add_to_history(user_id, results)
        
        if not results:
            err_text = "✦ <b>Помилка</b>\n\nВільних імен за вашими параметрами не знайдено."
            await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
            return

        username = results[0]
        clean_u = username.lstrip('@')
        text = format_result_card(username)
        
        buttons = [
            [
                InlineKeyboardButton(text="↗ Відкрити посилання", url=`https://t.me/{clean_u}`),
                InlineKeyboardButton(text="✓ Зберегти", callback_data=f"save:{clean_u}")
            ],
            [
                InlineKeyboardButton(text="↻ Шукати ще раз", callback_data=f"len:{length}")
            ],
            [InlineKeyboardButton(text="« Головне меню", callback_data="nav:main")]
        ]
        
        await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("dcount:"))
async def digits_count_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    length = int(parts[1])
    d_count = int(parts[2])
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    msg = await callback.message.edit_text(f"✧ Сканування імені ({length} символів, {d_count} цифр)...", parse_mode="HTML")
    results = await generate_and_find_free(message_to_edit=msg, target_length=length, use_digits=True, digits_count=d_count, count=1)
    
    profile["checks_count"] += 1
    add_to_history(user_id, results)
    
    if not results:
        err_text = "✦ <b>Помилка</b>\n\nВільних імен за вашими параметрами не знайдено."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return

    username = results[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="↗ Відкрити посилання", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="✓ Зберегти", callback_data=f"save:{clean_u}")
        ],
        [
            InlineKeyboardButton(text="↻ Шукати ще раз", callback_data=f"len:{length}")
        ],
        [InlineKeyboardButton(text="« Головне меню", callback_data="nav:main")]
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
        await callback.answer(f"Успішно збережено: {uname}", show_alert=True)
    else:
        await callback.answer("Цей елемент вже є у вашому списку.", show_alert=True)

@dp.message(BotStates.prefix_search)
async def process_prefix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prefix = message.text.strip().lstrip("@")
    await state.clear()
    
    target_len = max(5, len(prefix) + 2)
    if target_len > 32:
        target_len = 32
        
    profile = get_user_profile(user_id)
    msg = await message.answer(f"✧ Пошук за префіксом «{prefix}»...", parse_mode="HTML")
    results = await generate_and_find_free(message_to_edit=msg, prefix=prefix, target_length=target_len, use_digits=True, digits_count=1, count=1)
    
    profile["checks_count"] += 1
    add_to_history(user_id, results)
    
    if not results:
        err_text = "✦ <b>Помилка</b>\n\nНічого не знайдено за цим префіксом."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return
        
    username = results[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="↗ Відкрити посилання", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="✓ Зберегти", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="« Головне меню", callback_data="nav:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(BotStates.smart_variations)
async def process_smart_variations(message: Message, state: FSMContext):
    user_id = message.from_user.id
    base = message.text.strip().lstrip("@")
    await state.clear()
    
    profile = get_user_profile(user_id)
    msg = await message.answer(f"✧ Генерація варіацій для «{base}»...", parse_mode="HTML")
    
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
        err_text = "✦ <b>Помилка</b>\n\nНе вдалося знайти вільних варіацій для цього слова."
        await msg.edit_text(err_text, reply_markup=main_keyboard(), parse_mode="HTML")
        return
        
    username = free_found[0]
    clean_u = username.lstrip('@')
    text = format_result_card(username)
    
    buttons = [
        [
            InlineKeyboardButton(text="↗ Відкрити посилання", url=f"https://t.me/{clean_u}"),
            InlineKeyboardButton(text="✓ Зберегти", callback_data=f"save:{clean_u}")
        ],
        [InlineKeyboardButton(text="« Головне меню", callback_data="nav:main")]
    ]
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
