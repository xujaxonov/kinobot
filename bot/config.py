import os

from dotenv import load_dotenv

load_dotenv()


def _parse_ids(value: str) -> set[int]:
    return {int(x) for x in value.replace(" ", "").split(",") if x}


BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_IDS = _parse_ids(os.getenv("ADMIN_IDS", ""))
# 0 bo'lsa, kino qo'shishda admin ogohlantiriladi (ID ni topish uchun botni avval shusiz ishga tushirish mumkin)
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID") or 0)

# @BotFather -> bot -> Payments orqali olinadigan tokenlar. Bo'sh bo'lsa, shu to'lov usuli o'chiq.
PROVIDERS: dict[str, tuple[str, str]] = {
    key: (name, token)
    for key, name, token in (
        ("click", "Click", os.getenv("CLICK_PROVIDER_TOKEN", "")),
        ("payme", "Payme", os.getenv("PAYME_PROVIDER_TOKEN", "")),
    )
    if token
}
