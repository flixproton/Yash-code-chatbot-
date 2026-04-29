import os
import asyncio
import threading
from datetime import datetime
from flask import Flask
from pymongo import MongoClient
from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# =========================
# LOAD ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MONGO_URI = os.getenv("MONGO_URI")
PORT = int(os.environ.get("PORT", 10000))

# =========================
# FLASK SERVER
# =========================
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot is running 🚀"

def run_web():
    app_flask.run(host="0.0.0.0", port=PORT)

# =========================
# DATABASE
# =========================
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]

users_col = db["users"]
messages_col = db["messages"]

# =========================
# SAVE USER
# =========================
def save_user(user):
    users_col.update_one(
        {"user_id": user.id},
        {
            "$set": {
                "name": user.full_name,
                "username": user.username,
                "last_active": datetime.utcnow()
            }
        },
        upsert=True
    )

# =========================
# START COMMAND
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    keyboard = [["💬 Chat", "ℹ️ Help"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"✨ Hello {user.first_name}!\n\n🤖 Welcome to Yash AI Bot 🚀",
        reply_markup=reply_markup
    )

# =========================
# BUTTON HANDLER
# =========================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "ℹ️ Help":
        await update.message.reply_text(
            "📌 Send any message (text/photo/video/voice).\nAdmin will reply you."
        )

    elif text == "💬 Chat":
        await update.message.reply_text("✍️ Send your message now!")

# =========================
# USER MESSAGE
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message

    save_user(user)

    info = f"📩 New Message\n\n👤 {user.full_name}\n🔗 @{user.username}\n🆔 {user.id}"

    await context.bot.send_message(chat_id=ADMIN_ID, text=info)

    fwd = await context.bot.forward_message(
        chat_id=ADMIN_ID,
        from_chat_id=msg.chat_id,
        message_id=msg.message_id
    )

    # Reliable reply mapping
    messages_col.insert_one({
        "admin_msg_id": fwd.message_id,
        "user_id": user.id
    })

# =========================
# ADMIN REPLY
# =========================
async def reply_from_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        return

    replied_id = update.message.reply_to_message.message_id

    data = messages_col.find_one({"admin_msg_id": replied_id})

    if not data:
        await update.message.reply_text("❌ User not found")
        return

    try:
        await context.bot.copy_message(
            chat_id=data["user_id"],
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
    except:
        await update.message.reply_text("❌ Failed to send")

# =========================
# BROADCAST
# =========================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to a message + /broadcast <optional_link>"
        )
        return

    msg = update.message.reply_to_message

    keyboard = None
    if context.args:
        link = context.args[0]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Open Link", url=link)]
        ])

    users = users_col.find()

    success = 0
    failed = 0

    for user in users:
        try:
            await context.bot.copy_message(
                chat_id=user["user_id"],
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
                reply_markup=keyboard
            )
            success += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1

    await update.message.reply_text(
        f"📢 Broadcast Done\n✅ {success}\n❌ {failed}"
    )

# =========================
# STATS
# =========================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total = users_col.count_documents({})

    await update.message.reply_text(f"👥 Total Users: {total}")

# =========================
# RUN BOT
# =========================
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.ALL & ~filters.User(ADMIN_ID), handle_message))
    app.add_handler(MessageHandler(filters.ALL & filters.User(ADMIN_ID), reply_from_admin))

    print("🚀 Bot running...")
    app.run_polling()

# =========================
# START BOTH
# =========================
if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    run_web()
