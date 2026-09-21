import asyncio
import html
import logging
import os
import random
import re
import uuid
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
    BufferedInputFile,
)
from aiogram.exceptions import TelegramBadRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# Отримання токена з Railway Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logging.error("BOT_TOKEN не знайдено у Variables Railway!")

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher()

ADMIN_ID = 5619415334
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

# Збереження даних у пам'яті
user_data_store = {}
search_results_cache = {}
global_checked_usernames = set()

TEXTS = {
    "en": {
        "welcome": "👋 <b>Welcome to USERNAME FIX, {name}!</b>\n═════════════════════\nAutomated Telegram Username Finder & Generator.\n\n👇 <i>Choose an action below:</i>",
        "btn_auto_search": "🔍 Auto-Search",
        "btn_prefix_search": "🔤 Prefix / Suffix",
        "btn_exact_search": "🎯 Exact Check",
        "btn_smart_variations": "🧠 Smart Variations",
        "btn_profile": "👤 Profile & Saved",
        "btn_settings": "🌍 Language",
        "btn_help": "ℹ️ Help",
        "btn_back": "« Back to Menu",
        "btn_export_txt": "📦 Export TXT",
        "search_prompt": "🔍 <b>Auto-Search Usernames</b>\nSelect desired username length (5 to 12 chars):",
        "exact_prompt": "🎯 <b>Exact Search</b>\nSend the exact username to check (e.g. <code>@username</code>):",
        "smart_prompt": "🧠 <b>Smart Variations</b>\nSend a base name (e.g., <code>falbercht</code>):",
        "prefix_prompt": "🔤 <b>Prefix Search</b>\nSend prefix or suffix (e.g., <code>app</code> or <code>bot</code>):",
        "searching": "🔍 Scanning Telegram network... Please wait ⏳",
        "search_results": "🎉 <b>Found Available Usernames</b>\n🆔 <b>Search ID:</b> <code>#{search_id}</code>\n─────────────────────\n{results}",
        "search_none": "❌ No free usernames found. Try again!",
        "profile_text": "👤 <b>User Profile</b>\n─────────────────────\n🆔 <b>User ID:</b> <code>{user_id}</code>\n🌍 <b>Language:</b> {lang}\n📊 <b>Checks Performed:</b> {checks}\n⭐ <b>Saved Usernames:</b> {saved_count}",
        "saved_title": "⭐ <b>Your Saved Usernames:</b>\n─────────────────────\n{list}",
        "saved_empty": "⭐ No saved usernames yet.",
        "saved_success": "✅ Username <b>{username}</b> saved!",
        "help_text": "ℹ️ <b>Help & Features</b>\n═════════════════════\n• <b>Auto-Search:</b> Scan random free usernames.\n• <b>Prefix/Suffix:</b> Search with specific text.\n• <b>Exact Check:</b> Direct username verification.\n• <b>Smart Variations:</b> Generate name variations.",
        "lang_changed": "Language updated! ✅",
    },
    "ua": {
        "welcome": "👋 <b>Ласкаво просимо до USERNAME FIX, {name}!</b>\n═════════════════════\nАвтоматизований пошук та генерація юзернеймів Telegram.\n\n👇 <i>Оберіть дію нижче:</i>",
        "btn_auto_search": "🔍 Авто-пошук",
        "btn_prefix_search": "🔤 Префікс / Суфікс",
        "btn_exact_search": "🎯 Точна перевірка",
        "btn_smart_variations": "🧠 Розумні варіації",
        "btn_profile": "👤 Профіль та Збережені",
        "btn_settings": "🌍 Налаштування мови",
        "btn_help": "ℹ️ Довідка",
        "btn_back": "« Назад у меню",
        "btn_export_txt": "📦 Експорт TXT",
        "search_prompt": "🔍 <b>Авто-пошук юзернеймів</b>\nОберіть бажану довжину (від 5 до 12 символів):",
        "exact_prompt": "🎯 <b>Точний пошук</b>\nВведіть юзернейм для перевірки (наприклад, <code>@username</code>):",
        "smart_prompt": "🧠 <b>Розумні варіації</b>\nВведіть базове ім'я (наприклад, <code>falbercht</code>):",
        "prefix_prompt": "🔤 <b>Пошук за словом</b>\nВведіть префікс або суфікс (наприклад, <code>app</code>):",
        "searching": "🔍 Скануємо мережу Telegram... Зачекайте ⏳",
        "search_results": "🎉 <b>Знайдені вільні юзернейми</b>\n🆔 <b>Search ID:</b> <code>#{search_id}</code>\n─────────────────────\n{results}",
        "search_none": "❌ Вільних юзернеймів не знайдено. Спробуйте ще раз!",
        "profile_text": "👤 <b>Профіль користувача</b>\n─────────────────────\n🆔 <b>User ID:</b> <code>{user_id}</code>\n🌍 <b>Мова:</b> {lang}\n📊 <b>Усього перевірок:</b> {checks}\n⭐ <b>Збережених:</b> {saved_count}",
        "saved_title": "⭐ <b>Ваші збережені юзернейми:</b>\n─────────────────────\n{list}",
        "saved_empty": "⭐ Збережених юзернеймів немає.",
        "saved_success": "✅ Юзернейм <b>{username}</b> збережено!",
        "help_text": "ℹ️ <b>Довідка та функції</b>\n═════════════════════\n• <b>Авто-пошук:</b> Пошук випадкових вільних юзерів.\n• <b>Префікс/Суфікс:</b> Пошук за початком/закінченням.\n• <b>Точна перевірка:</b> Пряма перевірка юзернейму.\n• <b>Розумні варіації:</b> Генерація назв із приставками.",
        "lang_changed": "Мову успішно змінено! ✅",
    }
}

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "ua",
            "saved": [],
            "checks_count": 0,
            "temp_length": 5,
        }
    return user_data_store[user_id]

