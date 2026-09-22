import asyncio
import html
import logging
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta
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

# 1. Налаштування логування (Технічні проблеми окремо у файл errors.log)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("errors.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.error("BOT_TOKEN is missing!")

bot = Bot(token=BOT_TOKEN if BOT_TOKEN else "DUMMY_TOKEN")
dp = Dispatcher()

ADMIN_ID = 5619415334  # Твій адміністративний ID
USERNAME_PATTERN = re.compile(f"^[A-Za-z][A-Za-z0-9_]{{4,31}}$")

# --- ІНІЦІАЛІЗАЦІЯ БАЗИ ДАНИХ ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    # Таблиця користувачів
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'en',
            checks_count INTEGER DEFAULT 0,
            last_active TEXT
        )
    """)
    
    # Таблиця банів
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            ban_until TEXT
        )
    """)
    
    # Таблиця збережених тегів
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            UNIQUE(user_id, username)
        )
    """)
    
    # Таблиця історії пошуку
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            searched_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# --- РОБОТА З БАЗОЮ ДАНИХ (Helper функції) ---
def get_user_profile(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT lang, checks_count FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not row:
        cursor.execute("INSERT INTO users (user_id, lang, checks_count, last_active) VALUES (?, 'en', 0, ?)", (user_id, now))
        conn.commit()
        lang, checks_count = 'en', 0
    else:
        lang, checks_count = row
        cursor.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (now, user_id))
        conn.commit()
        
    conn.close()
    return {"lang": lang, "checks_count": checks_count}

def update_user_lang(user_id: int, lang: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def increment_checks(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET checks_count = checks_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_user_banned(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT reason, ban_until FROM bans WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return False, ""
    reason, ban_until = row
    if ban_until != "forever":
        try:
            if datetime.now() > datetime.strptime(ban_until, "%Y-%m-%d %H:%M:%S"):
                # Бан минув — видаляємо
                unban_user(user_id)
                return False, ""
        except Exception:
            pass
    return True, reason

def ban_user(user_id: int, reason: str, duration_days: int = 0):
    if duration_days > 0:
        ban_until = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
    else:
        ban_until = "forever"
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO bans (user_id, reason, ban_until) VALUES (?, ?, ?)", (user_id, reason, ban_until))
    conn.commit()
    conn.close()

def unban_user(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_to_history(user_id: int, username: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO search_history (user_id, username, searched_at) VALUES (?, ?, ?)", (user_id, username, now))
    conn.commit()
    conn.close()

# Автоматичне очищення старих даних (історія старша за 14 днів)
def cleanup_old_data():
    try:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        limit_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM search_history WHERE searched_at < ?", (limit_date,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Cleanup error: {e}")

LANGS = {
    "en": {
        "welcome": "<b>Welcome back, {name}!</b>\n\nSelect an option from the menu below:",
        "btn_auto": "⚡ Auto Search",
        "btn_saved": "☆ Saved Tags",
        "btn_history": "⏱ History",
        "btn_updates": "✨ Updates №05 (Pro)",
        "btn_lang": "🌐 Language: EN / UA",
        "btn_help": "🛡 Help & Info",
        "back": "‹ Back",
        "main_menu": "⌂ Main Menu",
        "auto_title": "⚡ <b>Auto Search</b>\n\nChoose the desired username length (5 to 11 characters):",
        "help_text": "🛡 <b>Help & Instructions</b>\n\n1. Use <b>Auto Search</b> to find available usernames instantly.\n2. Save your favorite tags using the star button.",
        "updates_text": "✨ <b>Updates №05 (Pro Database Edition)</b>\n\n• Integrated SQLite database.\n• Advanced Admin panel with analytics & bans.",
        "len_prompt": "⚡ <b>Auto Search</b>\n\nSelected length: <code>{length}</code> chars.\nDo you want to include digits?",
        "digits_yes": "☑ With Digits",
        "digits_no": "☒ Letters Only",
        "dcount_prompt": "⚡ <b>Auto Search</b>\n\nLength: <code>{length}</code> characters.\nHow many digits would you like to include?",
        "scan_nodig": "⌕ Scanning {length}-char username...",
        "scan_dig": "⌕ Scanning username ({length} chars, {d_count} digits)...",
        "err_not_found": "⚠ <b>No Results Found</b>\n\nCould not find available usernames right now. Try again!",
        "res_title": "💎 <b>AVAILABLE USERNAME FOUND</b>\n\n◌ Username: <code>{username}</code>\n◌ Length: {length}\n◌ Status: Free\n",
        "btn_open": "↗ Open Link",
        "btn_save": "☆ Save",
        "btn_retry": "↻ Try Again",
        "saved_success": "Successfully saved {uname}!",
        "saved_already": "This tag is already in your saved list.",
        "saved_empty": "☆ <b>Saved Tags</b>\n\nYour saved list is empty.",
        "saved_title": "☆ <b>Saved Tags</b>\n\n",
        "history_empty": "⏱ <b>Search History</b>\n\nYour history is empty.",
        "history_title": "⏱ <b>Search History</b>\n\n",
        "lang_changed": "Language switched to English."
    },
    "uk": {
        "welcome": "<b>Вітаю, {name}!</b>\n\nОберіть потрібну дію в меню нижче:",
        "btn_auto": "⚡ Автоматичний пошук",
        "btn_saved": "☆ Збережені теги",
        "btn_history": "⏱ Історія",
        "btn_updates": "✨ Оновлення №05 (Pro)",
        "btn_lang": "🌐 Мова: UA / EN",
        "btn_help": "🛡 Довідка",
        "back": "‹ Назад",
        "main_menu": "⌂ Головне меню",
        "auto_title": "⚡ <b>Автоматичний пошук</b>\n\nОберіть бажану довжину нікнейма (від 5 до 11 символів):",
        "help_text": "🛡 <b>Довідка та інструкція</b>\n\n1. Використовуйте <b>Автопошук</b> для швидкого знаходження вільних імен.\n2. Зберігайте улюблені варіанти.",
        "updates_text": "✨ <b>Оновлення №05 (Pro Database Edition)</b>\n\n• Інтегровано повноцінну SQLite базу даних.\n• Потужна адмін-панель з розсилками, банами та аналітикою.",
        "len_prompt": "⚡ <b>Автоматичний пошук</b>\n\nОбрана довжина: <code>{length}</code> симв.\nЧи використовувати цифри у назві?",
        "digits_yes": "☑ З цифрами",
        "digits_no": "☒ Тільки букви",
        "dcount_prompt": "⚡ <b>Автоматичний пошук</b>\n\nДовжина: <code>{length}</code> символів.\nСкільки цифр бажаєте додати?",
        "scan_nodig": "⌕ Сканування імені з {length} символів...",
        "scan_dig": "⌕ Сканування імені ({length} символів, {d_count} цифр)...",
        "err_not_found": "⚠ <b>Нічого не знайдено</b>\n\nЗа заданими параметрами вільних імен зараз немає. Спробуйте ще раз!",
        "res_title": "💎 <b>ВІЛЬНИЙ ЮЗЕРНЕЙМ ЗНАЙДЕНО</b>\n\n◌ Ім'я: <code>{username}</code>\n◌ Довжина: {length}\n◌ Статус: Вільний\n",
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
    waiting_broadcast = State()
    waiting_ban = State()

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
        [InlineKeyboardButton(text=t(user_id, "btn_retry"), callback_data=retry_callback)],
        [InlineKeyboardButton(text=t(user_id, "main_menu"), callback_data="nav:main")]
    ])

async def check_single_username(session: aiohttp.ClientSession, username: str) -> bool:
    username = username.lstrip("@").strip()
    if not USERNAME_PATTERN.match(username):
        return False
    url = f"https://t.me/{username}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with session.get(url, headers=headers, allow_redirects=True) as resp:
            if resp.status != 200:
                return False
            text = await resp.text()
            if any(marker in text for marker in ["is available on Telegram", "you can set up", "username is not taken", "WebApp", "tgme_username_link"]):
                if "tgme_page_title" in text and "is available" not in text:
                    return False
                return True
            return False
    except Exception as e:
        logging.error(f"Network check error for {username}: {e}")
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
    return t(user_id, "res_title", username=username, length=length)

async def send_main_menu(message_or_callback, user_id: int, edit: bool = True):
    name = html.escape(message_or_callback.from_user.first_name)
    text = t(user_id, "welcome", name=name)
    markup = main_keyboard(user_id)
    if edit:
        await message_or_callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message_or_callback.answer(text, reply_markup=markup, parse_mode="HTML")

# --- ПЕРЕВІРКА НА БАН ПЕРЕД КОЖНИМ ПОВІДОМЛЕННЯМ ---
@dp.message.middleware()
async def ban_middleware(handler, event, data):
    if event.from_user:
        banned, reason = is_user_banned(event.from_user.id)
        if banned:
            await event.answer(f"⛔ Ви заблоковані в цьому боті.\nПричина: {reason}")
            return
    return await handler(event, data)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    get_user_profile(user_id)
    await send_main_menu(message, user_id, edit=False)

# --- АДМІН-ПАНЕЛЬ ТА ІНСТРУМЕНТИ ---
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_active LIKE ?", (f"{today}%",))
    dau = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(checks_count) FROM users")
    total_checks = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM bans")
    total_bans = cursor.fetchone()[0]
    conn.close()
    
    admin_text = (
        "🛡 <b>Pro Адмін-панель</b>\n\n"
        f"👥 Всього користувачів: <code>{total_users}</code>\n"
        f"🔥 DAU (актив за сьогодні): <code>{dau}</code>\n"
        f"📊 Всього перевірок: <code>{total_checks}</code>\n"
        f"⛔ Заблоковано користувачів: <code>{total_bans}</code>\n\n"
        "<b>Команди управління:</b>\n"
        "• /broadcast [текст] — розсилка\n"
        "• /ban [id] [днів (0=навжди)] [причина] — бан\n"
        "• /unban [id] — розблокування\n"
        "• /backup — завантажити файл бази"
    )
    await message.answer(admin_text, parse_mode="HTML")

@dp.message(Command("backup"))
async def cmd_backup(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if os.path.exists("bot_database.db"):
        file = BufferedInputFile.from_file("bot_database.db", filename="bot_database.db")
        await message.answer_document(file, caption="📁 Бекап бази даних SQLite")
    else:
        await message.answer("⚠ Файл бази не знайдено.")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        await message.answer("Формат: `/ban user_id дні причина`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        days = int(args[2])
        reason = args[3] if len(args) > 3. else "Порушення правил"
        ban_user(target_id, reason, days)
        await message.answer(f"✅ Користувача `{target_id}` заблоковано.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"Помилка: {e}")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        return
    target_id = int(args[1])
    unban_user(target_id)
    await message.answer(f"✅ Користувача `{target_id}` розблоковано.")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Введіть текст для розсилки.")
        return
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    sent = 0
    for (u_id,) in users:
        try:
            await bot.send_message(u_id, f"📢 <b>Оголошення:</b>\n\n{text}", parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Розсилку завершено. Успішно надіслано: {sent} користувачам.")

# --- CALLBA
