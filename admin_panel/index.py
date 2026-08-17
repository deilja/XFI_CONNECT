# Добавлена кнопка для функции /code

from aiogram import Dispatcher, types

cd = Dispatcher(bot)

cd.register_message_handler(code, commands=["code"])