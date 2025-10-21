import os, asyncio, random, datetime
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

USER_ID = None
DAILY_TOPIC = {"date": None, "topic": None}

SYSTEM_PROMPT = (
    "You are a friendly and encouraging Korean language tutor. "
    "Each morning, you choose a random, practical daily conversation topic "
    "(like travel, weather, family, shopping, emotions, etc.) "
    "and start a short dialogue in Korean with the student. "
    "When replying, speak naturally in Korean, correct mistakes gently, "
    "and ask follow-up questions to keep the conversation going."
)

# --- Generate a new topic every morning ---
async def generate_daily_topic(context: ContextTypes.DEFAULT_TYPE):
    global DAILY_TOPIC, USER_ID
    if not USER_ID:
        print("❗ USER_ID not set yet. Use /me in Telegram.")
        return

    today = datetime.date.today()
    if DAILY_TOPIC["date"] == today:
        return  # Already generated today

    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Please choose a new Korean daily conversation topic for today and start the conversation in Korean."}
            ],
            temperature=0.9,
            max_tokens=180
        )
        ai_message = completion.choices[0].message.content.strip()
        DAILY_TOPIC = {"date": today, "topic": ai_message}
        await context.bot.send_message(chat_id=USER_ID, text=f"🌅 오늘의 대화 주제:\n\n{ai_message}")
        print(f"✅ New daily topic: {ai_message[:50]}...")
    except Exception as e:
        print(f"Error generating daily topic: {e}")

# --- Telegram Commands ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "안녕하세요! 👋 저는 당신의 한국어 회화 선생님이에요.\n"
        "매일 아침 새로운 주제를 직접 정해서 한국어로 대화를 시작할게요.\n\n"
        "먼저 /me 로 저에게 인사해주세요!"
    )
    await update.message.reply_text(msg)

async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    USER_ID = update.message.chat_id
    await update.message.reply_text("좋아요! 😊 이제 매일 아침 새로운 대화 주제를 보낼게요.")
    print(f"✅ USER_ID set to {USER_ID}")

# --- Chat Handler (AI replies naturally around the current topic) ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()

    today = datetime.date.today()
    topic_text = DAILY_TOPIC["topic"] if DAILY_TOPIC["date"] == today else "일상적인 대화 (daily life conversation)"

    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nToday's topic: {topic_text}"},
                {"role": "user", "content": user_input}
            ],
            temperature=0.8,
            max_tokens=250,
        )
        reply = completion.choices[0].message.content.strip()
    except Exception as e:
        reply = f"⚠️ 오류가 발생했어요: {e}"

    await update.message.reply_text(reply)

# --- Scheduler & App Runner ---
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.create_task(generate_daily_topic(app.bot)), "interval", hours=24)
    scheduler.start()

    print("🤖 AI Korean Tutor (Dynamic Topics via OpenRouter) started.")
    await app.run_polling()

# --- Keep-alive Flask for Render ---
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Korean AI Tutor Bot is running (OpenRouter, dynamic topics)."

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main())
import os, asyncio, random, datetime
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

USER_ID = None
DAILY_TOPIC = {"date": None, "topic": None}

SYSTEM_PROMPT = (
    "You are a friendly and encouraging Korean language tutor. "
    "Each morning, you choose a random, practical daily conversation topic "
    "(like travel, weather, family, shopping, emotions, etc.) "
    "and start a short dialogue in Korean with the student. "
    "When replying, speak naturally in Korean, correct mistakes gently, "
    "and ask follow-up questions to keep the conversation going."
)

# --- Generate a new topic every morning ---
async def generate_daily_topic(context: ContextTypes.DEFAULT_TYPE):
    global DAILY_TOPIC, USER_ID
    if not USER_ID:
        print("❗ USER_ID not set yet. Use /me in Telegram.")
        return

    today = datetime.date.today()
    if DAILY_TOPIC["date"] == today:
        return  # Already generated today

    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Please choose a new Korean daily conversation topic for today and start the conversation in Korean."}
            ],
            temperature=0.9,
            max_tokens=180
        )
        ai_message = completion.choices[0].message.content.strip()
        DAILY_TOPIC = {"date": today, "topic": ai_message}
        await context.bot.send_message(chat_id=USER_ID, text=f"🌅 오늘의 대화 주제:\n\n{ai_message}")
        print(f"✅ New daily topic: {ai_message[:50]}...")
    except Exception as e:
        print(f"Error generating daily topic: {e}")

# --- Telegram Commands ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "안녕하세요! 👋 저는 당신의 한국어 회화 선생님이에요.\n"
        "매일 아침 새로운 주제를 직접 정해서 한국어로 대화를 시작할게요.\n\n"
        "먼저 /me 로 저에게 인사해주세요!"
    )
    await update.message.reply_text(msg)

async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    USER_ID = update.message.chat_id
    await update.message.reply_text("좋아요! 😊 이제 매일 아침 새로운 대화 주제를 보낼게요.")
    print(f"✅ USER_ID set to {USER_ID}")

# --- Chat Handler (AI replies naturally around the current topic) ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()

    today = datetime.date.today()
    topic_text = DAILY_TOPIC["topic"] if DAILY_TOPIC["date"] == today else "일상적인 대화 (daily life conversation)"

    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nToday's topic: {topic_text}"},
                {"role": "user", "content": user_input}
            ],
            temperature=0.8,
            max_tokens=250,
        )
        reply = completion.choices[0].message.content.strip()
    except Exception as e:
        reply = f"⚠️ 오류가 발생했어요: {e}"

    await update.message.reply_text(reply)

# --- Scheduler & App Runner ---
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.create_task(generate_daily_topic(app.bot)), "interval", hours=24)
    scheduler.start()

    print("🤖 AI Korean Tutor (Dynamic Topics via OpenRouter) started.")
    await app.run_polling()

# --- Keep-alive Flask for Render ---
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Korean AI Tutor Bot is running (OpenRouter, dynamic topics)."

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main())