def t(user_id: int, key: str, **kwargs) -> str:
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "ua")
    if lang not in TEXTS:
        lang = "ua"
    template = TEXTS[lang].get(key, TEXTS["ua"].get(key, ""))
    return template.format(**kwargs)

class BotStates(StatesGroup):
    auto_search = State()
    prefix_search = State()
    exact_search = State()
    smart_variations = State()

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(user_id, "btn_auto_search"), callback_data="menu:auto"),
                InlineKeyboardButton(text=t(user_id, "btn_exact_search"), callback_data="menu:exact"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_prefix_search"), callback_data="menu:prefix"),
                InlineKeyboardButton(text=t(user_id, "btn_smart_variations"), callback_data="menu:smart"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_profile"), callback_data="menu:profile"),
                InlineKeyboardButton(text=t(user_id, "btn_settings"), callback_data="menu:settings"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_help"), callback_data="menu:help"),
            ]
        ]
    )

def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")]]
    )

def length_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for length in range(5, 13):
        row.append(InlineKeyboardButton(text=str(length), callback_data=f"len:{length}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="setlang:ua"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang:en"),
            ],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logging.warning(f"TelegramBadRequest: {e}")
    except Exception as e:
        logging.error(f"Error editing message: {e}")

async def check_single_username(username: str) -> bool | None:
    username = username.lstrip("@").strip()
    if not USERNAME_PATTERN.match(username):
        return None
    url = f"https://t.me/{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=5) as resp:
                text = await resp.text()
                if "tgme_page_extra" in text or "tgme_page_title" in text:
                    if "If you have Telegram, you can contact" in text or "View in Telegram" in text or "tgme_user" in text:
                        return False
                if "If you have Telegram, you can set up" in text or "is available on Telegram" in text:
                    return True
                if resp.status == 200 and "tgme_page" in text and "tgme_page_photo" not in text:
                    return True
                return False
    except Exception:
        return None

