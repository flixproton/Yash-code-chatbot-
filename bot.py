import os
import asyncio
import threading
import logging
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

# Enable logging to see errors in the console
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

load_dotenv()

# =========================
# CONFIG & ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MONGO_URI = os.getenv("MONGO_URI")
PORT = int(os.environ.get("PORT", 10000))

# =========================
# DATABASE
# =========================
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client["telegram_bot"]
    users_col = db["users"]
    messages_col = db["messages"]
    client.server_info() # Test connection
    print("✅ MongoDB Connected Successfully")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

# =========================
# FLASK SERVER (For Render/Replit keep-alive)
# =========================
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot is running 🚀"

def run_web():
    app_flask.run(host="0.0.0.0", port=PORT)

# =========================
# HELPER FUNCTIONS
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
# BOT COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user)

    keyboard = [["💬 Chat", "ℹ️ Help"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"✨ Hello {user.first_name}!\n\n🤖 Welcome to Yash AI Bot 🚀\nAdmin will reply to your messages here.",
        reply_markup=reply_markup
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    total = users_col.count_documents({})
    await update.message.reply_text(f"👥 Total Users: {total}")

# =========================
# MESSAGE LOGIC (The "Brain")
# =========================
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.message
    
    if not msg: return

    # 1. HANDLE ADMIN REPLIES
    if user.id == ADMIN_ID:
        # If admin is replying to a forwarded message
        if msg.reply_to_message:
            replied_msg_id = msg.reply_to_message.message_id
            data = messages_col.find_one({"admin_msg_id": replied_msg_id})
            
            if data:
                try:
                    await context.bot.copy_message(
                        chat_id=data["user_id"],
                        from_chat_id=msg.chat_id,
                        message_id=msg.message_id
                    )
                    return # Successfully sent, stop here
                except Exception as e:
                    await msg.reply_text(f"❌ Send Error: {e}")
                    return

    # 2. HANDLE BUTTONS
    if msg.text == "ℹ️ Help":
        await msg.reply_text("📌 Send any message. Admin will reply to you directly.")
        return
    elif msg.text == "💬 Chat":
        await msg.reply_text("✍️ Send your message now!")
        return

    # 3. HANDLE USER MESSAGES (Forward to Admin)
    if user.id != ADMIN_ID:
        save_user(user)
        
        # Forward message to Admin
        try:
            # Send notification to Admin
            info = f"📩 New Message from {user.full_name} (@{user.username})"
            await context.bot.send_message(chat_id=ADMIN_ID, text=info)
            
            # Forward the actual content
            fwd = await context.bot.forward_message(
                chat_id=ADMIN_ID,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id
            )
            
            # Store mapping so Admin can reply
            messages_col.insert_one({
                "admin_msg_id": fwd.message_id,
                "user_id": user.id
            })
        except Exception as e:
            print(f"Forwarding error: {e}")

# =========================
# BROADCAST
# =========================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to broadcast.")
        return

    broadcast_msg = update.message.reply_to_message
    users = users_col.find()
    success = 0

    for user in users:
        try:
            await context.bot.copy_message(
                chat_id=user["user_id"],
                from_chat_id=broadcast_msg.chat_id,
                message_id=broadcast_msg.message_id
            )
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await update.message.reply_text(f"📢 Broadcast complete. Sent to {success} users.")

# =========================
# RUNNER
# =========================
def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers (Order matters!)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    # Catch-all for messages (Text, Photo, Video, etc.)
    # This covers buttons AND user messages
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_all_messages))

    print("🚀 Bot is polling...")
    app.run_polling()

if __name__ == "__main__":
    # Start Flask in a background thread
    threading.Thread(target=run_web, daemon=True).start()
    
    # Run the Bot in the main thread
    run_bot()
