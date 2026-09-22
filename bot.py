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

ADMIN_ID = 5619415334
USERNAME_PATTERN = re.compile(f"^[A-Za-z][A-Za-z0-9_]{{4,31}}$")

# --- ІНІЦІАЛІЗАЦІЯ БАЗИ ДАНИХ ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'en',
            checks_count INTEGER DEFAULT 0,
            last_active TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            ban_until TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            UNIQUE(user_id, username)
        )
    """)
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
                unban_user(user_id)
                return False, ""
        except Exception:
            pass
    return True, reason

def ban_user(user_id: int, reason: str, duration_days: int = 0):
    ban_until = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S") if duration_days > 0 else "forever"
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
        "btn_updates": "✨ Updates №05",
        "btn_rules": "📜 Rules & Bans",
        "btn_lang": "🌐 Language: EN / UA",
        "btn_help": "🛡 Help & Info",
        "back": "‹ Back",
        "main_menu": "⌂ Main Menu",
        "auto_title": "⚡ <b>Auto Search</b>\n\nChoose the desired username length (5 to 11 characters):",
        "help_text": "🛡 <b>Help & Instructions</b>\n\n1. Use <b>Auto Search</b> to find available usernames instantly.\n2. Save your favorite tags using the star button.",
        "rules_text": (
            "🛡 <b>Bot Rules & Ban Terms</b>\n\n"
            "To ensure a comfortable and stable service for everyone, please follow these guidelines. Violations may result in temporary or permanent suspension.\n\n"
            "❌ <b>What can get you banned:</b>\n"
            "1. <b>Spam & Flooding:</b> Artificially overloading the bot with automated requests/scripts.\n"
            "2. <b>Abuse:</b> Insulting administration, threats, or offensive language in feedback/support.\n"
            "3. <b>Fraud:</b> Using found usernames for malicious purposes (extortion, blackmail, selling tags).\n\n"
            "⏱ <b>Suspension Terms:</b>\n"
            "• <b>Warning / 1 Day:</b> Minor first-time offenses.\n"
            "• <b>7 – 30 Days:</b> Repeated violations or annoying spam.\n"
            "• <b>Forever:</b> Bot hacking attempts, severe DDoS, or fraud."
        ),
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
        "btn_updates": "✨ Оновлення №05",
        "btn_rules": "📜 Правила та бани",
        "btn_lang": "🌐 Мова: UA / EN",
        "btn_help": "🛡 Довідка",
        "back": "‹ Назад",
        "main_menu": "⌂ Головне меню",
        "auto_title": "⚡ <b>Автоматичний пошук</b>\n\nОберіть бажану довжину нікнейма (від 5 до 11 символів):",
        "help_text": "🛡 <b>Довідка та інструкція</b>\n\n1. Використовуйте <b>Автопошук</b> для швидкого знаходження вільних імен.\n2. Зберігайте улюблені варіанти.",
        "rules_text": (
            "🛡 <b>Правила та терміни блокування</b>\n\n"
            "Для забезпечення комфортної та стабільної роботи сервісу дотримуйтесь простих правил. Порушення тягне за собою бан.\n\n"
            "❌ <b>За що можна отримати бан:</b>\n"
            "1. <b>Спам і навантаження:</b> Штучне перевантаження бота масовими автоматизованими запитами.\n"
            "2. <b>Образи:</b> Образи адміністрації, погрози чи нецензурна лексика у підтримці.\n"
            "3. <b>Шахрайство:</b> Використання знайдених тегів у деструктивних цілях (вимагання грошей, шантаж).\n\n"
            "⏱ <b>Терміни блокування:</b>\n"
            "• <b>Попередження / 1 день:</b> За дрібні первинні порушення.\n"
            "• <b>7 – 30 днів:</b> За повторний спам чи неадекватну поведінку.\n"
            "• <b>Назавжди:</b> За спроби зламати бота, DDoS або шахрайство."
        ),
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

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id, "btn_auto"), callback_data="nav:auto")],
        [
            InlineKeyboardButton(text=t(user_id, "btn_saved"), callback_data="nav:view_saved"),
            InlineKeyboardButton(text=t(user_id, "btn_history"), callback_data="nav:view_history"),
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_updates"), callback_data="nav:updates"),
            InlineKeyboardButton(text=t(user_id, "btn_rules"), callback_data="nav:rules"),
        ],
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

# --- СТАРТ ТА ПЕРЕВІРКА БАНУ ---
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    banned, reason = is_user_banned(user_id)
    if banned:
        await message.answer(f"⛔ Ви заблоковані в цьому боті.\nПричина: {reason}")
        return
        
    await state.clear()
    get_user_profile(user_id)
    await send_main_menu(message, user_id, edit=False)

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
        reason = args[3] if len(args) > 3 else "Порушення правил"
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

# --- CALLBACK ОБРОБНИКИ НАВІГАЦІЇ ---
@dp.callback_query(F.data.startswith("nav:"))
async def menu_callbacks(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    banned, reason = is_user_banned(user_id)
    if banned:
        await callback.answer(f"⛔ Ви заблоковані: {reason}", show_alert=True)
        return

    await state.clear()
    action = callback.data.split(":")[1]
    profile = get_user_profile(user_id)
    
    if action == "main":
        await send_main_menu(callback, user_id, edit=True)
    elif action == "auto":
        await state.set_state(BotStates.auto_search)
        await callback.message.edit_text(t(user_id, "auto_title"), reply_markup=length_keyboard(user_id), parse_mode="HTML")
    elif action == "toggle_lang":
        new_lang = "uk" if profile["lang"] == "en" else "en"
        update_user_lang(user_id, new_lang)
        await send_main_menu(callback, user_id, edit=True)
        await callback.answer(t(user_id, "lang_changed"), show_alert=True)
        return
    elif action == "updates":
        await callback.message.edit_text(t(user_id, "updates_text"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "rules":
        await callback.message.edit_text(t(user_id, "rules_text"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "view_saved":
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM saved_tags WHERE user_id = ?", (user_id,))
        saved = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not saved:
            text = t(user_id, "saved_empty")
        else:
            items = [f"• <code>{u}</code>" for u in saved]
            text = t(user_id, "saved_title") + "\n".join(items)
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "view_history":
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM search_history WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,))
        history = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        if not history:
            text = t(user_id, "history_empty")
        else:
            items = [f"• <code>{u}</code>" for u in history]
            text = t(user_id, "history_title") + "\n".join(items)
        await callback.message.edit_text(text, reply_markup=back_keyboard(user_id), parse_mode="HTML")
    elif action == "help":
        await callback.message.edit_text(t(user_id, "help_text"), reply_markup=back_keyboard(user_id), parse_mode="HTML")
        
    await callback.answer()

@dp.callback_query(F.data.startswith("len:"))
async def length_selected_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if is_user_banned(user_id)[0]:
        return
    length = int(callback.data.split(":")[1])
    await callback.message.edit_text(t(user_id, "len_prompt", length=length), reply_markup=digits_choice_keyboard(user_id, length), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dig:"))
async def digits_choice_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    choice = parts[1]
    length = int(parts[2])
    user_id = callback.from_user.id
    if is_user_banned(user_id)[0]:
        return
    
    if choice == "yes":
        await callback.message.edit_text(t(user_id, "dcount_prompt", length=length), reply_markup=digits_count_keyboard(user_id, length), parse_mode="HTML")
    else:
        msg = await callback.message.edit_text(t(user_id, "scan_nodig", length=length), parse_mode="HTML")
        username = await generate_and_find_free(user_id=user_id, target_length=length, use_digits=False)
        
        increment_checks(user_id)
        if username:
            add_to_history(user_id, username)
        
        if not username:
            await msg.edit_text(t(user_id, "err_not_found"), reply_markup=main_keyboard(user_id), parse_mode="HTML")
            return

        clean_u = username.lstrip('@')
        await msg.edit_text(format_result_card(user_id, username), reply_markup=get_result_keyboard(user_id, clean_u, f"len:{length}"), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("dcount:"))
async def digits_count_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    length = int(parts[1])
    d_count = int(parts[2])
    user_id = callback.from_user.id
    if is_user_banned(user_id)[0]:
        return
    
    msg = await callback.message.edit_text(t(user_id, "scan_dig", length=length, d_count=d_count), parse_mode="HTML")
    username = await generate_and_find_free(user_id=user_id, target_length=length, use_digits=True, digits_count=d_count)
    
    increment_checks(user_id)
    if username:
        add_to_history(user_id, username)
    
    if not username:
        await msg.edit_text(t(user_id, "err_not_found"), reply_markup=main_keyboard(user_id), parse_mode="HTML")
        return

    clean_u = username.lstrip('@')
    await msg.edit_text(format_result_card(user_id, username), reply_markup=get_result_keyboard(user_id, clean_u, f"len:{length}"), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("save:"))
async def save_username_callback(callback: CallbackQuery):
    raw_uname = callback.data.split(":", 1)[1]
    uname = f"@{raw_uname.lstrip('@')}"
    user_id = callback.from_user.id
    
    try:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO saved_tags (user_id, username) VALUES (?, ?)", (user_id, uname))
        conn.commit()
        conn.close()
        await callback.answer(t(user_id, "saved_success", uname=uname), show_alert=True)
    except sqlite3.IntegrityError:
        await callback.answer(t(user_id, "saved_already"), show_alert=True)

async def background_cleanup_loop():
    while True:
        await asyncio.sleep(86400)
        cleanup_old_data()

async def main():
    cleanup_old_data()
    asyncio.create_task(background_cleanup_loop())
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Pro Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
