import os
import re
from datetime import datetime, timezone

import dateparser
from dateparser.search import search_dates

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("TOKEN")
TZ = os.getenv("TZ", "Europe/Paris")

HELP = (
    "✅ Rappels en français\n\n"
    "Format conseillé (ultra fiable) :\n"
    "  /r <quand> | <message>\n\n"
    "Exemples :\n"
    "  /r dans 1 minute | tester rappel\n"
    "  /r demain 14h | appeler le garage\n"
    "  /r ce soir 19h30 | lancer la cuisson\n"
    "  /r lundi 9h | payer facture\n\n"
    "Tu peux aussi tenter sans \"|\", mais c’est moins fiable."
)

def _parse_when_and_message(raw: str):
    """
    Parse "/r ...." into (when_dt_utc, human_when, message).
    Uses dateparser in French.
    """
    text = raw.strip()
    text = re.sub(r"^/r\s*", "", text, flags=re.IGNORECASE).strip()

    # Preferred format: "<when> | <message>"
    if "|" in text:
        when_part, msg = [p.strip() for p in text.split("|", 1)]
        if not msg:
            raise ValueError("Message vide.")
        dt = dateparser.parse(
            when_part,
            languages=["fr"],
            settings={
                "TIMEZONE": TZ,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            },
        )
        if not dt:
            raise ValueError("Date/heure non comprise.")
        return dt.astimezone(timezone.utc), when_part, msg

    # Fallback: try to find a date expression inside text
    found = search_dates(
        text,
        languages=["fr"],
        settings={
            "TIMEZONE": TZ,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )
    if not found:
        raise ValueError("Date/heure non trouvée.")
    (match_text, dt) = found[0]
    msg = text.replace(match_text, "").strip(" ,-–—:;")
    if not msg:
        msg = "Rappel"
    return dt.astimezone(timezone.utc), match_text, msg


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Bot de rappels prêt.\n\n" + HELP)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)

async def _send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data["chat_id"]
    msg = job.data["msg"]
    await context.bot.send_message(chat_id=chat_id, text=f"🔔 Rappel : {msg}")

async def r_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        when_utc, human_when, msg = _parse_when_and_message(update.message.text)
        chat_id = update.effective_chat.id

        now_utc = datetime.now(timezone.utc)
        delay_seconds = (when_utc - now_utc).total_seconds()
        if delay_seconds < 5:
            raise ValueError("La date/heure est trop proche ou déjà passée.")

        # Schedule with PTB JobQueue (reliable in cloud)
        context.job_queue.run_once(
            _send_reminder,
            when=delay_seconds,
            data={"chat_id": chat_id, "msg": msg},
            name=f"reminder-{chat_id}-{int(when_utc.timestamp())}",
        )

        # Confirmation (immediate)
        local_dt = when_utc.astimezone().strftime("%Y-%m-%d %H:%M")
        await update.message.reply_text(f"✅ OK. Rappel prévu ({human_when}) → {local_dt}\n📝 {msg}")

    except Exception:
        await update.message.reply_text("❌ Je n’ai pas compris.\n\n" + HELP)


def main():
    if not TOKEN:
        raise SystemExit("Missing TOKEN env var")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("r", r_cmd))

    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
