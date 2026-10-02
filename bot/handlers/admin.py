import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, MessageOriginType
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import db
from bot.config import ADMIN_IDS, PROVIDERS, STORAGE_CHANNEL_ID
from bot.keyboards import (
    ADD_MOVIE, BROADCAST, CANCEL, CHANNELS, DEL_MOVIE, EXIT_ADMIN, STATS,
    admin_menu, cancel_menu, channels_kb, confirm_kb, paid_choice_kb, som, user_menu,
)

log = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return event.from_user.id in ADMIN_IDS


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

MAX_STARS = 10000
MIN_UZS = 15000  # Telegram kartadan to'lovda ~1$ dan kam summani qabul qilmaydi


class AddMovie(StatesGroup):
    video = State()
    title = State()
    paid = State()
    price_uzs = State()
    price = State()


class DelMovie(StatesGroup):
    code = State()


class AddChannel(StatesGroup):
    chat = State()


class Broadcast(StatesGroup):
    message = State()
    confirm = State()


# ---------- umumiy ----------

@router.message(StateFilter("*"), F.text == CANCEL)
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Bekor qilindi.", reply_markup=admin_menu)


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👑 <b>Admin panel</b>", reply_markup=admin_menu)


@router.message(F.text == EXIT_ADMIN)
async def exit_admin(message: Message):
    await message.answer("🏠 Asosiy menyu. Admin panelga qaytish: /admin", reply_markup=user_menu)


# ---------- kino qo'shish ----------

@router.message(F.text == ADD_MOVIE)
async def add_movie_start(message: Message, state: FSMContext):
    if not STORAGE_CHANNEL_ID:
        await message.answer(
            "⚠️ STORAGE_CHANNEL_ID sozlanmagan. Ombor kanaldan biror xabarni botga forward qiling, "
            "chiqqan ID ni Railway Variables ga qo'shing."
        )
        return
    await state.set_state(AddMovie.video)
    await message.answer(
        "🎬 Kino videosini yuboring (video yoki fayl ko'rinishida, 2 GB gacha).",
        reply_markup=cancel_menu,
    )


@router.message(AddMovie.video, F.video | F.document)
async def add_movie_video(message: Message, state: FSMContext):
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id)
    await state.set_state(AddMovie.title)
    await message.answer("📝 Kino nomini yozing:")


@router.message(AddMovie.video)
async def add_movie_video_wrong(message: Message):
    await message.answer("⚠️ Iltimos, video yoki fayl yuboring.")


@router.message(AddMovie.title, F.text)
async def add_movie_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip()[:200])
    await state.set_state(AddMovie.paid)
    await message.answer("💰 Bu kino bepulmi yoki pullik?", reply_markup=paid_choice_kb())


