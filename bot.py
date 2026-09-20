import asyncio
import html
import logging
import random
import re
import aiohttp
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
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
    format="%(asctime)s | %(levelname)s | %(message)s",
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 0  # <--- Впишіть сюди ваш Telegram ID, щоб отримувати відгуки!

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher()

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

user_data_store = {}
monitored_usernames = {}
global_stats = {
    "total_checked": 0,
    "total_available": 0,
    "unique_users": set(),
}

# --- TRANSLATIONS ---
TEXTS = {
    "en": {
        "welcome": "👋 <b>Welcome, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — automated Telegram username finder & monitor.\n\n👇 <i>Select an option below:</i>",
        "btn_search": "🔍 Auto-Search Free",
        "btn_mon": "🔔 Monitor",
        "btn_saved": "⭐ Saved Usernames",
        "btn_feedback": "💬 Leave Feedback",
        "btn_settings": "Change Language 🌍",
        "btn_help": "ℹ️ Help",
        "btn_back": "« Back to Menu",
        "search_prompt": "🔍 <b>Auto-Search Usernames</b>\n─────────────────────\nSelect the desired username length (from 5 to 32 characters):",
        "type_prompt": "⚙️ <b>Username Content</b>\n─────────────────────\nDo you want usernames with numbers or letters only?",
        "btn_letters": "Letters Only 🔤",
        "btn_numbers": "With Numbers 🔢",
        "searching": "🔍 Searching for free usernames (Length: <b>{length}</b>)... Please wait ⏳",
        "search_results": "🎉 <b>Found Free Usernames (Length {length}):</b>\n─────────────────────\n{results}\n\n<i>Click the buttons below to open, save, or load more!</i>",
        "search_none": "❌ No free usernames found in this batch. Try again!",
        "btn_more": "🔄 Load More (2)",
        "mon_prompt": "🔔 <b>Monitoring</b>\n─────────────────────\nSend a taken username to track:",
        "mon_success": "✅ <b>Monitoring started for <code>{username}</code>!</b>\nWe will notify you immediately once it becomes available.",
        "saved_title": "⭐ <b>Your Saved Usernames:</b>\n─────────────────────\n{list}",
        "saved_empty": "⭐ You don't have any saved usernames yet.",
        "btn_save_prefix": "⭐ Save ",
        "saved_success": "✅ Username <b>{username}</b> successfully saved!",
        "feedback_prompt": "💬 <b>Feedback</b>\n─────────────────────\nPlease send your feedback or suggestions about the bot in the next message:",
        "feedback_success": "✅ Thank you! Your feedback has been successfully sent to the administration.",
        "help_text": "ℹ️ <b>Help</b>\n═════════════════════\nThis bot automatically generates and scans for available Telegram usernames based on your criteria.",
        "lang_changed": "Language successfully changed to English! ✅",
    },
    "ua": {
        "welcome": "👋 <b>Вітаємо, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — автоматичний пошук та моніторинг вільних юзернеймів.\n\n👇 <i>Оберіть розділ:</i>",
        "btn_search": "🔍 Авто-пошук вільних",
        "btn_mon": "🔔 Моніторинг",
        "btn_saved": "⭐ Збережені",
        "btn_feedback": "💬 Залишити відгук",
        "btn_settings": "Зміна мови 🌍",
        "btn_help": "ℹ️ Довідка",
        "btn_back": "« Повернутися в меню",
        "search_prompt": "🔍 <b>Авто-пошук юзернеймів</b>\n─────────────────────\nОберіть бажану кількість символів (від 5 до 32):",
        "type_prompt": "⚙️ <b>Вміст юзернейму</b>\n─────────────────────\nБажаєте шукати з цифрами чи лише букви?",
        "btn_letters": "Лише букви 🔤",
        "btn_numbers": "З цифрами 🔢",
        "searching": "🔍 Шукаємо вільні юзернейми (Довжина: <b>{length}</b>)... Зачекайте⏳",
        "search_results": "🎉 <b>Знайдені вільні юзернейми (Довжина {length}):</b>\n─────────────────────\n{results}\n\n<i>Натисніть на кнопки нижче, щоб відкрити, зберегти або знайти ще!</i>",
        "search_none": "❌ У цій спробі вільних юзернеймів не знайдено. Спробуйте ще раз!",
        "btn_more": "🔄 Більше (2)",
        "mon_prompt": "🔔 <b>Моніторинг</b>\n─────────────────────\nВведіть зайнятий юзернейм:",
        "mon_success": "✅ <b>Моніторинг для <code>{username}</code> активовано!</b>\nМи повідомимо вас одразу, як тільки він звільниться.",
        "saved_title": "⭐ <b>Ваші збережені юзернейми:</b>\n─────────────────────\n{list}",
        "saved_empty": "⭐ У вас поки немає збережених юзернеймів.",
        "btn_save_prefix": "⭐ Зберегти ",
        "saved_success": "✅ Юзернейм <b>{username}</b> успішно збережено!",
        "feedback_prompt": "💬 <b>Відгук</b>\n─────────────────────\nНапишіть ваш відгук або пропозицію щодо роботи бота у наступному повідомленні:",
        "feedback_success": "✅ Дякуємо! Ваш відгук успішно надіслано адміністрації.",
        "help_text": "ℹ️ <b>Довідка</b>\n═════════════════════\nБот автоматично генерує та перевіряє вільні Telegram юзернейми.",
        "lang_changed": "Мову успішно змінено на українську! ✅",
    },
    "de": {
        "welcome": "👋 <b>Willkommen, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — Automatisierte Benutzernamen-Suche.\n\n👇 <i>Wählen Sie eine Option:</i>",
        "btn_search": "🔍 Freie Suchen",
        "btn_mon": "🔔 Überwachen",
        "btn_saved": "⭐ Gespeichert",
        "btn_feedback": "💬 Feedback",
        "btn_settings": "Sprache ändern 🌍",
        "btn_help": "ℹ️ Hilfe",
        "btn_back": "« Zurück zum Menü",
        "search_prompt": "🔍 <b>Benutzernamen-Suche</b>\n─────────────────────\nWählen Sie die Länge (5 bis 32 Zeichen):",
        "type_prompt": "⚙️ <b>Inhalt</b>\n─────────────────────\nNur Buchstaben oder mit Zahlen?",
        "btn_letters": "Nur Buchstaben 🔤",
        "btn_numbers": "Mit Zahlen 🔢",
        "searching": "🔍 Suche nach freien Namen (Länge: <b>{length}</b>)...",
        "search_results": "🎉 <b>Ergebnisse (Länge {length}):</b>\n─────────────────────\n{results}",
        "search_none": "❌ Keine freien Benutzernamen gefunden.",
        "btn_more": "🔄 Mehr (2)",
        "mon_prompt": "🔔 <b>Überwachung</b>\n─────────────────────\nBesetzten Benutzernamen eingeben:",
        "mon_success": "✅ <b>Überwachung für <code>{username}</code> gestartet!</b>",
        "saved_title": "⭐ <b>Gespeicherte Namen:</b>\n─────────────────────\n{list}",
        "saved_empty": "⭐ Keine gespeicherten Namen.",
        "btn_save_prefix": "⭐ Speichern ",
        "saved_success": "✅ <b>{username}</b> gespeichert!",
        "feedback_prompt": "💬 <b>Feedback</b>\n─────────────────────\nSenden Sie Ihr Feedback:",
        "feedback_success": "✅ Danke! Gesendet.",
        "help_text": "ℹ️ <b>Hilfe</b>\n═════════════════════\nAutomatische Suche.",
        "lang_changed": "Sprache zu Deutsch geändert! ✅",
    },
    "zh": {
        "welcome": "👋 <b>欢迎, {name}!</b>\n═════════════════════\n<b>USERNAME FIX</b> — 自动用户名搜索与监控。\n\n👇 <i>请选择：</i>",
        "btn_search": "🔍 自动搜索空闲",
        "btn_mon": "🔔 监控",
        "btn_saved": "⭐ 已保存",
        "btn_feedback": "💬 留下反馈",
        "btn_settings": "更改语言 🌍",
        "btn_help": "ℹ️ 帮助",
        "btn_back": "« 返回菜单",
        "search_prompt": "🔍 <b>自动搜索用户名</b>\n─────────────────────\n选择字符长度（5 到 32）：",
        "type_prompt": "⚙️ <b>用户名类型</b>\n─────────────────────\n您希望包含数字还是仅字母？",
        "btn_letters": "仅字母 🔤",
        "btn_numbers": "含数字 🔢",
        "searching": "🔍 正在搜索 (长度: <b>{length}</b>)...",
        "search_results": "🎉 <b>搜索结果 (长度 {length}):</b>\n─────────────────────\n{results}",
        "search_none": "❌ 未找到空闲用户名，请重试！",
        "btn_more": "🔄 更多 (2)",
        "mon_prompt": "🔔 <b>监控</b>\n─────────────────────\n输入要监控的用户名：",
        "mon_success": "✅ <b>已开始监控 <code>{username}</code>！</b>",
        "saved_title": "⭐ <b>已保存的用户名:</b>\n─────────────────────\n{list}",
        "saved_empty": "⭐ 暂无保存的用户名。",
        "btn_save_prefix": "⭐ 保存 ",
        "saved_success": "✅ <b>{username}</b> 保存成功！",
        "feedback_prompt": "💬 <b>反馈</b>\n─────────────────────\n请发送您的反馈：",
        "feedback_success": "✅ 谢谢！已发送。",
        "help_text": "ℹ️ <b>帮助</b>\n═════════════════════\n自动为您生成并检测可用的 Telegram 用户名。",
        "lang_changed": "语言已更改为中文！ ✅",
    }
}

