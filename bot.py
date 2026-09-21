import asyncio
import html
import logging
import os
import random
import re
import sqlite3
from contextlib import closing

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


# =========================================================
# CONFIG
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing!")

DB_PATH = "tag_track.db"

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]{4,31}$"
)

PART_PATTERN = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*$"
)

MAX_USERNAME_LENGTH = 32
MIN_USERNAME_LENGTH = 5

SEARCH_COUNT = 3
MAX_ATTEMPTS = 1000

HTTP_TIMEOUT = 5
REQUEST_DELAY = 0.05


# =========================================================
# BOT
# =========================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    with closing(get_db()) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT NOT NULL DEFAULT 'en',
                checks_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_usernames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                UNIQUE(user_id, username),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, username),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """
        )

        db.commit()


def ensure_user(user_id: int):
    with closing(get_db()) as db:
        db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, language, checks_count)
            VALUES (?, 'en', 0)
            """,
            (user_id,),
        )
        db.commit()


def get_user_profile(user_id: int) -> dict:
    ensure_user(user_id)

    with closing(get_db()) as db:
        user = db.execute(
            """
            SELECT user_id, language, checks_count
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        saved = db.execute(
            """
            SELECT username
            FROM saved_usernames
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()

        history = db.execute(
            """
            SELECT username
            FROM history
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (user_id,),
        ).fetchall()

    return {
        "user_id": user["user_id"],
        "lang": user["language"],
        "checks_count": user["checks_count"],
        "saved": [row["username"] for row in saved],
        "history": [row["username"] for row in history],
    }


def set_language(user_id: int, lang: str):
    if lang not in ("en", "ua"):
        return

    ensure_user(user_id)

    with closing(get_db()) as db:
        db.execute(
            """
            UPDATE users
            SET language = ?
            WHERE user_id = ?
            """,
            (lang, user_id),
        )
        db.commit()


def add_checks(user_id: int, count: int):
    if count <= 0:
        return

    ensure_user(user_id)

    with closing(get_db()) as db:
        db.execute(
            """
            UPDATE users
            SET checks_count = checks_count + ?
            WHERE user_id = ?
            """,
            (count, user_id),
        )
        db.commit()


def add_to_history(user_id: int, usernames: list[str]):
    if not usernames:
        return

    ensure_user(user_id)

    with closing(get_db()) as db:
        for username in usernames:
            db.execute(
                """
                INSERT OR IGNORE INTO history (user_id, username)
                VALUES (?, ?)
                """,
                (user_id, username),
            )

        # Keep only latest 20 entries
        db.execute(
            """
            DELETE FROM history
            WHERE user_id = ?
            AND id NOT IN (
                SELECT id
                FROM history
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 20
            )
            """,
            (user_id, user_id),
        )

        db.commit()


def save_username(user_id: int, username: str) -> bool:
    ensure_user(user_id)

    with closing(get_db()) as db:
        cursor = db.execute(
            """
            INSERT OR IGNORE INTO saved_usernames (user_id, username)
            VALUES (?, ?)
            """,
            (user_id, username),
        )

        db.commit()

        return cursor.rowcount > 0


# =========================================================
# FSM
# =========================================================

class BotStates(StatesGroup):
    auto_search = State()
    prefix_search = State()
    suffix_search = State()
    smart_variations = State()


# =========================================================
# KEYBOARDS
# =========================================================

def main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(user_id)
    lang = profile["lang"]

    if lang == "ua":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔍 Авто-пошук",
                        callback_data="menu:auto",
                    ),
                    InlineKeyboardButton(
                        text="🔤 Префікс / Суфікс",
                        callback_data="menu:prefix",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🧠 Розумні варіації",
                        callback_data="menu:smart",
                    ),
                    InlineKeyboardButton(
                        text="👤 Профіль та Збережені",
                        callback_data="menu:profile",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🌍 Мова",
                        callback_data="menu:settings",
                    ),
                    InlineKeyboardButton(
                        text="ℹ️ Довідка",
                        callback_data="menu:help",
                    ),
                ],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Auto-Search",
                    callback_data="menu:auto",
                ),
                InlineKeyboardButton(
                    text="🔤 Prefix / Suffix",
                    callback_data="menu:prefix",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧠 Smart Variations",
                    callback_data="menu:smart",
                ),
                InlineKeyboardButton(
                    text="👤 Profile & Saved",
                    callback_data="menu:profile",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🌍 Language",
                    callback_data="menu:settings",
                ),
                InlineKeyboardButton(
                    text="ℹ️ Help",
                    callback_data="menu:help",
                ),
            ],
        ]
    )


def back_keyboard(user_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(user_id)

    text = "« Назад" if profile["lang"] == "ua" else "« Back"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data="menu:main",
                )
            ]
        ]
    )


def length_keyboard(user_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(user_id)

    buttons = []
    row = []

    for length in range(5, 13):
        row.append(
            InlineKeyboardButton(
                text=str(length),
                callback_data=f"len:{length}",
            )
        )

        if len(row) == 4:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    back_text = "« Назад" if profile["lang"] == "ua" else "« Back"

    buttons.append(
        [
            InlineKeyboardButton(
                text=back_text,
                callback_data="menu:main",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def prefix_suffix_keyboard(user_id: int) -> InlineKeyboardMarkup:
    profile = get_user_profile(user_id)

    if profile["lang"] == "ua":
        prefix_text = "⬅️ Префікс"
        suffix_text = "Суфікс ➡️"
        back_text = "« Назад"
    else:
        prefix_text = "⬅️ Prefix"
        suffix_text = "Suffix ➡️"
        back_text = "« Back"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=prefix_text,
                    callback_data="ps:prefix",
                ),
                InlineKeyboardButton(
                    text=suffix_text,
                    callback_data="ps:suffix",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=back_text,
                    callback_data="menu:main",
                )
            ],
        ]
    )


def result_keyboard(
    user_id: int,
    results: list[str],
) -> InlineKeyboardMarkup:

    profile = get_user_profile(user_id)
    lang = profile["lang"]

    buttons = []

    for username in results:
        clean = username.lstrip("@")

        save_text = (
            "⭐ Save"
            if lang == "en"
            else "⭐ Зберегти"
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🔗 {username}",
                    url=f"https://t.me/{clean}",
                ),
                InlineKeyboardButton(
                    text=save_text,
                    callback_data=f"save:{clean}",
                ),
            ]
        )

    back_text = "« Back" if lang == "en" else "« Назад"

    buttons.append(
        [
            InlineKeyboardButton(
                text=back_text,
                callback_data="menu:main",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =========================================================
# USERNAME VALIDATION
# =========================================================

def clean_username(value: str) -> str:
    return value.strip().lstrip("@").lower()


def is_valid_username(username: str) -> bool:
    return bool(USERNAME_PATTERN.fullmatch(username))


def is_valid_part(value: str) -> bool:
    return bool(PART_PATTERN.fullmatch(value))


# =========================================================
# TELEGRAM USERNAME CHECK
# =========================================================

async def check_single_username(
    session: aiohttp.ClientSession,
    username: str,
) -> bool | None:

    username = clean_username(username)

    if not is_valid_username(username):
        return None

    url = f"https://t.me/{username}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with session.get(
            url,
            headers=headers,
            allow_redirects=True,
        ) as response:

            if response.status == 429:
                logging.warning(
                    "Telegram returned HTTP 429 for @%s",
                    username,
                )
                return None

            if response.status != 200:
                return None

            text = await response.text()

            lower_text = text.lower()

            # Page indicating an existing Telegram entity
            taken_markers = [
                "tgme_page_title",
                "tgme_page_extra",
                "tgme_page_photo",
                "tgme_page_additional",
                "view in telegram",
            ]

            # Page indicating availability
            available_markers = [
                "is available on telegram",
                "username is not taken",
                "you can set up",
            ]

            if any(marker in lower_text for marker in available_markers):
                return True

            if any(marker in lower_text for marker in taken_markers):
                return False

            return None

    except asyncio.TimeoutError:
        logging.warning(
            "Timeout while checking @%s",
            username,
        )
        return None

    except aiohttp.ClientError as error:
        logging.warning(
            "HTTP error while checking @%s: %s",
            username,
            error,
        )
        return None

    except Exception as error:
        logging.exception(
            "Unexpected error while checking @%s: %s",
            username,
            error,
        )
        return None


# =========================================================
# USERNAME GENERATION
# =========================================================

def generate_random_part(length: int) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    chars = "abcdefghijklmnopqrstuvwxyz0123456789_"

    if length <= 0:
        return ""

    # First character must be a letter.
    result = random.choice(letters)

    for _ in range(length - 1):
        result += random.choice(chars)

    return result


def build_random_username(
    total_length: int,
    prefix: str = "",
    suffix: str = "",
) -> str | None:

    prefix = clean_username(prefix)
    suffix = clean_username(suffix)

    remaining = total_length - len(prefix) - len(suffix)

    if remaining < 1:
        return None

    random_part = generate_random_part(remaining)

    username = (
        f"{prefix}{random_part}{suffix}"
    ).lower()

    if len(username) > MAX_USERNAME_LENGTH:
        return None

    if not is_valid_username(username):
        return None

    return username


async def generate_and_find_free(
    message_to_edit: Message,
    lang: str,
    prefix: str = "",
    suffix: str = "",
    length: int = 5,
    count: int = 3,
) -> tuple[list[str], int]:

    free_found = []
    checked = set()

    attempts = 0

    steps = (
        [
            ("🔍 Починаємо пошук... 10%", 10),
            ("⚙️ Генеруємо комбінації... 30%", 30),
            ("🌐 Перевіряємо Telegram... 50%", 50),
            ("🔎 Відсіюємо зайняті юзи... 70%", 70),
            ("🔥 Майже знайшли... 90%", 90),
        ]
        if lang == "ua"
        else
        [
            ("🔍 Starting search... 10%", 10),
            ("⚙️ Generating combinations... 30%", 30),
            ("🌐 Checking Telegram... 50%", 50),
            ("🔎 Filtering taken usernames... 70%", 70),
            ("🔥 Almost there... 90%", 90),
        ]
    )

    step_index = 0

    timeout = aiohttp.ClientTimeout(
        total=HTTP_TIMEOUT
    )

    connector = aiohttp.TCPConnector(
        limit=5,
    )

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
    ) as session:

        while (
            len(free_found) < count
            and attempts < MAX_ATTEMPTS
        ):
            attempts += 1

            if (
                attempts % 100 == 0
                and step_index < len(steps)
            ):
                text, _ = steps[step_index]

                try:
                    await message_to_edit.edit_text(
                        text,
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

                step_index += 1

            candidate = build_random_username(
                total_length=length,
                prefix=prefix,
                suffix=suffix,
            )

            if not candidate:
                continue

            if candidate in checked:
                continue

            checked.add(candidate)

            result = await check_single_username(
                session,
                candidate,
            )

            if result is True:
                free_found.append(
                    f"@{candidate}"
                )

            await asyncio.sleep(
                REQUEST_DELAY
            )

    return free_found, attempts


# =========================================================
# START
# =========================================================

@dp.message(Command("start"))
async def cmd_start(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    user_id = message.from_user.id

    ensure_user(user_id)

    profile = get_user_profile(user_id)

    name = html.escape(
        message.from_user.first_name
        or "User"
    )

    if profile["lang"] == "ua":
        text = (
            f"👋 <b>Ласкаво просимо до Tag Track, "
            f"{name}!</b>\n\n"
            f"Оберіть дію в меню нижче:"
        )
    else:
        text = (
            f"👋 <b>Welcome to Tag Track, "
            f"{name}!</b>\n\n"
            f"Choose an action below:"
        )

    await message.answer(
        text,
        reply_markup=main_keyboard(user_id),
        parse_mode="HTML",
    )


# =========================================================
# MAIN MENU
# =========================================================

@dp.callback_query(
    F.data.startswith("menu:")
)
async def menu_callbacks(
    callback: CallbackQuery,
    state: FSMContext,
):
    user_id = callback.from_user.id

    await state.clear()

    action = callback.data.split(":", 1)[1]

    profile = get_user_profile(user_id)
    lang = profile["lang"]

    if action == "main":

        name = html.escape(
            callback.from_user.first_name
            or "User"
        )

        if lang == "ua":
            text = (
                f"👋 <b>Ласкаво просимо до "
                f"Tag Track, {name}!</b>"
            )
        else:
            text = (
                f"👋 <b>Welcome to Tag Track, "
                f"{name}!</b>"
            )

        await callback.message.edit_text(
            text,
            reply_markup=main_keyboard(user_id),
            parse_mode="HTML",
        )

    elif action == "auto":

        await state.set_state(
            BotStates.auto_search
        )

        text = (
            "🔍 Select length (5-12):"
            if lang == "en"
        else
            "Вже збережено!"
        )

    await callback.answer(
        text,
        show_alert=True,
    )


# =========================================================
# STARTUP
# =========================================================

async def main():

    init_database()

    logging.info(
        "Tag Track is starting..."
    )

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
