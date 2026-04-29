import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
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
    filters,
    ContextTypes
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MONGO_URI = os.getenv("MONGO_URI")

# MongoDB
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
# START + UI
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    keyboard = [["💬 Chat", "ℹ️ Help"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    text = f"""
✨ Hello {user.first_name}!

🤖 Welcome to Yash AI Bot  
📩 Send text, photo, video, voice  

Owner will reply you soon 🚀
"""

    await update.message.reply_text(text, reply_markup=reply_markup)

# =========================
# BUTTONS
# =========================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "ℹ️ Help":
        await update.message.reply_text(
            "📌 Send any message (text, photo, video, voice).\nAdmin will reply you."
        )

    elif text == "💬 Chat":
        await update.message.reply_text("✍️ Send your message now!")

# =========================
# HANDLE USER MSG
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message

    save_user(user)

    info = f"""
📩 New Message

👤 {user.full_name}
🔗 @{user.username}
🆔 {user.id}
"""

    # Send user info
    await context.bot.send_message(ADMIN_ID, info)

    # Forward message
    fwd = await context.bot.forward_message(
        ADMIN_ID,
        msg.chat_id,
        msg.message_id
    )

    # Save mapping (reliable reply)
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
# BROADCAST (PRO)
# =========================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Reply to a message\nUsage:\n1. Send media/text\n2. Reply with /broadcast <optional_link>"
        )
        return

    msg = update.message.reply_to_message

    # Optional button link
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
            await asyncio.sleep(0.05)  # anti flood
        except:
            failed += 1

    await update.message.reply_text(
        f"📢 Broadcast Complete\n\n✅ Success: {success}\n❌ Failed: {failed}"
    )

# =========================
# STATS
# =========================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    total = users_col.count_documents({})

    await update.message.reply_text(
        f"📊 Bot Stats\n\n👥 Total Users: {total}"
    )

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))

    # Order matters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.ALL & ~filters.User(ADMIN_ID), handle_message))
    app.add_handler(MessageHandler(filters.ALL & filters.User(ADMIN_ID), reply_from_admin))

    print("🚀 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
