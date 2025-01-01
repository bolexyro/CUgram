import os
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import firebase_admin
from firebase_admin import credentials, firestore_async, firestore
from pydantic import BaseModel
from fastapi import FastAPI


class Message(BaseModel):
    text: str
    attachment_url: str | None = None
    content_type: str | None = None


load_dotenv()

BOT_URL_BASE = os.getenv("STUDENT_BOT_URL_BASE")
AUTH_URL_BASE = os.getenv("AUTH_URL_BASE")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
BOT_TOKEN = os.getenv('STUDENT_BOT_TOKEN')
USERS_COLLECTION = "users"

app = FastAPI()
bot = telebot.TeleBot(BOT_TOKEN)

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db_async = firestore_async.client()
db_without_async = firestore.client()


def gen_markup(user_id: str):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton(
        "Authorize me", url=f'{AUTH_URL_BASE}authorize/{user_id}'))
    return markup


@app.post(path=f"/{BOT_TOKEN}")
def process_webhook_text_pay_bot(update: dict):
    """
    Process webhook calls for cugram
    """
    if update:
        update = telebot.types.Update.de_json(update)
        bot.process_new_updates([update])
    else:
        return


@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_ref = db_without_async.collection(
        USERS_COLLECTION).document(str(message.from_user.id))
    user = user_ref.get()
    if user.exists:
        user = user.to_dict()
        bot.send_message(chat_id=message.from_user.id,
                         text=f"You're already verified with your Covenant University email  {user['email']}. Feel free to continue using the bot.")
        return
    bot.send_message(chat_id=message.from_user.id,
                     text="Hello! To access this bot, you need to verify that you have a valid Covenant University email. Please sign in with your Google account using the button below.", reply_markup=gen_markup(message.from_user.id))


@app.get('/auth-complete/{user_id}')
def on_auth_completed(user_id: str):
    bot.send_message(
        user_id, text='Thank you for verifying your Covenant University email! You\'re now authorized to use the bot and receive messages.✅')


@app.post(path='/message')
def receive_message_handler(message: Message):
    docs = db_without_async.collection(USERS_COLLECTION).stream()
    for doc in docs:
        try:
            bot.send_message(doc.id, text=message.text)
            if message.attachment_url:
                if message.content_type == 'audio':
                    bot.send_audio(doc.id, audio=message.attachment_url)
                elif message.content_type == 'photo':
                    bot.send_photo(doc.id, photo=message.attachment_url)
                elif message.content_type == 'voice':
                    bot.send_voice(doc.id, voice=message.attachment_url)
                elif message.content_type == 'video':
                    bot.send_video(doc.id, video=message.attachment_url)
                elif message.content_type == 'document':
                    bot.send_document(doc.id, document=message.attachment_url)
        except:
            pass


bot.remove_webhook()

# Set webhook
bot.set_webhook(
    url=BOT_URL_BASE + BOT_TOKEN
)

# bot.polling()
