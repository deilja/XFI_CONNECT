"""XFI CONNECT Telegram bot entry point."""

import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database.migrations import run_migrations
from bot.services.vpn_api import close_all_clients
from bot.services.scheduler import run_daily_tasks, run_traffic_sync_scheduler
from bot.services.payment_auto_check import run_payment_auto_check_scheduler

from bot.services import cryptobot_provider as _cryptobot_provider  # noqa: F401
from bot.services import cryptobot_ui as _cryptobot_ui  # noqa: F401

from bot.handlers.user import router as user_router
from bot.handlers.admin import admin_router
from bot.handlers import ai, admin_ai

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("logs/bot.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"),
    ],
)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Initialize database, UI, extensions and runtime services."""
    logger.info("XFI CONNECT запускается")
    run_migrations()

    from bot.utils.user_ui_texts import load_user_ui_text_cache
    logger.info("User UI text cache loaded: %s entries", load_user_ui_text_cache())
    from bot.utils.page_renderer import validate_required_user_pages
    logger.info("Required user pages validated: %s entries", validate_required_user_pages())
    from bot.utils.telegram_links import load_telegram_link_domain
    load_telegram_link_domain()
    from bot.services.yadreno_admin_core_guard import recover_core_guards_on_startup
    await recover_core_guards_on_startup()
    from bot.utils.custom_extensions import load_custom_extensions
    extensions_result = load_custom_extensions()
    if extensions_result.skipped:
        logger.info("Custom extensions не загружены: %s", extensions_result.reason)
    else:
        logger.info("Custom extensions: загружено %s, ошибок %s", len(extensions_result.loaded), len(extensions_result.failed))
    try:
        from bot.services.custom_payment_webhooks import start_custom_payment_webhook_server
        bot.custom_payment_webhook_server = await start_custom_payment_webhook_server(bot)
    except Exception as exc:
        logger.warning("Не удалось запустить custom payment webhook server: %s", exc)
    bot_info = await bot.get_me()
    bot.my_username = bot_info.username
    logger.info("Бот запущен: @%s", bot_info.username)
    try:
        from bot.services.yadreno_admin import recover_active_dialogs_on_startup
        await recover_active_dialogs_on_startup(bot)
    except Exception as exc:
        logger.warning("Не удалось восстановить AI Admin dialogs: %s", exc)


async def on_shutdown(bot: Bot):
    logger.info("XFI CONNECT останавливается")
    monitor_loop = getattr(bot, "ai_key_monitor_loop", None)
    if monitor_loop is not None:
        try:
            await monitor_loop.stop()
        except Exception as exc:
            logger.warning("Не удалось остановить AI key monitor: %s", exc)
    webhook_server = getattr(bot, "custom_payment_webhook_server", None)
    if webhook_server is not None:
        try:
            await webhook_server.stop()
        except Exception as exc:
            logger.warning("Не удалось остановить custom payment webhook server: %s", exc)
    await close_all_clients()
    logger.info("XFI CONNECT остановлен")


async def main():
    from bot.middlewares.parse_mode_fallback import SafeParseSession
    bot = Bot(token=BOT_TOKEN, session=SafeParseSession())
    dp = Dispatcher(storage=MemoryStorage())
    from bot.middlewares.bot_blocked import BotBlockedResetMiddleware
    bot_blocked_reset = BotBlockedResetMiddleware()
    dp.message.outer_middleware(bot_blocked_reset)
    dp.callback_query.outer_middleware(bot_blocked_reset)
    dp.include_router(admin_ai.router)
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.include_router(ai.router)
    from aiogram.exceptions import TelegramNetworkError
    from aiogram.types import ErrorEvent
    from bot.utils.callbacks import is_expired_callback_error

    @dp.errors()
    async def global_error_handler(event: ErrorEvent):
        exception = event.exception
        if isinstance(exception, TelegramNetworkError):
            logger.warning("Нет связи с Telegram API: %s", exception)
            return True
        if is_expired_callback_error(exception):
            logger.warning("Просроченный Telegram callback: %s", exception)
            return True
        logger.error("Необработанная ошибка: %s", exception, exc_info=True)
        return True

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await bot.delete_webhook(drop_pending_updates=True)

    daily_task = asyncio.create_task(run_daily_tasks(bot))
    traffic_task = asyncio.create_task(run_traffic_sync_scheduler(bot))
    payment_task = asyncio.create_task(run_payment_auto_check_scheduler(bot))

    # AI provider health monitor starts with the bot and is cancelled on shutdown.
    # Provider checks are supplied by the key-validation integration; if it is not
    # configured, the monitor remains fail-closed and cannot mark a provider healthy.
    from bot.services.ai_key_monitor import AIKeyHealthMonitor
    from bot.services.ai_key_monitor_loop import AIKeyMonitorLoop
    from bot.services.ai_key_store import AIKeyStore
    from bot.services.ai_key_validation import AIKeyValidator
    from bot.services.ai_key_manager import SUPPORTED_PROVIDERS

    key_store = AIKeyStore("data/ai_keys.enc")
    validator = AIKeyValidator()
    async def provider_check(provider: str) -> bool:
        return False if provider not in SUPPORTED_PROVIDERS else False

    monitor = AIKeyHealthMonitor(key_store, SUPPORTED_PROVIDERS, provider_check)
    monitor_loop = AIKeyMonitorLoop(monitor, interval=900)
    bot.ai_key_monitor_loop = monitor_loop
    monitor_loop.start()

    background_tasks = [daily_task, traffic_task, payment_task]
    try:
        await dp.start_polling(bot)
    finally:
        await monitor_loop.stop()
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        await close_all_clients()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал остановки")
