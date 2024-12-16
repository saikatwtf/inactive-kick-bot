from pymongo import MongoClient
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import datetime
import config  # Import the config module

# MongoDB setup
client = MongoClient(config.MONGO_URI)
db = client[config.MONGO_DB_NAME]
users_collection = db[config.MONGO_COLLECTION_NAME]

# Inactivity threshold (in days)
INACTIVITY_THRESHOLD = config.INACTIVITY_THRESHOLD

# Command: Start
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Hi! I am the Inactivity Kicker Bot.\n"
        "I will monitor inactivity in this group and clean up as needed.\n"
        "Powerd by @AnnihilusOP"
    )

# Track user activity
def track_activity(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    username = update.message.from_user.username or update.message.from_user.first_name
    now = datetime.datetime.utcnow()

    # Upsert user activity in the database
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"username": username, "last_active": now}},
        upsert=True
    )

# Command: Show Active Users
def show_active(update: Update, context: CallbackContext) -> None:
    active_users = []
    now = datetime.datetime.utcnow()
    threshold = now - datetime.timedelta(days=INACTIVITY_THRESHOLD)

    # Fetch users active within the threshold
    for user in users_collection.find({"last_active": {"$gte": threshold}}):
        username = user['username']
        active_users.append(f"@{username}" if username else f"User {user['user_id']}")

    if active_users:
        update.message.reply_text("Active Users:\n" + "\n".join(active_users))
    else:
        update.message.reply_text("No active users found.")

# Command: Kick Inactive Users
def kick_inactive(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    now = datetime.datetime.utcnow()
    threshold = now - datetime.timedelta(days=INACTIVITY_THRESHOLD)

    # Find inactive users
    inactive_users = users_collection.find({"last_active": {"$lt": threshold}})
    for user in inactive_users:
        user_id = user['user_id']
        username = user['username']
        try:
            context.bot.kick_chat_member(chat_id, user_id)
            users_collection.delete_one({"user_id": user_id})  # Remove user from DB
            update.message.reply_text(f"Kicked @{username} for inactivity.")
        except Exception as e:
            update.message.reply_text(f"Failed to kick {username}: {e}")

# Command: Start Monitoring
def monitoring(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    context.job_queue.run_repeating(
        check_inactivity, interval=3600, first=10, context=chat_id
    )
    update.message.reply_text("Started monitoring inactivity!")

# Background Job: Check Inactivity
def check_inactivity(context: CallbackContext) -> None:
    chat_id = context.job.context
    now = datetime.datetime.utcnow()
    threshold = now - datetime.timedelta(days=INACTIVITY_THRESHOLD)

    # Find inactive users
    inactive_users = users_collection.find({"last_active": {"$lt": threshold}})
    for user in inactive_users:
        user_id = user['user_id']
        username = user['username']
        try:
            context.bot.kick_chat_member(chat_id, user_id)
            users_collection.delete_one({"user_id": user_id})  # Remove user from DB
            context.bot.send_message(chat_id, f"Kicked @{username} for inactivity.")
        except Exception as e:
            context.bot.send_message(chat_id, f"Error kicking @{username}: {e}")

# Main function
def main():
    # Initialize the bot with API token from config
    updater = Updater(config.API_TOKEN)
    dispatcher = updater.dispatcher

    # Command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("active", show_active))
    dispatcher.add_handler(CommandHandler("kickinactives", kick_inactive))
    dispatcher.add_handler(CommandHandler("monitoring", monitoring))

    # Message handler to track activity
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, track_activity))

    # Start the bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
