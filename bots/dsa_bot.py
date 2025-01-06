from models.enums import CloudCollections
from models.states import UserState
from models.schemas import Message, Attachment, User
from typing import Annotated
import os
from dotenv import load_dotenv
import aiohttp
import telebot
from telebot import async_telebot, asyncio_filters
from telebot.asyncio_storage import StateMemoryStorage
from telebot.types import Message as TelegramMessage, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
# necessary for state parameter in handlers.
from telebot.states.asyncio.middleware import StateMiddleware
from telebot.states.asyncio.context import StateContext
from fastapi import FastAPI, status, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import firebase_admin
from firebase_admin import credentials, firestore_async

import random
import string
from datetime import datetime
# current_dir = os.path.dirname(os.path.abspath(__file__))
# parent_dir = os.path.dirname(current_dir)
# sys.path.append(parent_dir)

load_dotenv()

BOT_URL_BASE = os.getenv("DSA_BOT_URL_BASE")
BOT_TOKEN = os.getenv('DSA_BOT_TOKEN')
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
AUTH_URL_BASE = os.getenv("AUTH_URL_BASE")
SECRET_TOKEN = os.getenv("DSA_BOT_SERVER_SECRET_TOKEN")
STUDENT_BOT_SERVER_SECRET_TOKEN = os.getenv("STUDENT_BOT_SERVER_SECRET_TOKEN")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.remove_webhook()
    # Set webhook
    await bot.set_webhook(
        url=BOT_URL_BASE + BOT_TOKEN
    )
    yield


app = FastAPI(lifespan=lifespan)

state_storage = StateMemoryStorage() # don't use this in production; switch to redis
bot = async_telebot.AsyncTeleBot(BOT_TOKEN, state_storage=state_storage)

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db_async = firestore_async.client()

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


async def is_an_official(user_id) -> User | None:
    official_user_ref = db_async.collection(
        CloudCollections.officials.value).document(str(user_id))
    official_user_data = await official_user_ref.get()
    return User(**official_user_data.to_dict()) if official_user_data.exists else None


@app.get('/auth-complete/{user_id}', dependencies=[Depends(verify_token)])
async def on_auth_completed(user_id: str):
    await bot.send_message(
        user_id, text='Thank you for verifying your Covenant University email! You\'re now authorized to use the bot and receive messages.✅')


@bot.message_handler(commands=["cancel"])
async def cancel_operation(message: TelegramMessage, state: StateContext):
    await state.delete()
    await bot.send_message(chat_id=message.from_user.id, text="operation canceled")


@bot.message_handler(commands=['start'])
async def send_welcome(message):
    official_user = await is_an_official(message.from_user.id)
    if official_user:
        await bot.send_message(chat_id=message.from_user.id,
                               text=f"You're already verified as {official_user.name} - {official_user.email}. Feel free to continue using the bot")
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            "Authorize me", url=f'{AUTH_URL_BASE}authorize/{message.from_user.id}?is_official=true'))
        await bot.send_message(chat_id=message.from_user.id,
                               text="Hello! To access this bot, you need to verify that you're hold an administrative position at Covenant University. Please sign in with your Google account using the button below.", reply_markup=markup)


# so if user is included here, it means that the sender has been authenticated, so no need to check for authentication again
async def send_message_and_restart_message_handler(message: TelegramMessage, state: StateContext, user: User = None):
    official_user = user if user else await is_an_official(
        message.from_user.id)
    if official_user:
        await bot.send_message(chat_id=message.from_user.id,
                               text='Please type in the messages you would like to send to the students.')
        await state.set(UserState.message)
        await state.add_data(user=official_user)
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            "Authorize me", url=f'{AUTH_URL_BASE}authorize/{message.from_user.id}'))
        await bot.send_message(chat_id=message.from_user.id,
                               text="Hello! To access this bot, you need to verify that you're hold an administrative position at Covenant University. Please sign in with your Google account using the button below.", reply_markup=markup)


@bot.message_handler(commands=["send_message"])
async def ask_for_message(message: TelegramMessage, state: StateContext):
    await send_message_and_restart_message_handler(message, state=state)


# handle dean message to student input
@bot.message_handler(state=UserState.message)
async def handle_message(message: TelegramMessage, state: StateContext):
    await state.add_data(message=message.text)
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(
        "Yes ✅", callback_data="attach_file_yes"), InlineKeyboardButton("No 🚫", callback_data="attach_file_no"))
    await bot.send_message(chat_id=message.from_user.id,
                           text="Do you want to attach any file", reply_markup=markup)


@bot.callback_query_handler(state=[UserState.message], func=lambda call: call.data.startswith("attach_file"))
async def callback_query(call: CallbackQuery, state: StateContext):
    user_id = call.from_user.id

    await state.set(UserState.attachments)
    if call.data == "attach_file_yes":
        await bot.send_message(
            chat_id=user_id, text='Please send your attachments now. When you\'re done, type /done to confirm. 🚀')
    else:
        await show_confirmation_message(user_id, state=state)


