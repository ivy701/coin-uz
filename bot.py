import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

import config
from services import database
from handlers import start, shop, balance, profile, webapp, admin
from middlewares import AccessControlMiddleware

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log startup env vars (no secrets)
logger.info("=== STARTUP ===")
logger.info("PORT=%s", os.environ.get("PORT", "NOT SET"))
logger.info("BOT_TOKEN set: %s", bool(os.environ.get("BOT_TOKEN")))
logger.info("FRAGMENT_API_KEY set: %s", bool(os.environ.get("FRAGMENT_API_KEY")))
logger.info("FRAGMENT_API_BASE=%s", os.environ.get("FRAGMENT_API_BASE", "NOT SET"))
logger.info("===============")


async def start_api_server():
    """Start aiohttp API server with HTTPS support for local WebApp"""
    from api.server import create_app
    import ssl
    from pathlib import Path

    cert_file = Path("cert.pem")
    key_file = Path("key.pem")

    if not cert_file.exists() or not key_file.exists():
        try:
            import datetime, ipaddress
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, 'localhost'),
            ])
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
                .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650))
                .add_extension(
                    x509.SubjectAlternativeName([
                        x509.DNSName('localhost'),
                        x509.IPAddress(ipaddress.IPv4Address('127.0.0.1')),
                    ]),
                    critical=False,
                )
                .sign(key, hashes.SHA256())
            )
            key_file.write_bytes(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
            cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            logger.info("Generated local SSL certificates (cert.pem, key.pem)")
        except Exception as e:
            logger.warning(f"Could not generate SSL cert: {e}")

    ssl_context = None
    if os.environ.get("USE_SSL", "").lower() in ("1", "true", "yes"):
        if cert_file.exists() and key_file.exists():
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(str(cert_file), str(key_file))

    port = int(os.environ.get("PORT") or os.environ.get("API_PORT") or 8085)
    host = os.environ.get("IP") or os.environ.get("API_HOST") or "0.0.0.0"
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()

    # Bind to designated port
    site = web.TCPSite(runner, host, port, ssl_context=ssl_context, reuse_address=True)
    await site.start()
    protocol = "https" if ssl_context else "http"
    logger.info("API server started on %s://%s:%s", protocol, host, port)
    return runner


async def main():
    # Start API server first (Railway needs port open to mark deploy as success)
    runner = await start_api_server()

    # Initialize Telethon gift sender (if credentials provided)
    logger.info(f"API_ID check: {config.API_ID}, API_HASH check: {bool(config.API_HASH)}")
    
    if config.API_ID and config.API_HASH:
        try:
            from services.telethon_client import init_gift_sender
            session = config.TELETHON_SESSION_STRING or config.SESSION_NAME
            logger.info(f"Initializing Telethon with session type: {'string' if config.TELETHON_SESSION_STRING else 'file'}")
            await init_gift_sender(
                config.API_ID,
                config.API_HASH,
                session,
                config.PHONE_NUMBER if config.PHONE_NUMBER else None
            )
            logger.info("Telethon gift sender initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Telethon: {e}")
            logger.warning("Gift sending will not be available")
    else:
        logger.warning(f"Telethon not configured: API_ID={config.API_ID}, API_HASH={'set' if config.API_HASH else 'not set'}")

    # Reuse bot and dispatcher created during API server startup
    if hasattr(runner, 'app') and "bot" in runner.app and "dp" in runner.app:
        bot = runner.app["bot"]
        dp = runner.app["dp"]
    else:
        bot = Bot(
            token=config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        dp.update.middleware(AccessControlMiddleware())
        dp.include_router(admin.router)
        dp.include_router(start.router)
        dp.include_router(webapp.router)
        dp.include_router(shop.router)
        dp.include_router(balance.router)
        dp.include_router(profile.router)

    await database.init_db()
    logger.info("Database initialized, bot starting...")

    if hasattr(runner, 'app'):
        runner.app["bot"] = bot
        runner.app["dp"] = dp

    use_webhook = os.environ.get("USE_WEBHOOK", "1").lower() in ("1", "true", "yes")
    
    webhook_url = os.environ.get("WEBHOOK_URL") or "https://web-production-4014a4.up.railway.app/webhook/telegram"
    if "1b7cb" in webhook_url:
        webhook_url = "https://web-production-4014a4.up.railway.app/webhook/telegram"

    try:
        if use_webhook:
            try:
                logger.info("Setting Telegram Webhook to %s...", webhook_url)
                await bot.set_webhook(
                    url=webhook_url,
                    drop_pending_updates=True,
                    allowed_updates=dp.resolve_used_update_types()
                )
                logger.info("Telegram Webhook active at %s! Listening for updates...", webhook_url)
            except Exception as e:
                logger.warning("Could not set webhook: %s", e)

            # Keep server running to serve webhook requests
            while True:
                await asyncio.sleep(3600)
        else:
            # Polling mode (fallback)
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                logger.info("Webhook cleared for polling")
            except Exception as e:
                logger.warning("Could not clear webhook: %s", e)

            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # Cleanup
        from services.telethon_client import stop_gift_sender
        await stop_gift_sender()
        await bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
