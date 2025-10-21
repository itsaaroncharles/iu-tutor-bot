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
    "You are IU, a friendly Korean best friend and tutor. Keep responses SHORT and natural - just 1-2 sentences in Korean, then English translation in parentheses. "
    "Use only modern, everyday Korean words. Be encouraging but concise. "
    "If user writes Korean, give ONE brief tip about their grammar/vocabulary, then continue the conversation naturally. "
    "Never repeat yourself or give multiple explanations for the same thing. "
    "Never start with <s> or special tokens."
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
                {"role": "user", "content": "Start a short, fun conversation topic in Korean (1-2 sentences max) with English translation. Be enthusiastic but brief!"}
            ],
            temperature=0.8,
            max_tokens=120
        )
        topic_text = completion.choices[0].message.content.strip()
        
        # Clean up any unwanted prefixes
        if topic_text.startswith("<s>"):
            topic_text = topic_text[3:].strip()
        if topic_text.startswith("<"):
            topic_text = topic_text.split(">", 1)[-1].strip()
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
        "안녕! 👋 나는 IU야! 너의 한국어 친구이자 선생님이 될게!\n"
        "매일 재미있는 주제로 대화하고, 한국어 실력을 늘려보자!\n"
        "틀려도 괜찮아 - 내가 친절하게 도와줄게. 그리고 더 자연스러운 표현도 알려줄게!\n\n"
        "먼저 /me 를 눌러서 시작해줘!\n\n"
        "(Hi! 👋 I'm IU! I'll be your Korean friend and teacher!\n"
        "Let's chat about fun topics every day and improve your Korean!\n"
        "It's okay to make mistakes - I'll help you kindly and teach you more natural expressions!\n\n"
        "First, press /me to get started!)"
    )
    await update.message.reply_text(msg)

async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    USER_ID = update.message.chat_id
    await update.message.reply_text(
        "야호! 😊 이제 우리 친구야! 매일 재미있는 주제로 대화해보자!\n\n"
        "(Yay! 😊 Now we're friends! Let's chat about fun topics every day!)"
    )
    print(f"✅ USER_ID set to {USER_ID}")