async def show_confirmation_message(user_id, state: StateContext):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(
        "Yes ✅", callback_data="send_message_yes"), InlineKeyboardButton("No 🚫", callback_data="send_message_no"))
    async with state.data() as data:
        message: str = data.get('message', 'Unknown')
        user: User = data.get("user", User(
            email="unknown@gmail.com", name="Unknown"))
        attachments: list[Attachment] = data.get('attachments', [])

    await bot.send_message(chat_id=user_id,
                           text='Confirm this is the message you want to send')
    await bot.send_message(chat_id=user_id, text="⬇️⬇️⬇️⬇️⬇️⬇️⬇️")
    await bot.send_message(user_id, text=f"✉️ {user.name} <{user.email}> \n\n {message}", reply_markup=markup if len(attachments) == 0 else None)

    for index, attachment in enumerate(attachments):
        is_last_attachment = index == len(attachments) - 1

        if attachment.content_type == 'audio':
            await bot.send_audio(user_id, audio=attachment.file_id,
                                 reply_markup=markup if is_last_attachment else None)
        elif attachment.content_type == 'photo':
            await bot.send_photo(user_id, photo=attachment.file_id,
                                 reply_markup=markup if is_last_attachment else None)
        elif attachment.content_type == 'voice':
            await bot.send_voice(user_id, voice=attachment.file_id,
                                 reply_markup=markup if is_last_attachment else None)
        elif attachment.content_type == 'video':
            await bot.send_video(user_id, video=attachment.file_id,
                                 reply_markup=markup if is_last_attachment else None)
        elif attachment.content_type == 'document':
            await bot.send_document(
                user_id, document=attachment.file_id, reply_markup=markup if is_last_attachment else None)


@bot.message_handler(commands=['done'], state=UserState.attachments)
async def handle_attachment_complete(message: TelegramMessage, state: StateContext):
    await show_confirmation_message(user_id=message.from_user.id, state=state)


def generate_random_filename():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    return f"{timestamp}_{random_string}"

# 'text', 'location', 'contact', 'sticker'
@bot.message_handler(content_types=['audio', 'photo', 'voice', 'video', 'document'], state=UserState.attachments)
async def handle_attachments(message: TelegramMessage, state: StateContext):
    if message.content_type == 'audio':
        file_id = message.audio.file_id
        file_name = message.audio.file_name
    elif message.content_type == 'photo':
        # Get the highest resolution photo according to chatgpt
        file_id = message.photo[-1].file_id
        file_name = generate_random_filename()
    elif message.content_type == 'voice':
        file_id = message.voice.file_id
        file_name = generate_random_filename() 
    elif message.content_type == 'video':
        file_id = message.video.file_id
        file_name = message.video.file_name
    elif message.content_type == 'document':
        file_id = message.document.file_id
        file_name = message.document.file_name
    file_url = await bot.get_file_url(file_id=file_id)
    async with state.data() as data:
        attachments: list = data.get('attachments', [])

    attachments.append(Attachment(
        url=file_url, content_type=message.content_type, file_id=file_id, file_name=file_name))
    await state.add_data(attachments=attachments)


@bot.callback_query_handler(state=[UserState.attachments], func=lambda call: call.data.startswith("send_message"))
async def callback_query(call: CallbackQuery, state: StateContext):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == "send_message_yes":
        async with state.data() as data:
            official_user = data.get("user", User(
                email="unknown@gmail.com", name="Unknown"))
            message = data.get('message', 'Unknown')
            attachments = data.get('attachments', None)
        await bot.send_message(chat_id=chat_id,
                               text='Message is sending.....',)
        await send_message_to_students(
            Message(text=message, attachments=attachments, user=official_user), user_id)
        await state.delete()
        async with state.data() as data:
            message = data.get('message', 'Unknown')
            attachments = data.get('attachments', None)
    else:
        await bot.send_message(
            user_id, "Ok.... click on /restart to restart or /cancel to cancel")
        await state.set(UserState.cancel_or_restart)


@bot.message_handler(commands=["restart"], state=[UserState.cancel_or_restart])
async def restart_handler(message: TelegramMessage, state: StateContext):
    async with state.data() as data:
        official_user = data.get("user", User(
                email="unknown@gmail.com", name="Unknown"))
    await send_message_and_restart_message_handler(message, state=state, user=official_user)


async def send_message_to_students(message: Message, user_id):
    url = "https://cugram.onrender.com/message"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {STUDENT_BOT_SERVER_SECRET_TOKEN}"
    }

    payload = message.model_dump()
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(url=url, json=payload) as response:
            print(f"status code is {response.status}")
            if response.status == 200:
                await bot.send_message(chat_id=user_id,
                                       text='Message sent successfully')
            else:
                await bot.send_message(chat_id=user_id,
                                       text='Message was unable to be sent')


bot.add_custom_filter(asyncio_filters.StateFilter(bot))

bot.setup_middleware(StateMiddleware(bot))

# uncomment this for polling

# import asyncio
# async def main():
    # await bot.remove_webhook()
    # await bot.polling()

# asyncio.run(main())