def get_user_profile(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "lang": "en",
            "saved": [],
            "temp_length": 5,
            "temp_use_numbers": True,
        }
    global_stats["unique_users"].add(user_id)
    return user_data_store[user_id]

def t(user_id: int, key: str, **kwargs) -> str:
    profile = get_user_profile(user_id)
    lang = profile.get("lang", "en")
    if lang not in TEXTS:
        lang = "en"
    template = TEXTS[lang].get(key, TEXTS["en"].get(key, ""))
    return template.format(**kwargs)

class BotStates(StatesGroup):
    auto_search = State()
    monitor_username = State()
    waiting_feedback = State()

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_search"), callback_data="menu:search")],
            [
                InlineKeyboardButton(text=t(user_id, "btn_mon"), callback_data="menu:monitor"),
                InlineKeyboardButton(text=t(user_id, "btn_saved"), callback_data="menu:saved"),
            ],
            [
                InlineKeyboardButton(text=t(user_id, "btn_feedback"), callback_data="menu:feedback"),
                InlineKeyboardButton(text=t(user_id, "btn_settings"), callback_data="menu:settings"),
            ],
            [InlineKeyboardButton(text=t(user_id, "btn_help"), callback_data="menu:help")],
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

def type_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_letters"), callback_data="type:letters")],
            [InlineKeyboardButton(text=t(user_id, "btn_numbers"), callback_data="type:numbers")],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

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
                    if "If you have Telegram, you can contact" in text or "View in Telegram" in text or "tgme_user" in text or "tgme_channel" in text:
                        return False
                if "If you have Telegram, you can set up" in text or "is available on Telegram" in text:
                    return True
                if resp.status == 200 and "tgme_page" in text and "tgme_page_photo" not in text:
                    return True
                return False
    except Exception:
        return None

