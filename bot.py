import json
import logging
import os
import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

STATE_FILE = Path("bot_state.json")


# ---------- STATE ----------
def load_state():
    if not STATE_FILE.exists():
        return {"blocked": [], "map": {}}
    return json.loads(STATE_FILE.read_text())


def save_state(data):
    STATE_FILE.write_text(json.dumps(data))


def is_blocked(user_id):
    return user_id in load_state().get("blocked", [])


def block(user_id):
    data = load_state()
    if user_id not in data["blocked"]:
        data["blocked"].append(user_id)
    save_state(data)


def unblock(user_id):
    data = load_state()
    if user_id in data["blocked"]:
        data["blocked"].remove(user_id)
    save_state(data)


def save_map(msg_id, user_id):
    data = load_state()
    data["map"][str(msg_id)] = user_id
    save_state(data)


def get_user_by_reply(msg):
    data = load_state()
    return data["map"].get(str(msg.message_id))


# ---------- BOT ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пиши сообщение — я передам админу 👇")


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if is_blocked(user.id):
        await update.message.reply_text("Вы заблокированы.")
        return

    sent = await context.bot.send_message(
        ADMIN_ID,
        f"📩 {text}\n\n👤 @{user.username if user.username else 'нет'}\n🆔 {user.id}"
    )

    save_map(sent.message_id, user.id)
    await update.message.reply_text("Отправлено 👍")


async def block_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.from_user.id != ADMIN_ID:
        return

    action, uid = q.data.split(":")
    uid = int(uid)

    if action == "block":
        block(uid)
        await q.edit_message_text("Пользователь заблокирован ❌")
    else:
        unblock(uid)
        await q.edit_message_text("Пользователь разблокирован ✅")


# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(CallbackQueryHandler(block_btn))

    app.run_polling()


if __name__ == "__main__":
    main()
