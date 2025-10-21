import os, asyncio, datetime, json, threading
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

# --- CONFIG ---
TELEGRAM_TOKEN = os.getenv("TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

USER_ID = None
DATA_FILE = "user_vocab.json"

# Load or initialize persistent memory
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        USER_DATA = json.load(f)
else:
    USER_DATA = {"known": [], "unsure": [], "topic": None, "date": None}

SYSTEM_PROMPT = (
    "You are a kind, encouraging Korean tutor who speaks mostly in Korean. "
    "Keep replies short (2–4 sentences). If the learner makes a mistake, correct it gently, "
    "give one improved example, and briefly explain the grammar only if it helps understanding. "
    "Avoid romanization unless requested. Always encourage the learner to speak naturally."
)

# --- SAVE/LOAD ---
def save_user_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(USER_DATA, f, ensure_ascii=False, indent=2)

# --- DAILY TOPIC GENERATOR ---
async def generate_daily_topic(context: ContextTypes.DEFAULT_TYPE):
    global USER_DATA, USER_ID
    today = str(datetime.date.today())

    if not USER_ID:
        print("❗ USER_ID not set. Use /me in Telegram first.")
        return
    if USER_DATA.get("date") == today:
        return  # already generated today

    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Choose a natural Korean conversation topic for today (e.g. weather, travel, shopping, feelings). Start the conversation in Korean."}
            ],
            max_tokens=150,
            temperature=0.9,
        )
        topic = completion.choices[0].message.content.strip()
        USER_DATA.update({"topic": topic, "date": today})
        save_user_data()
        await context.bot.send_message(chat_id=USER_ID, text=f"🌅 오늘의 대화 주제:\n\n{topic}")
        print(f"✅ New daily topic generated: {topic[:40]}...")
    except Exception as e:
        print(f"❌ Error generating daily topic: {e}")

# --- COMMANDS ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "안녕하세요! 👋 저는 한국어 회화 선생님이에요.\n"
        "매일 아침 새로운 주제를 직접 정하고 대화를 시작할게요.\n"
        "대화 중 모르는 단어나 문법은 물어보세요. 제가 기록해 둘게요.\n\n"
        "먼저 /me 를 입력해서 연결해 주세요!"
    )
    await update.message.reply_text(msg)

async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    USER_ID = update.message.chat_id
    await update.message.reply_text("좋아요! 😊 이제 매일 아침 새로운 대화 주제를 보낼게요.")
    print(f"✅ USER_ID set to {USER_ID}")

# --- CHAT HANDLER ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_DATA
    text = update.message.text.strip()

    # Detect if user asks about meaning/unknown words
    if any(phrase in text for phrase in ["?", "뜻", "몰라", "모르", "what", "meaning"]):
        USER_DATA["unsure"].append(text)
        save_user_data()

    topic = USER_DATA.get("topic") or "일상적인 대화"

    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nToday's topic: {topic}"},
                {"role": "user", "content": text}
            ],
            max_tokens=250,
            temperature=0.8,
        )
        reply = completion.choices[0].message.content.strip()
    except Exception as e:
        reply = f"⚠️ 오류가 발생했어요: {e}"

    await update.message.reply_text(reply)

# --- FINISH / REVIEW COMMAND ---
async def cmd_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_DATA
    unsure = USER_DATA.get("unsure", [])
    if not unsure:
        await update.message.reply_text("오늘 모르는 단어가 없네요! 잘하셨어요 👏")
        return

    prompt = (
        f"You are a Korean tutor. Review these Korean words or phrases the learner was unsure about: {unsure}. "
        "For each, explain its meaning, show one example sentence in Korean with English meaning, "
        "and if possible, briefly mention one grammar tip related to it. "
        "Then make a short quiz (2–3 questions) to test recall."
    )
    try:
        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.7,
        )
        review = completion.choices[0].message.content.strip()
    except Exception as e:
        review = f"⚠️ 복습 중 오류가 발생했어요: {e}"

    await update.message.reply_text(f"🧠 오늘의 복습:\n\n{review}")
    USER_DATA["unsure"].clear()
    save_user_data()

# --- DEBUG COMMAND ---
async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID, USER_DATA
    msg = (
        f"🔍 Debug Info:\n"
        f"USER_ID: {USER_ID}\n"
        f"Topic: {USER_DATA.get('topic')}\n"
        f"Unsure words: {len(USER_DATA.get('unsure', []))}\n"
        f"Date: {USER_DATA.get('date')}"
    )
    await update.message.reply_text(msg)

# --- MAIN APP ---
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("finish", cmd_finish))
    app.add_handler(CommandHandler("debug", cmd_debug))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.create_task(generate_daily_topic(app.bot)), "interval", hours=24)
    scheduler.start()

    print("🤖 Korean AI Tutor (Dynamic Topics + Review System) started.")
    await app.run_polling()

# --- FLASK KEEP-ALIVE FOR RENDER ---
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Korean Tutor Bot (AI dynamic topics + review memory) running!"

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080, threaded=True)

if __name__ == "__main__":
    # Run Flask in background thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Run Telegram bot cleanly without asyncio.run()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())