@router.callback_query(AddMovie.paid, F.data == "add:free")
async def add_movie_free(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    await save_movie(bot, call.message.chat.id, state, is_paid=False, price=0, price_uzs=0)


async def _ask_stars_price(message: Message, state: FSMContext, price_uzs: int) -> None:
    await state.update_data(price_uzs=price_uzs)
    await state.set_state(AddMovie.price)
    skip = "\nStars orqali sotmaslik uchun <code>0</code> yozing." if price_uzs else ""
    await message.answer(
        f"⭐ Telegram Stars narxini yozing (1–{MAX_STARS}). Masalan: <code>50</code>{skip}"
    )


@router.callback_query(AddMovie.paid, F.data == "add:paid")
async def add_movie_paid(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_reply_markup(reply_markup=None)
    if not PROVIDERS:
        await _ask_stars_price(call.message, state, price_uzs=0)
        return
    await state.set_state(AddMovie.price_uzs)
    names = " / ".join(name for name, _ in PROVIDERS.values())
    await call.message.answer(
        f"💳 {names} uchun narxni <b>so'mda</b> yozing. Masalan: <code>15000</code>\n"
        f"Kamida {som(MIN_UZS)} bo'lsin (Telegram cheklovi ~1$).\n"
        "So'mda sotmaslik uchun <code>0</code> yozing."
    )


@router.message(AddMovie.price_uzs, F.text.regexp(r"^\d{1,9}$"))
async def add_movie_price_uzs(message: Message, state: FSMContext):
    price_uzs = int(message.text)
    if 0 < price_uzs < MIN_UZS:
        await message.answer(f"⚠️ Narx kamida {som(MIN_UZS)} bo'lishi kerak (yoki 0).")
        return
    await _ask_stars_price(message, state, price_uzs)


@router.message(AddMovie.price_uzs)
async def add_movie_price_uzs_wrong(message: Message):
    await message.answer("⚠️ Faqat son yozing. Masalan: 15000")


@router.message(AddMovie.price, F.text.regexp(r"^\d{1,5}$"))
async def add_movie_price(message: Message, state: FSMContext, bot: Bot):
    price = int(message.text)
    price_uzs = (await state.get_data())["price_uzs"]
    if price > MAX_STARS or (price == 0 and not price_uzs):
        await message.answer(f"⚠️ Narx 1 dan {MAX_STARS} gacha bo'lishi kerak.")
        return
    await save_movie(bot, message.chat.id, state, is_paid=True, price=price, price_uzs=price_uzs)


@router.message(AddMovie.price)
async def add_movie_price_wrong(message: Message):
    await message.answer("⚠️ Faqat son yozing. Masalan: 50")


async def save_movie(bot: Bot, chat_id: int, state: FSMContext, is_paid: bool, price: int, price_uzs: int) -> None:
    data = await state.get_data()
    title = data["title"]
    try:
        stored = await bot.copy_message(STORAGE_CHANNEL_ID, data["src_chat"], data["src_msg"], caption=escape(title))
    except TelegramAPIError as e:
        await state.clear()
        await bot.send_message(
            chat_id,
            f"❌ Ombor kanalga saqlab bo'lmadi: {escape(str(e))}\nBot kanalda admin ekanini tekshiring.",
            reply_markup=admin_menu,
        )
        return

    code = await db.add_movie(title, stored.message_id, is_paid, price, price_uzs)
    if is_paid:
        parts = ([som(price_uzs)] if price_uzs else []) + ([f"{price} ⭐"] if price else [])
        price_text = "💎 " + " / ".join(parts)
    else:
        price_text = "🆓 Bepul"
    try:
        await bot.edit_message_caption(
            chat_id=STORAGE_CHANNEL_ID,
            message_id=stored.message_id,
            caption=f"🔢 <code>{code}</code> | {escape(title)} | {price_text}",
        )
    except TelegramAPIError:
        pass  # sarlavha shunchaki qulaylik uchun

    await state.clear()
    me = await bot.me()
    await bot.send_message(
        chat_id,
        "✅ <b>Kino saqlandi!</b>\n\n"
        f"🎬 {escape(title)}\n"
        f"🔢 Kod: <code>{code}</code>\n"
        f"{price_text}\n"
        f"🔗 Havola: https://t.me/{me.username}?start={code}",
        reply_markup=admin_menu,
    )


# ---------- kino o'chirish ----------

@router.message(F.text == DEL_MOVIE)
async def del_movie_start(message: Message, state: FSMContext):
    await state.set_state(DelMovie.code)
    await message.answer("🔢 O'chiriladigan kino kodini yuboring:", reply_markup=cancel_menu)


@router.message(DelMovie.code, F.text.regexp(r"^\d{1,9}$"))
async def del_movie(message: Message, state: FSMContext, bot: Bot):
    code = int(message.text)
    movie = await db.get_movie(code)
    if not movie:
        await message.answer("❌ Bunday kodli kino yo'q. Boshqa kod yuboring yoki bekor qiling.")
        return
    await db.delete_movie(code)
    try:
        await bot.delete_message(STORAGE_CHANNEL_ID, movie["storage_msg_id"])
    except TelegramAPIError:
        pass  # 48 soatdan eski xabarni bot o'chira olmasligi mumkin
    await state.clear()
    await message.answer(f"🗑 <b>{escape(movie['title'])}</b> (kod {code}) o'chirildi.", reply_markup=admin_menu)


@router.message(DelMovie.code)
async def del_movie_wrong(message: Message):
    await message.answer("⚠️ Faqat kino kodini (son) yuboring.")


# ---------- majburiy kanallar ----------

async def _channels_text() -> tuple[str, list]:
    channels = await db.get_channels()
    if not channels:
        return "📢 Majburiy obuna kanallari yo'q.", channels
    lines = "\n".join(f"• {escape(ch['title'])} — {ch['link']}" for ch in channels)
    return f"📢 <b>Majburiy obuna kanallari:</b>\n{lines}\n\nO'chirish uchun ❌ tugmasini bosing.", channels


@router.message(F.text == CHANNELS)
async def channels_list(message: Message):
    text, channels = await _channels_text()
    await message.answer(text, reply_markup=channels_kb(channels), disable_web_page_preview=True)


@router.callback_query(F.data == "addch")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AddChannel.chat)
    await call.message.answer(
        "📢 Kanal <b>@username</b> yoki <b>ID</b> sini yuboring, yoki kanaldan xabar forward qiling.\n\n"
        "⚠️ Avval botni kanalga <b>admin</b> qiling!",
        reply_markup=cancel_menu,
    )


@router.message(AddChannel.chat)
async def add_channel(message: Message, state: FSMContext, bot: Bot):
    origin = message.forward_origin
    if origin and origin.type == MessageOriginType.CHANNEL:
        ref: int | str = origin.chat.id
    elif message.text:
        ref = message.text.strip().removeprefix("https://t.me/")
        if ref.lstrip("-").isdigit():
            ref = int(ref)
        elif not ref.startswith("@"):
            ref = "@" + ref
    else:
        await message.answer("⚠️ @username, ID yuboring yoki kanaldan xabar forward qiling.")
        return

    try:
        chat = await bot.get_chat(ref)
        me = await bot.me()
        member = await bot.get_chat_member(chat.id, me.id)
    except TelegramAPIError:
        await message.answer("❌ Kanal topilmadi yoki bot unga qo'shilmagan.")
        return
    if member.status != ChatMemberStatus.ADMINISTRATOR:
        await message.answer("❌ Bot bu kanalda admin emas. Avval admin qiling.")
        return

    if chat.username:
        link = f"https://t.me/{chat.username}"
    elif chat.invite_link:
        link = chat.invite_link
    else:
        link = (await bot.create_chat_invite_link(chat.id)).invite_link

    await db.add_channel(chat.id, chat.title or str(chat.id), link)
    await state.clear()
    await message.answer(f"✅ <b>{escape(chat.title or '')}</b> majburiy obunaga qo'shildi.", reply_markup=admin_menu)


@router.callback_query(F.data.startswith("delch:"))
async def del_channel(call: CallbackQuery):
    await db.delete_channel(int(call.data.split(":")[1]))
    await call.answer("🗑 O'chirildi")
    text, channels = await _channels_text()
    try:
        await call.message.edit_text(text, reply_markup=channels_kb(channels), disable_web_page_preview=True)
    except TelegramBadRequest:
        pass


# ---------- statistika ----------

@router.message(F.text == STATS)
async def stats(message: Message):
    s = await db.stats()
    top = await db.top_movies(5)
    top_lines = "\n".join(
        f"{i}. {escape(m['title'])} [{m['code']}] — 👁 {m['views']}" for i, m in enumerate(top, 1)
    ) or "—"
    await message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b>\n"
        f"🆕 Bugun qo'shilgan: <b>{s['today']}</b>\n"
        f"🚫 Botni bloklagan: <b>{s['blocked']}</b>\n\n"
        f"🎬 Kinolar: <b>{s['movies']}</b> (💎 pullik: {s['paid_movies']})\n"
        f"💰 Sotuvlar: <b>{s['sales']}</b> ta\n"
        f"💳 So'mda: <b>{som(s['uzs'])}</b>\n"
        f"⭐ Stars: <b>{s['stars']}</b>\n\n"
        f"🔥 <b>Top 5:</b>\n{top_lines}"
    )


