import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from bot import db
from bot.common import send_invoice, send_movie
from bot.config import ADMIN_IDS, PROVIDERS
from bot.keyboards import som

router = Router()
log = logging.getLogger(__name__)


def _code(payload: str) -> int | None:
    kind, _, value = payload.partition(":")
    return int(value) if kind == "movie" and value.isdigit() else None


def _expected_amount(movie, currency: str) -> int:
    """Invoice summasi Telegram birligida (Stars yoki tiyin). 0 = bu valyutada sotilmaydi."""
    if currency == "XTR":
        return movie["price"]
    if currency == "UZS":
        return movie["price_uzs"] * 100
    return 0


@router.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery, bot: Bot):
    _, code, method = call.data.split(":")
    movie = await db.get_movie(int(code))
    if not movie or not movie["is_paid"]:
        await call.answer("❌ Kino topilmadi.", show_alert=True)
        return
    if await db.has_purchase(call.from_user.id, movie["code"]):
        await call.answer()
        await send_movie(bot, call.message.chat.id, movie)
        return

    available = (method == "stars" and movie["price"]) or (method in PROVIDERS and movie["price_uzs"])
    if not available:
        await call.answer("⚠️ Bu to'lov usuli hozir mavjud emas.", show_alert=True)
        return

    await call.answer()
    try:
        await send_invoice(bot, call.message.chat.id, movie, method)
    except TelegramBadRequest as e:
        log.error("Invoice yuborilmadi (kino %s, %s): %s", code, method, e)
        await call.message.answer("⚠️ To'lov oynasini ochib bo'lmadi. Boshqa to'lov usulini tanlang yoki keyinroq urinib ko'ring.")


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    code = _code(query.invoice_payload)
    movie = await db.get_movie(code) if code else None
    if not movie or not movie["is_paid"]:
        await query.answer(ok=False, error_message="Kino topilmadi yoki o'chirilgan.")
        return
    expected = _expected_amount(movie, query.currency)
    if not expected or query.total_amount != expected:
        await query.answer(ok=False, error_message="Narx o'zgargan. Kino kodini qaytadan yuboring.")
    elif await db.has_purchase(query.from_user.id, code):
        await query.answer(ok=False, error_message="Siz bu kinoni allaqachon sotib olgansiz. Kodini yuboring.")
    else:
        await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    payment = message.successful_payment
    code = _code(payment.invoice_payload)
    if payment.currency == "UZS":
        amount = payment.total_amount // 100
        amount_text = f"💳 {som(amount)}"
    else:
        amount = payment.total_amount
        amount_text = f"⭐ {amount} Stars"
    await db.add_purchase(message.from_user.id, code, amount, payment.currency, payment.telegram_payment_charge_id)

    movie = await db.get_movie(code)
    if movie:
        await message.answer("✅ To'lov qabul qilindi! Kino yuborilmoqda...")
        await send_movie(bot, message.chat.id, movie)
        title = movie["title"]
    else:
        await message.answer("✅ To'lov qabul qilindi, lekin kino topilmadi. Iltimos, /paysupport orqali murojaat qiling.")
        title = f"#{code} (o'chirilgan)"

    user = message.from_user
    provider_line = (
        f"\n🏦 Provayder cheki: <code>{payment.provider_payment_charge_id}</code>"
        if payment.provider_payment_charge_id else ""
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Yangi sotuv!</b>\n🎬 {escape(title)}\n{amount_text}\n"
                f"👤 {escape(user.full_name)} (<code>{user.id}</code>)\n"
                f"🧾 <code>{payment.telegram_payment_charge_id}</code>{provider_line}",
            )
        except TelegramAPIError as e:
            log.warning("Admin %s ga xabar yuborilmadi: %s", admin_id, e)


@router.message(Command("paysupport"))
async def pay_support(message: Message):
    await message.answer(
        "💬 To'lov bo'yicha muammo bo'lsa, to'lov chekidagi raqam bilan adminga yozing.\n"
        "Kino yetib kelmagan bo'lsa, avval kino kodini qaytadan yuboring: sotib olingan kinolar qayta to'lovsiz yuboriladi."
    )
