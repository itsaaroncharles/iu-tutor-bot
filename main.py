import os, json, datetime, threading, asyncio
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

# --------- ENV ----------
TOKEN = os.getenv("TOKEN")  # Telegram BotFather token
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # OpenRouter key
if not TOKEN:
    print("❗ ENV missing TOKEN")
if not OPENROUTER_API_KEY:
    print("❗ ENV missing OPENROUTER_API_KEY")

client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

# --------- SIMPLE PERSISTENCE ----------
DATA_FILE = "user_vocab.json"
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        USER_DATA = json.load(f)
else:
    USER_DATA = {"unsure": [], "topic": None, "date": None}

def save_user_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(USER_DATA, f, ensure_ascii=False, indent=2)

USER_ID = None  # set by /me

SYSTEM_PROMPT = (
    "You are a kind, encouraging Korean tutor. "
    "Speak mostly in Korean in short (2–4) sentences. "
    "If needed, gently correct grammar, provide one improved example, and "
    "add a brief grammar note only when helpful. Avoid romanization unless asked."
)

# --------- AI HELPERS ----------
async def ai_chat(prompt_messages, max_tokens=250, temperature=0.8, model="mistralai/mistral-7b-instruct"):
    resp = client.chat.completions.create(
        model=model,
        messages=prompt_messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()

# --------- DAILY TOPIC (runs inside bot thread loop) ----------
async def generate_daily_topic(bot):
    today = str(datetime.date.today())
    if not USER_ID:
        print("ℹ️ USER_ID not set yet; skip daily topic.")
        return
    if USER_DATA.get("date") == today:
        return  # already generated today

    topic_text = await ai_chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Choose a natural, practical Korean conversation topic for today and start the conversation in Korean (1–3 sentences)."}
        ],
        max_tokens=160,
        temperature=0.9
    )
    USER_DATA["topic"] = topic_text
    USER_DATA["date"] = today
    save_user_data()
    await bot.send_message(chat_id=USER_ID, text=f"🌅 오늘의 대화 주제:\n\n{topic_text}")
    print(f"✅ Daily topic set: {topic_text[:60]}...")

# --------- TELEGRAM HANDLERS (all run in bot thread) ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "안녕하세요! 👋 한국어 회화 선생님이에요.\n"
        "매일 아침 새로운 주제를 제가 정해서 대화를 시작해요.\n"
        "모르는 단어나 문법은 물어보세요. 나중에 복습해 드릴게요.\n\n"
        "먼저 /me 로 연결해 주세요!"
    )
    await update.message.reply_text(msg)

async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    USER_ID = update.message.chat_id
    await update.message.reply_text("좋아요! 😊 이제 매일 아침 새로운 대화 주제를 보낼게요.")
    # kick off today's topic immediately
    await generate_daily_topic(context.bot)
    print(f"✅ USER_ID set to {USER_ID}")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # If user expresses uncertainty, remember it
    if any(k in text for k in ["?", "뜻", "몰라", "모르", "what", "meaning"]):
        USER_DATA["unsure"].append(text)
        save_user_data()

    topic = USER_DATA.get("topic") or "일상적인 대화"
    reply = await ai_chat(
        [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\nToday's theme (as starter text): {topic}"},
            {"role": "user", "content": text}
        ],
        max_tokens=260,
        temperature=0.8
    )
    await update.message.reply_text(reply)

async def cmd_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unsure = USER_DATA.get("unsure", [])
    if not unsure:
        await update.message.reply_text("오늘 모르는 단어가 없네요! 잘하셨어요 👏")
        return

    review = await ai_chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                "Review these Korean words/phrases the learner was unsure about: "
                f"{unsure}. For each: (1) meaning, (2) one example sentence in Korean "
                "with English meaning, (3) one short grammar tip if helpful. "
                "Then give a mini-quiz (2–3 items) for recall."
            )}
        ],
        max_tokens=420,
        temperature=0.7
    )
    await update.message.reply_text(f"🧠 오늘의 복습:\n\n{review}")
    USER_DATA["unsure"].clear()
    save_user_data()

async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🔍 Debug\nUSER_ID: {USER_ID}\nDate: {USER_DATA.get('date')}\n"
        f"Topic: {USER_DATA.get('topic')}\nUnsure count: {len(USER_DATA.get('unsure', []))}"
    )

# --------- BOT THREAD ---------
def run_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("finish", cmd_finish))
    app.add_handler(CommandHandler("debug", cmd_debug))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    # Scheduler that safely calls coroutine in this thread's loop
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(generate_daily_topic(app.bot), loop),
                      "interval", hours=24)
    scheduler.start()

    print("🤖 Korean AI Tutor started (OpenRouter).")
    loop.run_until_complete(app.run_polling())
    loop.close()

# --------- FLASK (main thread) ---------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Korean Tutor Bot (OpenRouter) running. ✅", 200

if __name__ == "__main__":
    # Start Telegram bot in background thread with its own event loop
    threading.Thread(target=run_bot_thread, daemon=True).start()
    # Run Flask in main thread for Render healthcheck
    port = int(os.getenv("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, threaded=True)
