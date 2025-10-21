import os, asyncio, random
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)

USER_ID = None

DAILY_TOPICS = [
    "카페에서 주문하기 (Ordering at a café)",
    "공항에서 체크인하기 (Airport check-in)",
    "방 안의 물건 묘사하기 (Describing things in a room)",
    "식당에서 주문하기 (Ordering at a restaurant)",
    "길 묻기 (Asking for directions)",
    "기분 표현하기 (Expressing feelings)"
]

SYSTEM_PROMPT = (
    "You are a friendly Korean language tutor. "
    "Speak mostly in Korean, using short sentences. "
    "If the user makes a grammar mistake, gently correct it and show one improved sentence. "
    "Then ask a small follow-up question to continue the dialogue. "
    "Keep replies natural and encouraging."
)

# --- Daily topic broadcast ---
async def send_daily_topic(context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    if not USER_ID:
        print("USER_ID not set yet. Use /me to link Telegram user.")
        return
    topic = random.choice(DAILY_TOPICS)
    await context.bot.send_message(
        chat_id=USER_ID,
        text=f"📚 오늘의 주제: {topic}\n\n이 주제로 대화해 봐요! 먼저 한 문장으로 시작해 보세요."
    )

# --- Commands ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "안녕하세요! 👋 저는 한국어 회화 선생님이에요.\n"
        "매일 간단한 주제를 보내드릴게요. 자유롭게 한국어로 대화하면 제가 자연스럽게 도와드릴게요.\n\n"
        "먼저 /me 로 내 계정을 연결해주세요!"
    )
    await update.message.reply_text(msg)

async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    USER_ID = update.message.chat_id
    await update.message.reply_text("좋아요! 이제 매일 한국어 대화 주제를 보낼게요 😊")
    print(f"✅ USER_ID set to: {USER_ID}")

# --- Main chat handler (AI-driven) ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",  # free, good Korean support
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ],
            max_tokens=250,
            temperature=0.8,
        )
        reply = completion.choices[0].message.content.strip()
    except Exception as e:
        reply = f"⚠️ 오류가 발생했어요: {e}"
    await update.message.reply_text(reply)

# --- Scheduler + Telegram setup ---
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.create_task(send_daily_topic(app.bot)), "interval", hours=24)
    scheduler.start()

    print("🤖 Korean AI Tutor Bot started (OpenRouter)")
    await app.run_polling()

# --- Keep-alive Flask server for Render ---
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Korean Tutor Bot is running (OpenRouter)."

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main())
