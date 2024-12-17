from pymongo import MongoClient
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import datetime
import config  # Import config module
import re  # To parse the threshold duration

#Dont Remove My Credit @AnnihilusOP 
#This Repo Is By SaikatWtf 
# For Any Kind Of Error Ask Us In my bot @annihilusop_bot

# MongoDB setup
client = MongoClient(config.MONGO_URI)
db = client[config.MONGO_DB_NAME]


# Helper function to check if user is an admin
def is_admin(update: Update) -> bool:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    # Get the chat's administrators
    chat_admins = update.effective_chat.get_administrators()
    return any(admin.user.id == user_id for admin in chat_admins)


# Helper function to parse time durations like 7d, 3h, 30m
def parse_duration(duration: str) -> datetime.timedelta:
    match = re.match(r"(\d+)([dhm])", duration)
    if not match:
        raise ValueError("Invalid time format. Use '7d', '3h', or '30m'.")
    value, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return datetime.timedelta(days=value)
    elif unit == "h":
        return datetime.timedelta(hours=value)
    elif unit == "m":
        return datetime.timedelta(minutes=value)


# Command: Start
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Hi! I am the Inactivity Kicker Bot.\n"
        "I will monitor inactivity in this group and clean up as needed.\n"
        "Use /sudo to toggle activity tracking on or off.\n"
        "Use /kickinactive <duration> to kick inactive users.\n"
        "Only admins can use these commands."
    )


# Command: Toggle Monitoring (Admins Only)
def monitor(update: Update, context: CallbackContext) -> None:
    if not is_admin(update):
        update.message.reply_text("Only group admins can use this command.")
        return

    chat_id = update.message.chat_id
    monitoring_collection = db["monitoring_groups"]

    # Check if monitoring is already enabled
    if monitoring_collection.find_one({"chat_id": chat_id}):
        # Monitoring is currently enabled, so disable it
        monitoring_collection.delete_one({"chat_id": chat_id})
        update.message.reply_text("Monitoring has been disabled for this group.")
    else:
        # Monitoring is not enabled, so enable it
        monitoring_collection.insert_one({"chat_id": chat_id})
        update.message.reply_text("Monitoring has been enabled for this group.")


# Track user activity
def track_activity(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    monitoring_collection = db["monitoring_groups"]

    # Check if monitoring is enabled for this group
    if not monitoring_collection.find_one({"chat_id": chat_id}):
        return  # Do nothing if monitoring is not enabled

    user_id = update.message.from_user.id
    username = update.message.from_user.username or update.message.from_user.first_name
    now = datetime.datetime.utcnow()

    # Get the collection for this group
    collection = db[f"group_{chat_id}"]

    # Upsert user activity in the group-specific collection
    collection.update_one(
        {"user_id": user_id},
        {"$set": {"username": username, "last_active": now}},
        upsert=True
    )


# Command: Kick Inactive Users (Admins Only)
def kick_inactive(update: Update, context: CallbackContext) -> None:
    if not is_admin(update):
        update.message.reply_text("Only group admins can use this command.")
        return

    chat_id = update.message.chat_id
    monitoring_collection = db["monitoring_groups"]

    if not monitoring_collection.find_one({"chat_id": chat_id}):
        update.message.reply_text("Monitoring is not enabled for this group. Use /sudo to enable it.")
        return

    collection = db[f"group_{chat_id}"]

    try:
        # Parse the duration from the command arguments
        duration = context.args[0] if context.args else None
        if not duration:
            update.message.reply_text("Please specify a duration (e.g., /kickinactive 7d).")
            return
        threshold_duration = parse_duration(duration)

        now = datetime.datetime.utcnow()
        threshold_time = now - threshold_duration

        # Find inactive users
        inactive_users = collection.find({"last_active": {"$lt": threshold_time}})
        kicked_users = []
        for user in inactive_users:
            user_id = user['user_id']
            username = user['username']
            try:
                context.bot.kick_chat_member(chat_id, user_id)
                collection.delete_one({"user_id": user_id})  # Remove user from DB
                kicked_users.append(f"@{username}" if username else f"User {user_id}")
            except Exception as e:
                update.message.reply_text(f"Failed to kick @{username}: {e}")
        
        if kicked_users:
            update.message.reply_text("Kicked the following inactive users:\n" + "\n".join(kicked_users))
        else:
            update.message.reply_text("No inactive users to kick.")
    except ValueError as e:
        update.message.reply_text(str(e))


# Command: Show Active Users
def show_active(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    collection = db[f"group_{chat_id}"]

    active_users = []
    now = datetime.datetime.utcnow()
    threshold = now - datetime.timedelta(days=7)  # Default threshold for "active users"

    # Fetch users active within the threshold
    for user in collection.find({"last_active": {"$gte": threshold}}):
        username = user['username']
        active_users.append(f"@{username}" if username else f"User {user['user_id']}")
    
    if active_users:
        update.message.reply_text("Active Users:\n" + "\n".join(active_users))
    else:
        update.message.reply_text("No active users found.")


# Main function
def main():
    # Initialize the bot with API token from config
    updater = Updater(config.API_TOKEN)
    dispatcher = updater.dispatcher

    # Command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("sudo", monitor))
    dispatcher.add_handler(CommandHandler("kickinactive", kick_inactive))
    dispatcher.add_handler(CommandHandler("active", show_active))

    # Message handler to track activity
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, track_activity))

    # Start the bot
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
