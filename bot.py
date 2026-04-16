import json
import logging
import os
import re
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = 8376888091:AAH2bbaAoKHQ3khqkOS2Kch1Oh7UnKRWbME
ADMIN_ID = 5877007064
STATE_FILE = Path("bot_state.json")


def get_admin_id() -> int:
    if not ADMIN_ID:
        raise RuntimeError("ADMIN_ID is not set")
    try:
        return int(ADMIN_ID)
    except ValueError as exc:
        raise RuntimeError("ADMIN_ID must be a number") from exc


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"blocked_users": [], "admin_messages": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"blocked_users": [], "admin_messages": {}}
    data.setdefault("blocked_users", [])
    data.setdefault("admin_messages", {})
    return data


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_blocked(user_id: int) -> bool:
    state = load_state()
    return user_id in state["blocked_users"]


def set_blocked(user_id: int, blocked: bool) -> None:
    state = load_state()
    blocked_users = set(state["blocked_users"])
    if blocked:
        blocked_users.add(user_id)
    else:
        blocked_users.discard(user_id)
    state["blocked_users"] = sorted(blocked_users)
    save_state(state)


def remember_admin_message(admin_message_id: int, user_id: int) -> None:
    state = load_state()
    state["admin_messages"][str(admin_message_id)] = user_id
    save_state(state)


def find_user_for_admin_reply(reply_message) -> int | None:
    state = load_state()
    user_id = state["admin_messages"].get(str(reply_message.message_id))
    if user_id:
        return int(user_id)

    text = reply_message.text or reply_message.caption or ""
    match = re.search(r"ID: (\d+)", text)
    if match:
        return int(match.group(1))
    return None


def block_keyboard(user_id: int, blocked: bool = False) -> InlineKeyboardMarkup:
    if blocked:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Разблокировать", callback_data=f"unblock:{user_id}")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("Блокировка", callback_data=f"block:{user_id}")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    if is_blocked(update.effective_user.id):
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        return

    await update.message.reply_text(
        "Привет 👋\n\n"
        "Просто напиши сюда сообщение или предложи пост — я передам админу."
    )


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or update.effective_user.id != get_admin_id():
        return

    if not context.args:
        await update.message.reply_text("Напиши так: /unban ID_пользователя")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return

    set_blocked(user_id, False)
    await update.message.reply_text(f"Пользователь {user_id} разблокирован.")


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.message or not update.effective_user:
        return False
    if update.effective_user.id != get_admin_id():
        return False
    if not update.message.reply_to_message:
        await update.message.reply_text("Чтобы ответить пользователю, ответь на его сообщение в этом чате.")
        return True

    user_id = find_user_for_admin_reply(update.message.reply_to_message)
    if not user_id:
        await update.message.reply_text("Не смог найти пользователя для ответа. Ответь именно на сообщение, которое пришло от бота.")
        return True

    if is_blocked(user_id):
        await update.message.reply_text("Этот пользователь заблокирован. Сначала разблокируй его, если хочешь отправить ответ.")
        return True

    await context.bot.send_message(chat_id=user_id, text=update.message.text)
    await update.message.reply_text("Ответ отправлен пользователю.")
    return True


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text or not update.effective_user:
        return

    if await handle_admin_reply(update, context):
        return

    user = update.effective_user

    if is_blocked(user.id):
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        return

    username = f"@{user.username}" if user.username else "нет username"
    full_name = user.full_name or "без имени"

    sent_message = await context.bot.send_message(
        chat_id=get_admin_id(),
        text=(
            "📩 Новое сообщение\n\n"
            f"{update.message.text}\n\n"
            f"👤 {full_name}\n"
            f"🔗 {username}\n"
            f"🆔 ID: {user.id}\n\n"
            "Чтобы ответить пользователю, ответь на это сообщение."
        ),
        reply_markup=block_keyboard(user.id),
    )
    remember_admin_message(sent_message.message_id, user.id)

    await update.message.reply_text("Готово 👍 отправил")


async def handle_block_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return

    await query.answer()

    if query.from_user.id != get_admin_id():
        await query.answer("Эта кнопка только для админа.", show_alert=True)
        return

    action, user_id_text = query.data.split(":", 1)
    user_id = int(user_id_text)

    if action == "block":
        set_blocked(user_id, True)
        await query.edit_message_reply_markup(reply_markup=block_keyboard(user_id, blocked=True))
        await query.message.reply_text(f"Пользователь {user_id} заблокирован.")
        try:
            await context.bot.send_message(chat_id=user_id, text="Вы заблокированы и больше не можете пользоваться ботом.")
        except Exception as exc:
            logger.warning("Could not notify blocked user %s: %s", user_id, exc)
    elif action == "unblock":
        set_blocked(user_id, False)
        await query.edit_message_reply_markup(reply_markup=block_keyboard(user_id, blocked=False))
        await query.message.reply_text(f"Пользователь {user_id} разблокирован.")


def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CallbackQueryHandler(handle_block_button, pattern="^(block|unblock):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Telegram bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
