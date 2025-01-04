from models.schemas import Message, DownloadedAttachment
from models.enums import CloudCollections
import os
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import firebase_admin
from firebase_admin import credentials, firestore_async, firestore
from fastapi import FastAPI, status, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import aiohttp
import io
from typing import Annotated

load_dotenv()

BOT_URL_BASE = os.getenv("STUDENT_BOT_URL_BASE")
AUTH_URL_BASE = os.getenv("AUTH_URL_BASE")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
BOT_TOKEN = os.getenv('STUDENT_BOT_TOKEN')
SECRET_TOKEN = os.getenv("STUDENT_BOT_SERVER_SECRET_TOKEN")

app = FastAPI()
bot = telebot.TeleBot(BOT_TOKEN)

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db_async = firestore_async.client()
db_without_async = firestore.client()

security = HTTPBearer()


def verify_token(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    if credentials.credentials != SECRET_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing token",
        )


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
    student_ref = db_without_async.collection(
        CloudCollections.students.value).document(str(message.from_user.id))
    student = student_ref.get()
    if student.exists:
        student = student.to_dict()
        bot.send_message(chat_id=message.from_user.id,
                         text=f"You're already verified with your Covenant University email  {student['email']}. Feel free to continue using the bot.")
        return
    bot.send_message(chat_id=message.from_user.id,
                     text="Hello! To access this bot, you need to verify that you have a valid Covenant University email. Please sign in with your Google account using the button below.", reply_markup=gen_markup(message.from_user.id))


@app.get('/auth-complete/{user_id}', dependencies=[Depends(verify_token)])
def on_auth_completed(user_id: str):
    bot.send_message(
        user_id, text='Thank you for verifying your Covenant University email! You\'re now authorized to use the bot and receive messages.✅')


@app.post(path='/message', dependencies=[Depends(verify_token)])
async def receive_message_handler(message: Message):
    docs = db_without_async.collection(
        CloudCollections.students.value).stream()
    attachments_downloaded = False

    downloaded_attachments: list[DownloadedAttachment] = []

    if message.attachments:
        try:
            for attachment in message.attachments:
                url = attachment.url
                async with aiohttp.ClientSession() as session:
                    async with session.get(url=url) as response:
                        if response.status == 200:
                            file_in_memory = io.BytesIO()
                            async for chunk in response.content.iter_any():
                                file_in_memory.write(chunk)
                            file_in_memory.name = os.path.basename(url)
                            file_in_memory.seek(0)
                            attachments_downloaded = True
                            downloaded_attachments.append(DownloadedAttachment(
                                file=file_in_memory, content_type=attachment.content_type))
        except Exception as e:
            attachments_downloaded = False
            print(f"Exception => {e}")

    for doc in docs:
        try:
            bot.send_message(
                doc.id, text=f"✉️ {message.user.name} <{message.user.email}> \n\n {message.text}")
            if message.attachments and attachments_downloaded:
                for attachment in downloaded_attachments:
                    if attachment.content_type == 'audio':
                        bot.send_audio(doc.id, audio=attachment.file)
                    elif attachment.content_type == 'photo':
                        bot.send_photo(doc.id, photo=attachment.file)
                    elif attachment.content_type == 'voice':
                        bot.send_voice(doc.id, voice=attachment.file)
                    elif attachment.content_type == 'video':
                        bot.send_video(doc.id, video=attachment.file)
                    elif attachment.content_type == 'document':
                        bot.send_document(doc.id, document=attachment.file)
            elif message.attachments and not attachments_downloaded:
                bot.send_message(
                    doc.id, text="An error occurred while trying to download the attachment")
        except Exception as e:
            # this try and except block is to catch any errors that may arise if doc.id is not a good telegram user id
            print(f"Exception => {e}")


bot.remove_webhook()

# Set webhook
bot.set_webhook(
    url=BOT_URL_BASE + BOT_TOKEN
)

# bot.polling()
