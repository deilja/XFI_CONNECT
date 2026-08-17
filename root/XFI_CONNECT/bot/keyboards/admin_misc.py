from aiogram import InlineKeyboardMarkup, InlineKeyboardButton

admin_misc_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text='🛠 AI редактор кода', callback_data='admin_code_editor')
        ],
    ]
)