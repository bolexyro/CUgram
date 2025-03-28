from models.enums import CloudCollections
from models.states import UserState
from models.schemas import Message, Attachment, User
import telebot
from telebot import async_telebot, asyncio_filters
from telebot.asyncio_storage import StateMemoryStorage
from telebot.types import (
    Message as TelegramMessage,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)

# necessary for state parameter in handlers.
from telebot.states.asyncio.middleware import StateMiddleware
from telebot.states.asyncio.context import StateContext
from fastapi import FastAPI
from contextlib import asynccontextmanager
import firebase_admin
from firebase_admin import credentials, firestore_async

from config import settings
import random
import string
from datetime import datetime
import time
import pytz

# current_dir = os.path.dirname(os.path.abspath(__file__))
# parent_dir = os.path.dirname(current_dir)
# sys.path.append(parent_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await dsa_bot.remove_webhook()
    # Set webhook
    await dsa_bot.set_webhook(url=settings.dsa_bot_url_base + settings.dsa_bot_token)
    yield


app = FastAPI(lifespan=lifespan)

# TODO don't use this in production; switch to redis
state_storage = StateMemoryStorage()
dsa_bot = async_telebot.AsyncTeleBot(
    settings.dsa_bot_token, state_storage=state_storage
)
student_bot = async_telebot.AsyncTeleBot(settings.student_bot_token)

firebase_cred = credentials.Certificate(settings.service_account_key_path)
firebase_admin.initialize_app(firebase_cred)
db = firestore_async.client()


@app.post(path=f"/{settings.dsa_bot_token}")
async def process_webhook_text_pay_bot(update: dict):
    """
    Process webhook calls for cugram
    """
    if update:
        update = telebot.types.Update.de_json(update)
        await dsa_bot.process_new_updates([update])
    else:
        return


async def is_an_official(user_id) -> User | None:
    official_user_ref = db.collection(CloudCollections.officials.value).document(
        str(user_id)
    )
    official_user_data = await official_user_ref.get()
    return User(**official_user_data.to_dict()) if official_user_data.exists else None


@dsa_bot.message_handler(commands=["cancel"])
async def cancel_operation(message: TelegramMessage, state: StateContext):
    await state.delete()
    await dsa_bot.send_message(chat_id=message.from_user.id, text="operation canceled")


@dsa_bot.message_handler(commands=["start"])
async def send_welcome(message):
    official_user = await is_an_official(message.from_user.id)
    if official_user:
        await dsa_bot.send_message(
            chat_id=message.from_user.id,
            text=f"You're already verified as {official_user.name} - {official_user.email}. Feel free to continue using the bot",
        )
    else:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "Authorize me",
                url=f"{settings.auth_url_base}authorize/{message.from_user.id}?is_official=true",
            )
        )
        await dsa_bot.send_message(
            chat_id=message.from_user.id,
            text="Hello! To access this bot, you need to verify that you're hold an administrative position at Covenant University. Please sign in with your Google account using the button below.",
            reply_markup=markup,
        )


# so if user is included here, it means that the sender has been authenticated, so no need to check for authentication again
async def send_message_and_restart_message_handler(
    message: TelegramMessage, state: StateContext, user: User = None
):
    official_user = user if user else await is_an_official(message.from_user.id)
    if official_user:
        await dsa_bot.send_message(
            chat_id=message.from_user.id,
            text="Please type in the messages you would like to send to the students.",
        )
        await state.set(UserState.message)
        await state.add_data(user=official_user)
    else:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "Authorize me",
                url=f"{settings.auth_url_base}authorize/{message.from_user.id}",
            )
        )
        await dsa_bot.send_message(
            chat_id=message.from_user.id,
            text="Hello! To access this bot, you need to verify that you're hold an administrative position at Covenant University. Please sign in with your Google account using the button below.",
            reply_markup=markup,
        )


@dsa_bot.message_handler(commands=["send_message"])
async def ask_for_message(message: TelegramMessage, state: StateContext):
    await send_message_and_restart_message_handler(message, state=state)


