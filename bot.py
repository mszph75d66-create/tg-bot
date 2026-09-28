"""
Telegram media-downloader bot
YouTube, Instagram, TikTok linklaridan video/audio yuklab beradi.

Kerakli kutubxonalar:
    pip install python-telegram-bot yt-dlp --break-system-packages

Ishlatish:
    python3 bot.py

Eslatma:
- Ba'zi platformalar (ayniqsa Instagram) login talab qilishi mumkin.
  Bunday holda cookies.txt fayl orqali yt-dlp ga cookie berish kerak
  (pastdagi COOKIES_FILE o'zgaruvchisini sozlang).
- Telegram bot 50MB dan katta faylni yuklab bera olmaydi (oddiy bot API bilan).
  Shuning uchun katta videolarda sifatni pasaytirib yuklanadi.
"""

import logging
import os
import re
import tempfile
import uuid

import yt_dlp
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ====== SOZLAMALAR ======
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # token Railway "Variables" bo'limida saqlanadi
COOKIES_FILE = None  # masalan: "cookies.txt" (Instagram/TikTok uchun kerak bo'lsa)
MAX_TELEGRAM_FILE_MB = 50
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

URL_REGEX = re.compile(
    r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be|instagram\.com|tiktok\.com|vm\.tiktok\.com)\S+)",
    re.IGNORECASE,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Menga YouTube, Instagram yoki TikTok link yuboring — "
        "men video/audio faylini yuklab beraman.\n\n"
        "Masalan:\n"
        "https://www.tiktok.com/@user/video/123456\n"
        "https://www.instagram.com/reel/XXXXX\n"
        "https://youtu.be/XXXXXXX"
    )


def build_ydl_opts(out_path: str) -> dict:
    opts = {
        "outtmpl": out_path,
        "format": "best[filesize<50M]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }
    if COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    return opts


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    match = URL_REGEX.search(text)

    if not match:
        await update.message.reply_text(
            "Iltimos, YouTube, Instagram yoki TikTok linkini yuboring."
        )
        return

    url = match.group(1)
    chat_id = update.effective_chat.id

    status_msg = await update.message.reply_text("⏳ Yuklab olinmoqda, biroz kuting...")
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)

    with tempfile.TemporaryDirectory() as tmpdir:
        file_id = str(uuid.uuid4())
        out_template = os.path.join(tmpdir, f"{file_id}.%(ext)s")

        try:
            ydl_opts = build_ydl_opts(out_template)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

            if not os.path.exists(filename):
                # ba'zan kengaytma mos kelmasligi mumkin, papkadan qidiramiz
                candidates = [
                    os.path.join(tmpdir, f)
                    for f in os.listdir(tmpdir)
                    if f.startswith(file_id)
                ]
                if not candidates:
                    raise FileNotFoundError("Yuklangan fayl topilmadi")
                filename = candidates[0]

            size_mb = os.path.getsize(filename) / (1024 * 1024)
            if size_mb > MAX_TELEGRAM_FILE_MB:
                await status_msg.edit_text(
                    f"❌ Fayl juda katta ({size_mb:.1f}MB). "
                    f"Telegram bot orqali {MAX_TELEGRAM_FILE_MB}MB dan katta fayl yuborib bo'lmaydi."
                )
                return

            title = info.get("title", "video")
            await status_msg.edit_text("📤 Yuborilmoqda...")

            with open(filename, "rb") as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption=title,
                    supports_streaming=True,
                )
            await status_msg.delete()

        except Exception as e:
            logger.exception("Yuklashda xatolik")
            await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}")


def main():
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN o'zgaruvchisi topilmadi. Railway Variables bo'limiga qo'shing."
        )

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
