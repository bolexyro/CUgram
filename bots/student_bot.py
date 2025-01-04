from models.schemas import Message, DownloadedAttachment
from models.enums import CloudCollections
from typing import Annotated
import os
from dotenv import load_dotenv
import aiohttp
import io
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot import async_telebot
from fastapi import FastAPI, status, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from contextlib import asynccontextmanager
import firebase_admin
from firebase_admin import credentials, firestore_async

load_dotenv()

BOT_URL_BASE = os.getenv("STUDENT_BOT_URL_BASE")
AUTH_URL_BASE = os.getenv("AUTH_URL_BASE")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
BOT_TOKEN = os.getenv('STUDENT_BOT_TOKEN')
SECRET_TOKEN = os.getenv("STUDENT_BOT_SERVER_SECRET_TOKEN")


@asynccontextmanager
async def lifespan(app=FastAPI):
    await bot.remove_webhook()
    # Set webhook
    await bot.set_webhook(
        url=BOT_URL_BASE + BOT_TOKEN
    )
    yield

app = FastAPI(lifespan=lifespan)
bot = async_telebot.AsyncTeleBot(BOT_TOKEN)

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db = firestore_async.client()

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
async def process_webhook_text_pay_bot(update: dict):
    """
    Process webhook calls for cugram
    """
    if update:
        update = telebot.types.Update.de_json(update)
        await bot.process_new_updates([update])
    else:
        return


@bot.message_handler(commands=['start'])
async def send_welcome(message):
    student_ref = db.collection(
        CloudCollections.students.value).document(str(message.from_user.id))
    student = await student_ref.get()
    if student.exists:
        student = student.to_dict()
        await bot.send_message(chat_id=message.from_user.id,
                               text=f"You're already verified with your Covenant University email  {student['email']}. Feel free to continue using the bot.")
        return
    await bot.send_message(chat_id=message.from_user.id,
                           text="Hello! To access this bot, you need to verify that you have a valid Covenant University email. Please sign in with your Google account using the button below.", reply_markup=gen_markup(message.from_user.id))


@app.get('/auth-complete/{user_id}', dependencies=[Depends(verify_token)])
async def on_auth_completed(user_id: str):
    await bot.send_message(
        user_id, text='Thank you for verifying your Covenant University email! You\'re now authorized to use the bot and receive messages. ✅')


@app.post(path='/message', dependencies=[Depends(verify_token)])
async def receive_message_handler(message: Message):
    docs = db.collection(
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

    async for doc in docs:
        try:
            await bot.send_message(
                doc.id, text=f"✉️ {message.user.name} <{message.user.email}> \n\n {message.text}")
            if message.attachments and attachments_downloaded:
                for attachment in downloaded_attachments:
                    if attachment.content_type == 'audio':
                        await bot.send_audio(doc.id, audio=attachment.file)
                    elif attachment.content_type == 'photo':
                        await bot.send_photo(doc.id, photo=attachment.file)
                    elif attachment.content_type == 'voice':
                        await bot.send_voice(doc.id, voice=attachment.file)
                    elif attachment.content_type == 'video':
                        await bot.send_video(doc.id, video=attachment.file)
                    elif attachment.content_type == 'document':
                        await bot.send_document(doc.id, document=attachment.file)
            elif message.attachments and not attachments_downloaded:
                await bot.send_message(
                    doc.id, text="An error occurred while trying to download the attachment")
        except Exception as e:
            # this try and except block is to catch any errors that may arise if doc.id is not a good telegram user id
            print(f"Exception => {e}")


# uncomment this for polling

# import asyncio
# async def main():
    # await bot.remove_webhook()
    # await bot.polling()

# asyncio.run(main())
