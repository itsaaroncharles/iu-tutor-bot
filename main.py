from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler
import random, asyncio, os
from flask import Flask
from threading import Thread

TOKEN = os.getenv("TOKEN")
USER_ID = None

topics = {
    "방 (room)": ["의자 (chair)", "책상 (desk)", "문 (door)", "창문 (window)"],
    "카페 (cafe)": ["커피 (coffee)", "빵 (bread)", "메뉴판 (menu)", "점원 (staff)"],
    "공항 (airport)": ["비행기 (airplane)", "표 (ticket)", "짐 (luggage)", "여권 (passport)"]
}

async def send_daily_topic(context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    if USER_ID is None:
        print("❗ USER_ID not set yet. Use /me to set it.")
        return
    topic, words = random.choice(list(topics.items()))
    vocab = ", ".join(words)
    msg = f"📚 오늘의 주제: {topic}\n단어들: {vocab}\n\n이 단어로 문장 만들어볼까요?"
    await context.bot.send_message(chat_id=USER_ID, text=msg)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "안녕하세요! 👋 저는 당신의 한국어 연습 파트너예요.\n"
        "매일 하나의 주제로 대화해요.\n\n"
        "먼저 /me 를 눌러 나에게 인사해주세요!"
    )

async def set_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ID
    USER_ID = update.message.chat_id
    await update.message.reply_text("좋아요! 이제 매일 주제를 보낼게요 😊")
    print(f"✅ USER_ID set to: {USER_ID}")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    responses = [
        "좋아요! 다른 단어로 문장 만들어볼까요?",
        "멋져요! 조금 더 길게 말해보세요!",
        "잘했어요 👏 다음엔 카페에 있는 물건으로 해볼까요?",
        "훌륭해요! 발음 연습도 잊지 마세요 ☺️"
    ]
    await update.message.reply_text(random.choice(responses))

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("me", set_me))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.create_task(send_daily_topic(app.bot)), "interval", hours=24)
    scheduler.start()

    print("🤖 Bot started!")
    await app.run_polling()

# Keep-alive web server (Render requirement)
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main())
