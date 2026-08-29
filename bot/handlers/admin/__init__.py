"""Connecting XFI CONNECT admin routers."""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin.main import router as main_router
from bot.handlers.admin.message_editor import router as message_editor_router
from bot.handlers.admin.servers import router as servers_router
from bot.handlers.admin.payments import router as payments_router
from bot.handlers.admin.cryptobot import router as cryptobot_router
from bot.handlers.admin.tariffs import router as tariffs_router
from bot.handlers.admin.broadcast import router as broadcast_router
from bot.handlers.admin.broadcast_editor import router as broadcast_editor_router
from bot.handlers.admin.users_list import router as users_list_router
from bot.handlers.admin.users_manage import router as users_manage_router
from bot.handlers.admin.users_keys import router as users_keys_router
from bot.handlers.admin.users_keys_deleted import router as users_keys_deleted_router
from bot.handlers.admin.system import router as system_router
from bot.handlers.admin.trial import router as trial_router
from bot.handlers.admin.referral import router as referral_router
from bot.handlers.admin.promotions import router as promotions_router
from bot.handlers.admin.coupons import router as coupons_router
from bot.handlers.admin.coupon_generator import router as coupon_generator_router
from bot.handlers.admin.groups import router as groups_router
from bot.handlers.admin.support import router as support_router
from bot.handlers.admin.customization_reset import router as customization_reset_router
from bot.handlers.admin.code_editor import router as code_editor_router
from bot.handlers.admin.dev_agent import router as dev_agent_router
from bot.handlers.admin.yaa_local import router as yaa_local_router

admin_router = Router()

# Legacy update entry points are intentionally blocked. Production changes are
# made through the repository owner and are never pulled by the bot itself.
update_disabled_router = Router()


@update_disabled_router.message(Command("update"))
async def update_command_disabled(message: Message):
    await message.answer("Обновления через Telegram отключены в XFI CONNECT.")


@update_disabled_router.callback_query(F.data.startswith("admin_update"))
async def update_callback_disabled(callback: CallbackQuery):
    await callback.answer("Обновления отключены", show_alert=True)


admin_router.include_router(update_disabled_router)
admin_router.include_router(main_router)
admin_router.include_router(message_editor_router)
admin_router.include_router(servers_router)
admin_router.include_router(cryptobot_router)
admin_router.include_router(payments_router)
admin_router.include_router(tariffs_router)
admin_router.include_router(groups_router)
admin_router.include_router(broadcast_router)
admin_router.include_router(broadcast_editor_router)
admin_router.include_router(users_list_router)
admin_router.include_router(users_manage_router)
admin_router.include_router(support_router)
admin_router.include_router(users_keys_router)
admin_router.include_router(users_keys_deleted_router)
admin_router.include_router(system_router)
admin_router.include_router(trial_router)
admin_router.include_router(referral_router)
admin_router.include_router(promotions_router)
admin_router.include_router(coupons_router)
admin_router.include_router(coupon_generator_router)
admin_router.include_router(customization_reset_router)
admin_router.include_router(code_editor_router)
admin_router.include_router(dev_agent_router)
admin_router.include_router(yaa_local_router)