async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger to generate/send today’s topic now (useful for testing)."""
    await choose_and_send_daily_topic(context)

async def cmd_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unsure = USER_DATA.get("unsure", [])
    if not unsure:
        await update.message.reply_text(
            "오늘 모르는 게 없었네! 정말 잘했어! 👏\n\n"
            "(You didn't have anything you didn't know today! You did really well! 👏)"
        )
        return

    prompt = (
        f"You are IU, a friendly Korean tutor. Review these Korean words/phrases the learner was unsure about: {unsure}. "
        "Use only modern, commonly used Korean words in your explanations. "
        "For each unclear item, give the meaning, one simple Korean example sentence, and brief grammar tip if helpful. "
        "Then make a short, fun quiz (2–3 questions) for practice. "
        "Be encouraging and friendly like a best friend. End with English translation in parentheses."
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
        
        # Clean up any unwanted prefixes
        if review.startswith("<s>"):
            review = review[3:].strip()
        if review.startswith("<"):
            review = review.split(">", 1)[-1].strip()
            
    except Exception as e:
        review = f"앗, 복습하려다가 문제가 생겼어! 나중에 다시 해보자! 😅\n\n(Oops, there was a problem trying to review! Let's try again later! 😅)\n\nError: {e}"

    await update.message.reply_text(f"🧠 오늘 공부한 것들 정리해볼까?\n\n{review}")
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
    
    # Don't respond to empty messages
    if not text:
        return

    print(f"💬 Received message: {text}")  # Debug logging

    # Heuristic: learner uncertainty markers -> store the raw text they asked about
    if any(k in text for k in ["?", "뜻", "몰라", "모르", "what", "meaning"]):
        USER_DATA["unsure"].append(text)
        save_user_data()
        print(f"📝 Added to unsure list: {text}")

    # Always be ready to chat - don't rely only on daily topics
    topic = USER_DATA.get("topic") or "자유로운 한국어 대화 (free Korean conversation)"

    # Detect if user is writing in Korean (only if substantial Korean content)
    korean_chars = sum(1 for char in text if '\uac00' <= char <= '\ud7a3')
    has_korean = korean_chars >= 2  # Need at least 2 Korean characters to count
    
    # Check if conversation is getting dry (short responses)
    is_dry_response = len(text.strip()) <= 15 and not any(k in text.lower() for k in ["?", "뭐", "왜", "어떻게", "언제", "어디", "what", "how", "why"])

    try:
        print(f"🤖 Making API call to OpenRouter...")
        
        # Simple, focused prompt to avoid repetition
        if has_korean:
            enhanced_prompt = f"{SYSTEM_PROMPT}\n\nUser wrote in Korean. Give ONE quick tip about their Korean, then respond naturally to continue the conversation. Keep it short - max 2 sentences + English translation."
        elif is_dry_response:
            enhanced_prompt = f"{SYSTEM_PROMPT}\n\nUser seems quiet. Ask ONE engaging question to keep the conversation going. Keep it short and friendly."
        else:
            enhanced_prompt = f"{SYSTEM_PROMPT}\n\nRespond naturally to continue the conversation. Keep it short and friendly."

        completion = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[
                {"role": "system", "content": enhanced_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.7,
            max_tokens=150
        )
        reply = completion.choices[0].message.content.strip()
        print(f"✅ API response received: {reply[:50]}...")
        
        # Clean up any unwanted prefixes and repetitions
        if reply.startswith("<s>"):
            reply = reply[3:].strip()
        if reply.startswith("<"):
            reply = reply.split(">", 1)[-1].strip()
        
        # Remove duplicate lines that often cause repetition
        lines = reply.split('\n')
        clean_lines = []
        seen_lines = set()
        for line in lines:
            line_clean = line.strip()
            if line_clean and line_clean not in seen_lines:
                clean_lines.append(line)
                seen_lines.add(line_clean)
        reply = '\n'.join(clean_lines)
        
        # Fallback if API returns empty response
        if not reply or len(reply.strip()) == 0:
            reply = "어? 뭔가 이상해! 다시 말해줘! 😅\n\n(Huh? Something's weird! Tell me again! 😅)"
            
    except Exception as e:
        print(f"❌ API Error: {e}")
        reply = f"앗, 뭔가 문제가 생겼어! 잠깐 후에 다시 말해줘! 😅\n\n(Oops, something went wrong! Tell me again in a bit! 😅)\n\nError: {str(e)}"

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

    print("🎤 IU Korean Tutor started! Ready to be your Korean best friend and teacher!")
    # IMPORTANT: Keep signals disabled on Render if you ever move this to a thread.
    # In main thread, default is fine; still safe to pass stop_signals=None.
    app.run_polling(stop_signals=None)

# -------------------- FLASK (BACKGROUND THREAD) --------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "IU Korean Tutor Bot is running! Your friendly Korean learning companion 🎤"

def run_flask_background():
    port = int(os.environ.get("PORT", 10000))
    # threaded=True keeps it lightweight while the bot runs in the main thread
    flask_app.run(host="0.0.0.0", port=port, threaded=True, debug=False, use_reloader=False)

# -------------------- ENTRYPOINT --------------------
if __name__ == "__main__":
    print("🚀 Starting IU Korean Tutor Bot - Your friendly Korean learning companion!")
    print(f"📝 Environment check - TELEGRAM_TOKEN: {'✅ Set' if TELEGRAM_TOKEN else '❌ Missing'}")
    print(f"📝 Environment check - OPENROUTER_API_KEY: {'✅ Set' if OPENROUTER_API_KEY else '❌ Missing'}")
    print(f"📝 Environment check - PORT: {os.environ.get('PORT', '10000 (default)')}")
    
    try:
        # 1) Start Flask in a background thread (to keep Render 'web service' alive)
        print("🌐 Starting Flask server in background thread...")
        threading.Thread(target=run_flask_background, daemon=True).start()

        # 2) Run Telegram bot in the MAIN thread (no signal errors)
        print("🎤 Starting IU Telegram bot in main thread...")
        run_bot_main_thread()
    except Exception as e:
        print(f"❌ Critical startup error: {e}")
        import traceback
        traceback.print_exc()
        raise