# handle dean message to student input
@dsa_bot.message_handler(state=UserState.message)
async def handle_message(message: TelegramMessage, state: StateContext):
    await state.add_data(message=message.text)
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Yes ✅", callback_data="attach_file_yes"),
        InlineKeyboardButton("No 🚫", callback_data="attach_file_no"),
    )
    await dsa_bot.send_message(
        chat_id=message.from_user.id,
        text="Do you want to attach any file",
        reply_markup=markup,
    )


@dsa_bot.callback_query_handler(
    state=[UserState.message], func=lambda call: call.data.startswith("attach_file")
)
async def callback_query(call: CallbackQuery, state: StateContext):
    user_id = call.from_user.id

    await state.set(UserState.attachments)
    if call.data == "attach_file_yes":
        await dsa_bot.send_message(
            chat_id=user_id,
            text="Please send your attachments now. When you're done, type /done to confirm. 🚀",
        )
    else:
        await show_confirmation_message(user_id, state=state)


async def show_confirmation_message(user_id, state: StateContext):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Yes ✅", callback_data="send_message_yes"),
        InlineKeyboardButton("No 🚫", callback_data="send_message_no"),
    )
    async with state.data() as data:
        message: str = data.get("message", "Unknown")
        user: User = data.get("user", User(email="unknown@gmail.com", name="Unknown"))
        attachments: list[Attachment] = data.get("attachments", [])

    await dsa_bot.send_message(
        chat_id=user_id, text="Confirm this is the message you want to send"
    )
    await dsa_bot.send_message(chat_id=user_id, text="⬇️⬇️⬇️⬇️⬇️⬇️⬇️")
    await dsa_bot.send_message(
        user_id,
        text=f"✉️ {user.name} <{user.email}> \n\n {message}",
        reply_markup=markup if len(attachments) == 0 else None,
    )

    for index, attachment in enumerate(attachments):
        is_last_attachment = index == len(attachments) - 1

        if attachment.content_type == "audio":
            await dsa_bot.send_audio(
                user_id,
                audio=attachment.file_id,
                reply_markup=markup if is_last_attachment else None,
            )
        elif attachment.content_type == "photo":
            await dsa_bot.send_photo(
                user_id,
                photo=attachment.file_id,
                reply_markup=markup if is_last_attachment else None,
            )
        elif attachment.content_type == "voice":
            await dsa_bot.send_voice(
                user_id,
                voice=attachment.file_id,
                reply_markup=markup if is_last_attachment else None,
            )
        elif attachment.content_type == "video":
            await dsa_bot.send_video(
                user_id,
                video=attachment.file_id,
                reply_markup=markup if is_last_attachment else None,
            )
        elif attachment.content_type == "document":
            await dsa_bot.send_document(
                user_id,
                document=attachment.file_id,
                reply_markup=markup if is_last_attachment else None,
            )


@dsa_bot.message_handler(commands=["done"], state=UserState.attachments)
async def handle_attachment_complete(message: TelegramMessage, state: StateContext):
    await show_confirmation_message(user_id=message.from_user.id, state=state)


def generate_random_filename():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_string = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    return f"{timestamp}_{random_string}"


# 'text', 'location', 'contact', 'sticker'


@dsa_bot.message_handler(
    content_types=["audio", "photo", "voice", "video", "document"],
    state=UserState.attachments,
)
async def handle_attachments(message: TelegramMessage, state: StateContext):
    if message.content_type == "audio":
        file_id = message.audio.file_id
        file_name = message.audio.file_name
    elif message.content_type == "photo":
        # Get the highest resolution photo according to chatgpt
        file_id = message.photo[-1].file_id
        file_name = generate_random_filename()
    elif message.content_type == "voice":
        file_id = message.voice.file_id
        file_name = generate_random_filename()
    elif message.content_type == "video":
        file_id = message.video.file_id
        file_name = message.video.file_name
    elif message.content_type == "document":
        file_id = message.document.file_id
        file_name = message.document.file_name
    file_url = await dsa_bot.get_file_url(file_id=file_id)
    async with state.data() as data:
        attachments: list = data.get("attachments", [])

    attachments.append(
        Attachment(
            url=file_url,
            content_type=message.content_type,
            file_id=file_id,
            file_name=file_name,
        )
    )
    await state.add_data(attachments=attachments)


