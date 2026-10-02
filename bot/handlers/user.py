from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import MessageOriginType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from bot import db
from bot.common import deliver, missing_subscriptions
from bot.keyboards import SEARCH, TOP, movies_kb, subscribe_kb, user_menu

router = Router()


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, bot: Bot):
    user = message.from_user
    await db.add_user(user.id, user.full_name, user.username)
    await message.answer(
        f"👋 Assalomu alaykum, <b>{escape(user.first_name)}</b>!\n\n"
        "🎬 Kino kodini yuboring va men sizga kinoni yuboraman.\n"
        "🔍 Yoki kino nomini yozib qidiring.",
        reply_markup=user_menu,
    )
    # t.me/bot?start=125 havolasi orqali kelgan bo'lsa, kinoni darhol yuboramiz
    if command.args and command.args.isdigit() and len(command.args) <= 9:
        await deliver(bot, message.chat.id, user.id, int(command.args))


@router.message(Command("id"))
async def my_id(message: Message):
    await message.answer(f"🆔 Sizning ID: <code>{message.from_user.id}</code>")


@router.message(F.forward_origin.type == MessageOriginType.CHANNEL)
async def channel_id(message: Message):
    chat = message.forward_origin.chat
    await message.answer(f"📢 {chat.title}\n🆔 Kanal ID: <code>{chat.id}</code>")


@router.message(F.text == TOP)
async def top(message: Message):
    movies = await db.top_movies()
    if not movies:
        await message.answer("Hozircha kinolar yo'q.")
        return
    await message.answer("🔥 <b>Eng ko'p ko'rilgan kinolar:</b>", reply_markup=movies_kb(movies))


@router.message(F.text == SEARCH)
async def search_hint(message: Message):
    await message.answer("🔍 Kino kodini yoki nomini yozing:")


@router.message(F.text.regexp(r"^\d{1,9}$"))
async def by_code(message: Message, bot: Bot):
    await deliver(bot, message.chat.id, message.from_user.id, int(message.text))


@router.message(F.text, ~F.text.startswith("/"))
async def search(message: Message):
    movies = await db.search_movies(message.text.strip()[:50])
    if not movies:
        await message.answer("😔 Hech narsa topilmadi. Kino kodini yuborib ko'ring.")
        return
    await message.answer("🔍 <b>Topilgan kinolar:</b>", reply_markup=movies_kb(movies))


@router.callback_query(F.data.startswith("movie:"))
async def movie_cb(call: CallbackQuery, bot: Bot):
    await call.answer()
    await deliver(bot, call.message.chat.id, call.from_user.id, int(call.data.split(":")[1]))


@router.callback_query(F.data.startswith("check:"))
async def check_sub(call: CallbackQuery, bot: Bot):
    missing = await missing_subscriptions(bot, call.from_user.id)
    if missing:
        await call.answer("❌ Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)
        code = int(call.data.split(":")[1])
        try:
            await call.message.edit_reply_markup(reply_markup=subscribe_kb(missing, code))
        except TelegramBadRequest:
            pass  # tugmalar o'zgarmagan
        return

    await call.answer("✅ Rahmat!")
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    code = int(call.data.split(":")[1])
    if code:
        await deliver(bot, call.message.chat.id, call.from_user.id, code)
    else:
        await call.message.answer("✅ Endi kino kodini yuboring.")
