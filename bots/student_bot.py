from models.schemas import DownloadedAttachment, Message, Attachment
from models.enums import CloudCollections
from typing import Annotated
import os
from dotenv import load_dotenv
import aiohttp
import io
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyParameters
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
async def lifespan(app: FastAPI):
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
    user_id = message.from_user.id
    student_ref = db.collection(
        CloudCollections.students.value).document(str(user_id))
    student = await student_ref.get()
    if student.exists:
        student = student.to_dict()
        await bot.send_message(chat_id=message.from_user.id,
                               text=f"You're already verified with your Covenant University email {student['email']}. Feel free to continue using the bot.")
        return
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton(
        "Authorize me", url=f'{AUTH_URL_BASE}authorize/{user_id}'))
    await bot.send_message(chat_id=message.from_user.id,
                           text="Hello! To access this bot, you need to verify that you have a valid Covenant University email. Please sign in with your Google account using the button below.", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("download"))
async def callback_query(call: CallbackQuery):
    user_id = call.from_user.id
    message_id, attachment_index = call.data.split(":")[1:]
    message_ref = db.collection(
        CloudCollections.messages.value).document(message_id)
    message_data = (await message_ref.get()).to_dict()
    attachment = message_data["attachments"][int(attachment_index)]
    attachment = Attachment(**attachment)
    sender_email = message_data["user"]["email"]

    url = attachment.url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url=url) as response:
                if response.status == 200:
                    file_in_memory = io.BytesIO()
                    async for chunk in response.content.iter_any():
                        file_in_memory.write(chunk)
                    file_in_memory.name = os.path.basename(url)
                    file_in_memory.seek(0)
                    downloaded_attachment = DownloadedAttachment(
                        file=file_in_memory, content_type=attachment.content_type)

        message_caption = f"Attachment {attachment.file_name} by \n{sender_email}"

        reply_parameters = ReplyParameters(call.message.message_id)

        if attachment.content_type == 'audio':
            await bot.send_audio(user_id, audio=downloaded_attachment.file, reply_parameters=reply_parameters, caption=message_caption)
        elif attachment.content_type == 'photo':
            await bot.send_photo(user_id, photo=downloaded_attachment.file, reply_parameters=reply_parameters, caption=message_caption)
        elif attachment.content_type == 'voice':
            await bot.send_voice(user_id, voice=downloaded_attachment.file, reply_parameters=reply_parameters)
        elif attachment.content_type == 'video':
            await bot.send_video(user_id, video=downloaded_attachment.file, reply_parameters=reply_parameters, caption=message_caption)
        elif attachment.content_type == 'document':
            await bot.send_document(user_id, document=downloaded_attachment.file, reply_parameters=reply_parameters, caption=message_caption)

    except Exception as e:
        print(f"Exception => {e}")
        await bot.send_message(
            user_id, text="An error occurred while trying to download the attachment")


# uncomment this for polling

# import asyncio
# async def main():
#     await bot.remove_webhook()
#     await bot.polling()

# asyncio.run(main())
