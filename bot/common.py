import logging
from html import escape

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import LabeledPrice

from bot import db
from bot.config import ADMIN_IDS, PROVIDERS, STORAGE_CHANNEL_ID
from bot.keyboards import buy_kb, subscribe_kb

log = logging.getLogger(__name__)


async def missing_subscriptions(bot: Bot, user_id: int) -> list:
    """Foydalanuvchi a'zo bo'lmagan majburiy kanallar ro'yxati."""
    if user_id in ADMIN_IDS:
        return []
    missing = []
    for ch in await db.get_channels():
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
        except TelegramAPIError as e:
            # Bot kanaldan chiqarilgan bo'lsa, foydalanuvchini to'sib qo'ymaymiz
            log.warning("Kanal %s tekshirilmadi: %s", ch["chat_id"], e)
            continue
        if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED) or (
            member.status == ChatMemberStatus.RESTRICTED and not member.is_member
        ):
            missing.append(ch)
    return missing


async def send_movie(bot: Bot, chat_id: int, movie) -> None:
    me = await bot.me()
    await bot.copy_message(
        chat_id=chat_id,
        from_chat_id=STORAGE_CHANNEL_ID,
        message_id=movie["storage_msg_id"],
        caption=(
            f"🎬 <b>{escape(movie['title'])}</b>\n"
            f"🔢 Kod: <code>{movie['code']}</code>\n\n"
            f"🤖 @{me.username}"
        ),
        # Pullik kinoni boshqalarga forward/saqlab bo'lmaydi
        protect_content=movie["is_paid"],
    )
    await db.inc_views(movie["code"])


async def deliver(bot: Bot, chat_id: int, user_id: int, code: int) -> None:
    """Kod bo'yicha kinoni yuboradi: obuna -> to'lov -> video."""
    movie = await db.get_movie(code)
    if not movie:
        await bot.send_message(chat_id, "❌ Bunday kodli kino topilmadi.")
        return

    missing = await missing_subscriptions(bot, user_id)
    if missing:
        await bot.send_message(
            chat_id,
            "📢 Kinoni olish uchun quyidagi kanallarga a'zo bo'ling, so'ng <b>✅ Tekshirish</b> tugmasini bosing:",
            reply_markup=subscribe_kb(missing, code),
        )
        return

    if movie["is_paid"] and user_id not in ADMIN_IDS and not await db.has_purchase(user_id, code):
        kb = buy_kb(movie)
        if not kb.inline_keyboard:
            await bot.send_message(chat_id, "⚠️ Bu kino uchun hozircha to'lov usuli yo'q. Keyinroq urinib ko'ring.")
            return
        await bot.send_message(
            chat_id,
            f"💎 <b>{escape(movie['title'])}</b> — pullik kino.\n\nTo'lov usulini tanlang 👇",
            reply_markup=kb,
        )
        return

    await send_movie(bot, chat_id, movie)


async def send_invoice(bot: Bot, chat_id: int, movie, method: str) -> None:
    """method: 'stars' yoki PROVIDERS kaliti ('click', 'payme')."""
    if method == "stars":
        currency, token, amount = "XTR", "", movie["price"]
    else:
        currency, token, amount = "UZS", PROVIDERS[method][1], movie["price_uzs"] * 100  # tiyinda
    await bot.send_invoice(
        chat_id=chat_id,
        title=movie["title"][:32],
        description=f"🎬 {movie['title']}\n🔢 Kod: {movie['code']}\n\nTo'lovdan so'ng kino darhol yuboriladi."[:255],
        payload=f"movie:{movie['code']}",
        currency=currency,
        provider_token=token,
        prices=[LabeledPrice(label="Kino", amount=amount)],
    )
