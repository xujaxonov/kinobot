from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.config import PROVIDERS


def som(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"

TOP = "🔥 Top kinolar"
SEARCH = "🔍 Qidirish"

ADD_MOVIE = "➕ Kino qo'shish"
DEL_MOVIE = "🗑 Kino o'chirish"
CHANNELS = "📢 Kanallar"
STATS = "📊 Statistika"
BROADCAST = "📨 Xabar yuborish"
EXIT_ADMIN = "🏠 Asosiy menyu"
CANCEL = "❌ Bekor qilish"


def _reply(*rows: list[str]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
    )


user_menu = _reply([TOP, SEARCH])
admin_menu = _reply([ADD_MOVIE, DEL_MOVIE], [CHANNELS, STATS], [BROADCAST, EXIT_ADMIN])
cancel_menu = _reply([CANCEL])


def _inline(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscribe_kb(channels, code: int = 0) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"➕ {ch['title']}", url=ch["link"])] for ch in channels]
    rows.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data=f"check:{code}")])
    return _inline(rows)


def movies_kb(movies) -> InlineKeyboardMarkup:
    return _inline([
        [InlineKeyboardButton(
            text=f"{'💎 ' if m['is_paid'] else ''}{m['title']} [{m['code']}]",
            callback_data=f"movie:{m['code']}",
        )]
        for m in movies
    ])


def buy_kb(movie) -> InlineKeyboardMarkup:
    """Pullik kino uchun mavjud to'lov usullari. Hech biri bo'lmasa, tugmalar ro'yxati bo'sh."""
    code = movie["code"]
    rows = []
    if movie["price_uzs"]:
        rows += [
            [InlineKeyboardButton(text=f"💳 {name} — {som(movie['price_uzs'])}", callback_data=f"buy:{code}:{key}")]
            for key, (name, _) in PROVIDERS.items()
        ]
    if movie["price"]:
        rows.append([InlineKeyboardButton(
            text=f"⭐ Telegram Stars — {movie['price']} ⭐", callback_data=f"buy:{code}:stars"
        )])
    return _inline(rows)


def paid_choice_kb() -> InlineKeyboardMarkup:
    return _inline([[
        InlineKeyboardButton(text="🆓 Bepul", callback_data="add:free"),
        InlineKeyboardButton(text="💎 Pullik", callback_data="add:paid"),
    ]])


def confirm_kb(prefix: str) -> InlineKeyboardMarkup:
    return _inline([[
        InlineKeyboardButton(text="✅ Ha", callback_data=f"{prefix}:yes"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data=f"{prefix}:no"),
    ]])


def channels_kb(channels) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"❌ {ch['title']}", callback_data=f"delch:{ch['chat_id']}")]
        for ch in channels
    ]
    rows.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="addch")])
    return _inline(rows)