# ---------- reklama / xabar yuborish ----------

_background_tasks: set[asyncio.Task] = set()


@router.message(F.text == BROADCAST)
async def broadcast_start(message: Message, state: FSMContext):
    await state.set_state(Broadcast.message)
    await message.answer(
        "📨 Hammaga yuboriladigan xabarni yuboring (matn, rasm, video — istalgan turdagi).",
        reply_markup=cancel_menu,
    )


@router.message(Broadcast.message)
async def broadcast_preview(message: Message, state: FSMContext):
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id)
    await state.set_state(Broadcast.confirm)
    count = len(await db.active_user_ids())
    await message.answer(f"❓ Shu xabar <b>{count}</b> ta foydalanuvchiga yuborilsinmi?", reply_markup=confirm_kb("bc"))


@router.callback_query(Broadcast.confirm, F.data == "bc:no")
async def broadcast_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text("❌ Bekor qilindi.")
    await call.message.answer("👑 Admin panel", reply_markup=admin_menu)


@router.callback_query(Broadcast.confirm, F.data == "bc:yes")
async def broadcast_go(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    await call.answer()
    await call.message.edit_text("⏳ Yuborish boshlandi. Tugagach xabar beraman.")
    await call.message.answer("👑 Admin panel", reply_markup=admin_menu)
    task = asyncio.create_task(_run_broadcast(bot, call.message.chat.id, data["src_chat"], data["src_msg"]))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _send_copy(bot: Bot, user_id: int, src_chat: int, src_msg: int) -> bool:
    try:
        await bot.copy_message(user_id, src_chat, src_msg)
        return True
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return await _send_copy(bot, user_id, src_chat, src_msg)
    except TelegramForbiddenError:
        await db.mark_blocked(user_id)
    except TelegramAPIError as e:
        log.info("Broadcast %s: %s", user_id, e)
    return False


async def _run_broadcast(bot: Bot, admin_chat: int, src_chat: int, src_msg: int) -> None:
    ok = fail = 0
    for user_id in await db.active_user_ids():
        if await _send_copy(bot, user_id, src_chat, src_msg):
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.05)  # Telegram limiti: ~20-30 xabar/soniya
    await bot.send_message(admin_chat, f"✅ <b>Yuborish tugadi</b>\n\n📬 Yetkazildi: {ok}\n🚫 Yetkazilmadi: {fail}")