def analyze_username(username: str, lang: str = "en"):
    clean = username.lstrip("@")
    has_nums = bool(re.search(r"\d", clean))
    
    if lang == "ua":
        nums_str = "З цифрами 🔢" if has_nums else "Лише букви 🔤"
        first_char = clean[0].lower()
        is_vowel = first_char in "aeiou"
        letter_type = "Голосна" if is_vowel else "Приголосна"
    elif lang == "de":
        nums_str = "Mit Zahlen 🔢" if has_nums else "Nur Buchstaben 🔤"
        first_char = clean[0].lower()
        is_vowel = first_char in "aeiou"
        letter_type = "Vokal" if is_vowel else "Konsonant"
    elif lang == "zh":
        nums_str = "含数字 🔢" if has_nums else "仅字母 🔤"
        first_char = clean[0].lower()
        is_vowel = first_char in "aeiou"
        letter_type = "元音" if is_vowel else "辅音"
    else:
        nums_str = "With numbers 🔢" if has_nums else "Letters only 🔤"
        first_char = clean[0].lower()
        is_vowel = first_char in "aeiou"
        letter_type = "Vowel" if is_vowel else "Consonant"
    
    length = len(clean)
    if length == 5 and not has_nums:
        rating = "5/5 ⭐⭐⭐⭐⭐"
        price = "100 - 300 TON ($250 - $700)"
    elif length == 6 and not has_nums:
        rating = "4.5/5 ⭐⭐⭐⭐✨"
        price = "30 - 90 TON ($70 - $200)"
    elif not has_nums:
        rating = "4/5 ⭐⭐⭐⭐"
        price = "10 - 30 TON ($25 - $70)"
    else:
        rating = "3/5 ⭐⭐⭐"
        price = "1 - 8 TON ($3 - $20)"
        
    return nums_str, letter_type, rating, price

