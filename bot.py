import os
import sqlite3
import datetime
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configurations
# Using environment variables for sensitive data
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

# DB Setup
DB_FILE = "bot_database.db"

def init_db():
    """Initialize the SQLite database for tracking user usage."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usage (
            user_id INTEGER,
            year_month TEXT,
            message_count INTEGER,
            PRIMARY KEY (user_id, year_month)
        )
    ''')
    conn.commit()
    conn.close()

def increment_usage(user_id: int):
    """Increment the monthly message count for a user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_month = datetime.datetime.now().strftime("%Y-%m")

    cursor.execute('''
        INSERT INTO usage (user_id, year_month, message_count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, year_month)
        DO UPDATE SET message_count = message_count + 1
    ''', (user_id, current_month))

    conn.commit()
    conn.close()

def get_usage(user_id: int) -> int:
    """Get the message count for a user for the current month."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_month = datetime.datetime.now().strftime("%Y-%m")

    cursor.execute('SELECT message_count FROM usage WHERE user_id = ? AND year_month = ?', (user_id, current_month))
    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]
    return 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"مرحباً {user.mention_html()}!\n"
        f"أنا بوت ذكي أستخدم نموذج Gemini 2.5 Flash من Google.\n"
        f"أرسل لي أي رسالة وسأقوم بالرد عليها، وسأقوم بتسجيل استخدامك الشهري."
    )

async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the current month's usage for the user."""
    user_id = update.message.from_user.id
    usage_count = get_usage(user_id)
    await update.message.reply_text(f"لقد قمت بإرسال {usage_count} رسائل هذا الشهر.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages and reply using Gemini 2.5 Flash."""
    user_id = update.message.from_user.id
    text = update.message.text

    # Track usage
    increment_usage(user_id)

    try:
        # Call Gemini 2.5 Flash using the google-genai library
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=text,
        )
        reply_text = response.text
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        reply_text = f"عذراً، حدث خطأ أثناء الاتصال بالنموذج الذكي."

    await update.message.reply_text(reply_text)

app = Flask(__name__)

@app.route("/")
def health_check():
    return "Bot is running"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def main() -> None:
    """Start the bot."""
    # Initialize the database
    init_db()

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("usage", usage_command))

    # Message handler (for any text message that isn't a command)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start Flask app in a background thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main()