@dsa_bot.callback_query_handler(
    state=[UserState.attachments],
    func=lambda call: call.data.startswith("send_message"),
)
async def callback_query(call: CallbackQuery, state: StateContext):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == "send_message_yes":
        async with state.data() as data:
            official_user = data.get(
                "user", User(email="unknown@gmail.com", name="Unknown")
            )
            message = data.get("message", "Unknown")
            attachments = data.get("attachments", None)
        await dsa_bot.send_message(
            chat_id=chat_id,
            text="Message is sending.....",
        )
        await send_message_to_students(
            Message(text=message, attachments=attachments, user=official_user), user_id
        )
        await state.delete()
        async with state.data() as data:
            message = data.get("message", "Unknown")
            attachments = data.get("attachments", None)
    else:
        await dsa_bot.send_message(
            user_id, "Ok.... click on /restart to restart or /cancel to cancel"
        )
        await state.set(UserState.cancel_or_restart)


@dsa_bot.message_handler(commands=["restart"], state=[UserState.cancel_or_restart])
async def restart_handler(message: TelegramMessage, state: StateContext):
    async with state.data() as data:
        official_user = data.get(
            "user", User(email="unknown@gmail.com", name="Unknown")
        )
    await send_message_and_restart_message_handler(
        message, state=state, user=official_user
    )


def generate_unique_id():
    timestamp = int(time.time())
    random_string = "".join(random.choices(string.ascii_letters + string.digits, k=4))
    unique_id = f"{timestamp}{random_string}"
    return unique_id


async def send_message_to_students(message: Message, user_id):
    new_message_id = generate_unique_id()
    new_message_ref = db.collection(CloudCollections.messages.value).document(
        new_message_id
    )

    local_tz = pytz.timezone("Africa/Lagos")
    local_time = datetime.now(local_tz)
    local_time_str = local_time.isoformat()

    await new_message_ref.set({**message.model_dump(), "timestamp": local_time_str})

    docs = db.collection(CloudCollections.students.value).stream()
    async for doc in docs:
        try:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    "🔍 Open Viewer",
                    web_app=WebAppInfo(url="https://bolexyro.vercel.app/"),
                )
            )
            if message.attachments:
                for index, attachment in enumerate(message.attachments):
                    if attachment.content_type == "audio":
                        markup.add(
                            InlineKeyboardButton(
                                f"🎧 {attachment.file_name}",
                                callback_data=f"download:{new_message_id}:{index}",
                            )
                        )
                    elif attachment.content_type == "photo":
                        markup.add(
                            InlineKeyboardButton(
                                f"🖼️ {attachment.file_name}",
                                callback_data=f"download:{new_message_id}:{index}",
                            )
                        )
                    elif attachment.content_type == "voice":
                        markup.add(
                            InlineKeyboardButton(
                                f"🎙️ {attachment.file_name}",
                                callback_data=f"download:{new_message_id}:{index}",
                            )
                        )
                    elif attachment.content_type == "video":
                        markup.add(
                            InlineKeyboardButton(
                                f"🎥 {attachment.file_name}",
                                callback_data=f"download:{new_message_id}:{index}",
                            )
                        )
                    elif attachment.content_type == "document":
                        markup.add(
                            InlineKeyboardButton(
                                f"📄 {attachment.file_name}",
                                callback_data=f"download:{new_message_id}:{index}",
                            )
                        )
            await student_bot.send_message(
                doc.id,
                text=f"✉️ {message.user.name} <{message.user.email}> \n\n {message.text}",
                reply_markup=markup,
            )
        except Exception as e:
            # this try and except block is to catch any errors that may arise if doc.id is not a good telegram user id
            print(f"Exception => {e}")
    await dsa_bot.send_message(chat_id=user_id, text="Message sent successfully")


dsa_bot.add_custom_filter(asyncio_filters.StateFilter(dsa_bot))

dsa_bot.setup_middleware(StateMiddleware(dsa_bot))

# uncomment this for polling

# import asyncio

# async def main():
#     print("Bot Started .....")
#     await dsa_bot.remove_webhook()
#     await dsa_bot.polling()


# asyncio.run(main())