async def generate_and_find_free(length: int, use_numbers: bool, count: int = 2) -> list:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789_" if use_numbers else "abcdefghijklmnopqrstuvwxyz_"
    free_found = []
    attempts = 0
    while len(free_found) < count and attempts < 40:
        attempts += 1
        first_char = random.choice("abcdefghijklmnopqrstuvwxyz")
        remaining = "".join(random.choice(chars) for _ in range(length - 1))
        candidate = first_char + remaining
        
        if candidate in [f.lstrip("@") for f in free_found]:
            continue
            
        is_free = await check_single_username(candidate)
        if is_free is True:
            free_found.append(f"@{candidate}")
        await asyncio.sleep(0.1)
    return free_found

@dispatcher.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    name = html.escape(message.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await message.answer(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")

@dispatcher.callback_query(F.data.startswith("menu:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    if action == "main":
        name = html.escape(callback.from_user.first_name)
        text = t(user_id, "welcome", name=name)
        await callback.message.edit_text(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
    elif action == "search":
        await state.set_state(BotStates.auto_search)
        await callback.message.edit_text(t(user_id, "search_prompt"), reply_markup=length_keyboard(user_id), parse_mode="HTML")
    elif action == "monitor":
        await state.set_state(BotStates.monitor_username)
        await callback.message.edit_text(t(user_id, "mon_prompt"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "saved":
        profile = get_user_profile(user_id)
        saved_list = profile.get("saved", [])
        if not saved_list:
            saved_text = t(user_id, "saved_empty")
            markup = back_keyboard(user_id)
        else:
            # Виправлено синтаксичну помилку з лапками
            items = []
            for u in saved_list:
                clean_u = u.lstrip("@")
                items.append(f"🔹 <a href='https://t.me/{clean_u}'>{u}</a>")
            saved_text = t(user_id, "saved_title", list="\n".join(items))
            markup = back_keyboard(user_id)
        await callback.message.edit_text(saved_text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    elif action == "feedback":
        await state.set_state(BotStates.waiting_feedback)
        await callback.message.edit_text(t(user_id, "feedback_prompt"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "settings":
        await callback.message.edit_text("⚙️ <b>Language Selection</b>\n─────────────────────\nChoose your interface language:", reply_markup=settings_keyboard(user_id), parse_mode="HTML")
    elif action == "help":
        await callback.message.edit_text(t(user_id, "help_text"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    
    await callback.answer()

def settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang:en"),
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="setlang:ua"),
            ],
            [
                InlineKeyboardButton(text="🇩🇪 Deutsch", callback_data="setlang:de"),
                InlineKeyboardButton(text="🇨🇳 中文", callback_data="setlang:zh"),
            ],
            [InlineKeyboardButton(text=t(user_id, "btn_back"), callback_data="menu:main")],
        ]
    )

@dispatcher.callback_query(F.data.startswith("setlang:"))
async def set_lang_callback(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    get_user_profile(user_id)["lang"] = lang
    
    name = html.escape(callback.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    await callback.message.edit_text(text, reply_markup=main_keyboard(user_id), parse_mode="HTML")
    await callback.answer(t(user_id, "lang_changed"))

@dispatcher.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    get_user_profile(user_id)["temp_length"] = length
    
    await callback.message.edit_text(t(user_id, "type_prompt"), reply_markup=type_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

@dispatcher.callback_query(F.data.startswith("type:"))
async def type_selected_callback(callback: CallbackQuery):
    choice = callback.data.split(":")[1]
    user_id = callback.from_user.id
    profile = get_user_profile(user_id)
    
    profile["temp_use_numbers"] = (choice == "numbers")
    length = profile.get("temp_length", 5)
    lang = profile.get("lang", "en")
    
    await callback.message.edit_text(t(user_id, "searching", length=length), parse_mode="HTML")
    
    free_list = await generate_and_find_free(length, profile["temp_use_numbers"], count=2)
    
    if not free_list:
        text = t(user_id, "search_none")
        markup = length_keyboard(user_id)
    else:
        results_formatted = []
        keyboard_buttons = []
        for uname in free_list:
            nums, l_type, rating, price = analyze_username(uname, lang)
            results_formatted.append(
                f"🔹 <code>{uname}</code>\n"
                f"   • Type: {nums} | {l_type}\n"
                f"   • Rating: {rating}\n"
                f"   • Est. Price: <b>{price}</b>"
            )
            keyboard_buttons.append([
                InlineKeyboardButton(text=f"🔗 Open {uname}", url=f"https://t.me/{uname.lstrip('@')}"),
                InlineKeyboardButton(text=f"{t(user_id, 'btn_save_prefix')}{uname}", callback_data=f"save:{uname}")
            ])
        
        keyboard_buttons.append([InlineKeyboardButton(text=t(user_id, "btn_more"), callback_data=f"len:
