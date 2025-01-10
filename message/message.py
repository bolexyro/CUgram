from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from contextlib import asynccontextmanager
from models.schemas import Message
from models.enums import CloudCollections
from auth.utils import decode_jwt
from telebot import async_telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import firebase_admin
from firebase_admin import credentials, firestore_async
from typing import Annotated
import os
import time
import random
import string
import pytz
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


SECRET_TOKEN = os.getenv("STUDENT_BOT_SERVER_SECRET_TOKEN")
BOT_TOKEN = os.getenv('STUDENT_BOT_TOKEN')

BOT_URL_BASE = os.getenv("STUDENT_BOT_URL_BASE")
AUTH_URL_BASE = os.getenv("AUTH_URL_BASE")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
BOT_TOKEN = os.getenv('STUDENT_BOT_TOKEN')
SECRET_TOKEN = os.getenv("STUDENT_BOT_SERVER_SECRET_TOKEN")
JWT_SIGNING_SECRET_KEY = os.getenv("JWT_SIGNING_SECRET_KEY")

security = HTTPBearer()


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


def verify_token(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    if credentials.credentials != SECRET_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing token",
        )


def generate_unique_id():
    timestamp = int(time.time())
    random_string = ''.join(random.choices(
        string.ascii_letters + string.digits, k=4))
    unique_id = f"{timestamp}{random_string}"
    return unique_id


@app.post(path='/message/simple', dependencies=[Depends(verify_token)])
async def receive_message_handler(message: Message):
    new_message_id = generate_unique_id()
    new_message_ref = db.collection(
        CloudCollections.messages.value).document(new_message_id)

    local_tz = pytz.timezone('Africa/Lagos')
    local_time = datetime.now(local_tz)
    local_time_str = local_time.isoformat()

    await new_message_ref.set(
        {
            **message.model_dump(),
            "timestamp": local_time_str
        }
    )

    docs = db.collection(
        CloudCollections.students.value).stream()

    async for doc in docs:
        try:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(
                "🔍 Open Viewer", web_app=WebAppInfo(url="https://bolexyro.vercel.app/")))
            if message.attachments:
                for index, attachment in enumerate(message.attachments):
                    if attachment.content_type == 'audio':
                        markup.add(InlineKeyboardButton(
                            f"🎧 {attachment.file_name}", callback_data=f"download:{new_message_id}:{index}"))
                    elif attachment.content_type == 'photo':
                        markup.add(InlineKeyboardButton(
                            f"🖼️ {attachment.file_name}", callback_data=f"download:{new_message_id}:{index}"))
                    elif attachment.content_type == 'voice':
                        markup.add(InlineKeyboardButton(
                            f"🎙️ {attachment.file_name}", callback_data=f"download:{new_message_id}:{index}"))
                    elif attachment.content_type == 'video':
                        markup.add(InlineKeyboardButton(
                            f"🎥 {attachment.file_name}", callback_data=f"download:{new_message_id}:{index}"))
                    elif attachment.content_type == 'document':
                        markup.add(InlineKeyboardButton(
                            f"📄 {attachment.file_name}", callback_data=f"download:{new_message_id}:{index}"))
            await bot.send_message(
                doc.id, text=f"✉️ {message.user.name} <{message.user.email}> \n\n {message.text}", reply_markup=markup)
        except Exception as e:
            # this try and except block is to catch any errors that may arise if doc.id is not a good telegram user id
            print(f"Exception => {e}")


def verify_access_token(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    try:
        decode_jwt(token=credentials.credentials,
                   secret=JWT_SIGNING_SECRET_KEY)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.post("/message/rich", dependencies=[Depends(verify_access_token)])
async def create_rich_message():
    """
    Endpoint to create a rich message from a text editor.
    """
    print("rich message endpoint reached how can I help you")