async def generate_and_find_free(prefix: str = "", suffix: str = "", length: int = 5, count: int = 2) -> list:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789_"
    free_found = []
    attempts = 0
    
    while len(free_found) < count and attempts < 35:
        attempts += 1
        needed_len = length - len(prefix) - len(suffix)
        if needed_len < 1:
            needed_len = 2
            
        random_part = "".join(random.choice(chars) for _ in range(needed_len))
        candidate = f"{prefix}{random_part}{suffix}".lower()
        
        if not candidate[0].isalpha():
            candidate = "a" + candidate[1:]
            
        if candidate in global_checked_usernames:
            continue
            
        global_checked_usernames.add(candidate)
        is_free = await check_single_username(candidate)
        if is_free is True:
            free_found.append(f"@{candidate}")
        await asyncio.sleep(0.05)
    return free_found

def create_txt_export(results: list, search_id: str) -> BufferedInputFile:
    content = f"=== USERNAME FIX RESULTS (ID: #{search_id}) ===\n\n"
    for uname in results:
        content += f"Username: {uname}\nLink: https://t.me/{uname.lstrip('@')}\n-------------------\n"
    return BufferedInputFile(content.encode("utf-8"), filename=f"usernames_{search_id}.txt")

@dp.message(Command("start", "старт"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    name = html.escape(message.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await message.answer(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")

@dp.callback_query(F.data.startswith("menu:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await state.clear()
    action = callback.data.split(":")[1]
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = t(user_id, "welcome", name=name)
        await safe_edit_text(callback, text, reply_markup=main_keyboard(user_id))
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        await safe_edit_text(callback, t(user_id, "search_prompt"), reply_markup=length_keyboard(user_id))
    elif action == "prefix":
        await state.set_state(BotStates.prefix_search)
        await safe_edit_text(callback, t(user_id, "prefix_prompt"), reply_markup=back_keyboard(user_id))
    elif action == "exact":
        await state.set_state(BotStates.exact_search)
        await safe_edit_text(callback, t(user_id, "exact_prompt"), reply_markup=back_keyboard(user_id))
    elif action == "smart":
        await state.set_state(BotStates.smart_variations)
        await safe_edit_text(callback, t(user_id, "smart_prompt"), reply_markup=back_keyboard(user_id))
    elif action == "profile":
        profile = get_user_profile(user_id)
        text = t(
            user_id, "profile_text",
            user_id=user_id,
            lang=profile.get("lang", "ua").upper(),
            checks=profile.get("checks_count", 0),
            saved_count=len(profile.get("saved", []))
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⭐ Переглянути збережені", callback_data="menu:view_saved")],
                [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
            ]
        )
        await safe_edit_text(callback, text, reply_markup=markup)
    elif action == "view_saved":
        profile = get_user_profile(user_id)
        saved = profile.get("saved", [])
        if not saved:
            text = t(user_id, "saved_empty")
        else:
            items = [f"⭐ <code>{u}</code> — <a href='https://t.me/{u.lstrip('@')}'>Відкрити</a>" for u in saved]
            text = t(user_id, "saved_title", list="\n".join(items))
        await safe_edit_text(callback, text, reply_markup=back_keyboard(user_id))
    elif action == "settings":
        await safe_edit_text(callback, "⚙️ <b>Оберіть мову / Choose language:</b>", reply_markup=settings_keyboard(user_id))
    elif action == "help":
        await safe_edit_text(callback, t(user_id, "help_text"), reply_markup=back_keyboard(user_id))
        
    await callback.answer()

@dp.callback_query(F.data.startswith("setlang:"))
async def set_lang_callback(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    get_user_profile(user_id)["lang"] = lang
    
    name = html.escape(callback.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await safe_edit_text(callback, text, reply_markup=main_keyboard(user_id))
    await callback.answer(t(user_id, "lang_changed"))

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    await safe_edit_text(callback, t(user_id, "searching"))
    results = await generate_and_find_free(length=length, count=2)
    
    search_id = str(uuid.uuid4())[:6].upper()
    search_results_cache[search_id] = results
    
    profile = get_user_profile(user_id)
    profile["checks_count"] = profile.get("checks_count", 0) + len(results)
    
    if not results:
        await safe_edit_text(callback, t(user_id, "search_none"), reply_markup=main_keyboard(user_id))
        return

    formatted = [f"🔹 <code>{u}</code>" for u in results]
    buttons = []
    for u in results:
        buttons.append([
            InlineKeyboardButton(text=f"🔗 {u}", url=f"https://t.me/{u.lstrip('@')}"),
            InlineKeyboardButton(text="⭐ Зберегти", callback_data=f"save:{u}")
        ])
    buttons.append([InlineKeyboardButton(text=t(user_id, "btn_export_txt"), callback_data=f"export:{search_id}")])
    buttons.append([InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")])

    text = t(user_id, "search_results", search_id=search_id, results="\n".join(formatted))
    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("save:"))
async def save_username_callback(callback: CallbackQuery):
    uname = callback.data.split(":")[1]
    user_id = callback.from_user.id
    saved = get_user_profile(user_id)["saved"]
    
    if uname not in saved:
        saved.append(uname)
        await callback.answer(t(user_id, "saved_success", username=uname))
    else:
        await callback.answer("Вже збережено!")

@dp.callback_query(F.data.startswith("export:"))
async def export_txt_callback(callback: CallbackQuery):
    search_id = callback.data.split(":")[1]
    results = search_results_cache.get(search_id, [])
    
    if not results:
        await callback.answer("Результати застаріли!")
        return
        
    doc = create_txt_export(results, search_id)
    await callback.message.answer_document(doc, caption=f"📦 Файл результатів #{search_id}")
    await callback.answer()

@dp.message(BotStates.prefix_search)
async def process_prefix_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    prefix = message.text.strip().lstrip("@")
    await state.clear()
    
    msg = await message.answer(t(user_id, "searching"), parse_mode="HTML")
    results = await generate_and_find_free(prefix=prefix, length=len(prefix) + 3, count=2)
    
    search_id = str(uuid.uuid4())[:6].upper()
    search_results_cache[search_id] = results
    
    if not results:
        await msg.edit_text(t(user_id, "search_none"), reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    formatted = [f"🔹 <code>{u}</code>" for u in results]
    text = t(user_id, "search_results", search_id=search_id, results="\n".join(formatted))
    
    buttons = [[InlineKeyboardButton(text=f"🔗 {u}", url=f"https://t.me/{u.lstrip('@')}")] for u in results]
    buttons.append([InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")])
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.message(BotStates.exact_search)
async def process_exact_search(message: Message, state: FSMContext):
    user_id = message.from_user.id
    uname = message.text.strip().lstrip("@")
    await state.clear()
    
    is_free = await check_single_username(uname)
    status_str = "🟢 Вільний / Доступний" if is_free else "🔴 Зайнятий"
    
    text = (
        f"🎯 <b>Результат перевірки:</b>\n─────────────────────\n"
        f"🔹 <b>Юзернейм:</b> <code>@{uname}</code>\n"
        f"📊 <b>Статус:</b> {status_str}\n"
        f"🔗 <b>Посилання:</b> <a href='https://t.me/{uname}'>t.me/{uname}</a>"
    )
    await message.answer(text, reply_markup=back_keyboard(user_id), parse_mode="HTML", disable_web_page_preview=True)

@dp.message(BotStates.smart_variations)
async def process_smart_variations(message: Message, state: FSMContext):
    user_id = message.from_user.id
    base = message.text.strip().lstrip("@")
    await state.clear()
    
    msg = await message.answer(t(user_id, "searching"), parse_mode="HTML")
    variations = [f"the_{base}", f"{base}x", f"real_{base}", f"{base}hq", f"{base}_dev"]
    
    free_found = []
    for var in variations:
        if await check_single_username(var):
            free_found.append(f"@{var}")
            
    if not free_found:
        await msg.edit_text(t(user_id, "search_none"), reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return
        
    formatted = [f"🔹 <code>{u}</code>" for u in free_found]
    text = f"🧠 <b>Знайдені вільні варіації:</b>\n─────────────────────\n" + "\n".join(formatted)
    await msg.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
