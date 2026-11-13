import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

# Берем токен из переменных окружения или вставляем сюда напрямую
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ТВОЙ_ТОКЕН_ЗДЕСЬ")

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
*   Приветствие при команде /start
    """
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}! Бот успешно работает. 🚀",
        parse_mode=ParseMode.HTML
    )

@dp.message()
async def echo_handler(message: Message) -> None:
    """
*   Эхо-обработчик: повторяет каждое сообщение пользователя
    """
    try:
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        await message.answer("Не удалось обработать этот тип сообщения.")

async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
    
