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
# COMMANDS
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
# MESSAGE HANDLERS
# =========================

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    msg = update.message

    # 1. HANDLE ADMIN REPLIES
    if user.id == ADMIN_ID and msg.reply_to_message:
        replied_id = msg.reply_to_message.message_id
        data = messages_col.find_one({"admin_msg_id": replied_id})
        
        if data:
            try:
                await context.bot.copy_message(
                    chat_id=data["user_id"],
                    from_chat_id=msg.chat_id,
                    message_id=msg.message_id
                )
                return # Stop processing
            except Exception as e:
                await msg.reply_text(f"❌ Failed: {e}")
                return

    # 2. HANDLE BUTTONS
    if text == "ℹ️ Help":
        await msg.reply_text("📌 Send any message. Admin will reply you.")
        return
    elif text == "💬 Chat":
        await msg.reply_text("✍️ Send your message now!")
        return

    # 3. HANDLE USER MESSAGES (Forward to Admin)
    if user.id != ADMIN_ID:
        save_user(user)
        info = f"📩 New Message\n👤 {user.full_name}\n🆔 {user.id}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=info)
        
        fwd = await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id
        )
        
        # Save mapping
        messages_col.insert_one({
            "admin_msg_id": fwd.message_id,
            "user_id": user.id
        })

# =========================
# ADMIN TOOLS
# =========================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to broadcast.")
        return

    msg = update.message.reply_to_message
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Link", url=context.args[0])]]) if context.args else None
    
    users = users_col.find()
    success = 0
    for user in users:
        try:
            await context.bot.copy_message(user["user_id"], msg.chat_id, msg.message_id, reply_markup=kb)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await update.message.reply_text(f"📢 Done. Sent to {success} users.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    total = users_col.count_documents({})
    await update.message.reply_text(f"👥 Total Users: {total}")

# =========================
# RUN BOT
# =========================
def run_bot():
    # Use standard build
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    
    # Use one combined MessageHandler to prevent conflict
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_all_messages))

    print("🚀 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    run_web()
