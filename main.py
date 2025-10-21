import os
import json
import datetime
import threading
from flask import Flask

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from openai import OpenAI

# -------------------- CONFIG --------------------
TELEGRAM_TOKEN = os.getenv("TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TOKEN (Telegram bot token) env var is missing.")
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY env var is missing.")

client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

USER_ID = None  # set by /me
DATA_FILE = "user_vocab.json"

# Persistent memory (per single-user bot)
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        USER_DATA = json.load(f)
else:
    USER_DATA = {"known": [], "unsure": [], "topic": None, "date": None}

SYSTEM_PROMPT = (
    "You are a kind, encouraging Korean tutor who speaks mostly in Korean. "
    "Keep replies short (2–4 sentences). If the learner makes a mistake, correct it gently, "
    "give one improved example, and briefly explain the grammar only if helpful. "
    "Avoid romanization unless requested. Encourage natural, simple Korean."
)

def save_user_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(USER_DATA, f, ensure_ascii=False, indent=2)

# -------------------- DAILY TOPIC (AI) --------------------
async def choose_and_send_daily_topic(context: ContextTypes.DEFAULT_TYPE):
    """
    Runs inside PTB JobQueue (same event loop as the bot) -> no threads/asyncio conflicts.
    """
    global USER_DATA, USER_ID
    if not USER_ID:
        print("❗ USER_ID not set yet. Ask user to run /me.")
        return

    today = str(datetime.date.today())
    # Don’t regenerate if already done today
    if USER_DATA.get("date") == today and USER_DATA.get("topic"):
        return

    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Choose a natural Korean conversation topic for today (e.g., weather, travel, shopping, feelings) and start the conversation in Korean with 2–3 short sentences."}
            ],
            temperature=0.9,
            max_tokens=180
        )
        topic_text = completion.choices[0].message.content.strip()
        USER_DATA["topic"] = topic_text
        USER_DATA["date"] = today
        save_user_data()

        await context.bot.send_message(
            chat_id=USER_ID,
            text=f"🌅 오늘의 대화 주제:\n\n{topic_text}"
        )
        print(f"✅ New daily topic generated: {topic_text[:60]}...")
    except Exception as e:
        print(f"❌ Error generating daily topic: {e}")

# -------------------- COMMANDS --------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "안녕하세요! 👋 저는 한국어 회화 선생님이에요.\n"
        "매일 아침 새로운 주제를 AI가 정하고 대화를 시작할게요.\n"
        "대화 중 모르는 단어나 문법은 편하게 물어보세요. 제가 기록해 둘게요.\n\n"
        "먼저 /me 를 입력해서 연결해 주세요!"
    )
    await update.message.reply_text(msg)

async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    USER_ID = update.message.chat_id
    await update.message.reply_text("좋아요! 😊 이제 매일 아침 새로운 대화 주제를 보낼게요.")
    print(f"✅ USER_ID set to {USER_ID}")

async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger to generate/send today’s topic now (useful for testing)."""
    await choose_and_send_daily_topic(context)

async def cmd_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unsure = USER_DATA.get("unsure", [])
    if not unsure:
        await update.message.reply_text("오늘 모르는 단어가 없네요! 잘하셨어요 👏")
        return

    prompt = (
        f"You are a Korean tutor. Review these Korean words/phrases the learner was unsure about: {unsure}. "
        "For each, give the meaning, one Korean example sentence + short English gloss, and one brief grammar tip if relevant. "
        "Then make a short quiz (2–3 questions) for recall."
    )
    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=450
        )
        review = completion.choices[0].message.content.strip()
    except Exception as e:
        review = f"⚠️ 복습 중 오류가 발생했어요: {e}"

    await update.message.reply_text(f"🧠 오늘의 복습:\n\n{review}")
    USER_DATA["unsure"].clear()
    save_user_data()

async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"USER_ID: {USER_ID}\n"
        f"Date: {USER_DATA.get('date')}\n"
        f"Topic set: {bool(USER_DATA.get('topic'))}\n"
        f"Unsure count: {len(USER_DATA.get('unsure', []))}"
    )

# -------------------- CHAT HANDLER --------------------
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Heuristic: learner uncertainty markers -> store the raw text they asked about
    if any(k in text for k in ["?", "뜻", "몰라", "모르", "what", "meaning"]):
        USER_DATA["unsure"].append(text)
        save_user_data()

    topic = USER_DATA.get("topic") or "일상적인 대화"

    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nToday's topic:\n{topic}"},
                {"role": "user", "content": text}
            ],
            temperature=0.8,
            max_tokens=280
        )
        reply = completion.choices[0].message.content.strip()
    except Exception as e:
        reply = f"⚠️ 오류가 발생했어요: {e}"

    await update.message.reply_text(reply)

# -------------------- BOT (MAIN THREAD) --------------------
def run_bot_main_thread():
    """
    Run PTB in the main thread so signal handlers are fine.
    Use JobQueue (built-in) for daily topic instead of APScheduler.
    """
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("topic", cmd_topic))   # manual daily topic trigger
    app.add_handler(CommandHandler("finish", cmd_finish))
    app.add_handler(CommandHandler("debug", cmd_debug))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    # JobQueue: generate a topic soon after boot, then every 24h
    # First run after 10 seconds so you can test quickly, then repeat daily.
    app.job_queue.run_repeating(choose_and_send_daily_topic, interval=24*60*60, first=10)

    print("🤖 Korean AI Tutor started (main thread, JobQueue scheduler).")
    # IMPORTANT: Keep signals disabled on Render if you ever move this to a thread.
    # In main thread, default is fine; still safe to pass stop_signals=None.
    app.run_polling(stop_signals=None)

# -------------------- FLASK (BACKGROUND THREAD) --------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Korean Tutor Bot is running (OpenRouter, dynamic topics + review)."

def run_flask_background():
    port = int(os.environ.get("PORT", 10000))
    # threaded=True keeps it lightweight while the bot runs in the main thread
    flask_app.run(host="0.0.0.0", port=port, threaded=True)

# -------------------- ENTRYPOINT --------------------
if __name__ == "__main__":
    # 1) Start Flask in a background thread (to keep Render 'web service' alive)
    threading.Thread(target=run_flask_background, daemon=True).start()

    # 2) Run Telegram bot in the MAIN thread (no signal errors)
    run_bot_main_thread()
