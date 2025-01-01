import os
from dotenv import load_dotenv
import telebot
from telebot import custom_filters
from telebot.types import Message as TelegramMessage, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup  # states
from fastapi import FastAPI
import requests
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore_async, firestore
from enum import Enum

load_dotenv()

BOT_URL_BASE = os.getenv("DSA_BOT_URL_BASE")
BOT_TOKEN = os.getenv('DSA_BOT_TOKEN')
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
USERS_COLLECTION = "users"
AUTH_URL_BASE = os.getenv("AUTH_URL_BASE")
DSA_EMAIL = os.getenv("DSA_EMAIL")

app = FastAPI()
bot = telebot.TeleBot(BOT_TOKEN)

state_storage = StateMemoryStorage()  # you can init here another storage

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db_async = firestore_async.client()
db_without_async = firestore.client()


class Message(BaseModel):
    text: str
    attachment_url: str | None = None
    content_type: str | None = None


class UserState(StatesGroup):
    message = State()
    attachments = State()


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


class AuthStatus(Enum):
    is_dean = 1
    is_not_dean = 2
    does_not_exist = 3


def check_if_is_dean(user_id) -> AuthStatus:
    user_ref = db_without_async.collection(
        USERS_COLLECTION).document(str(user_id))
    user = user_ref.get()
    if user.exists:
        user = user.to_dict()
        if (user.get("is_dean", False)):
            return AuthStatus.is_dean
        else:
            return AuthStatus.is_not_dean
    else:
        return AuthStatus.does_not_exist


@bot.message_handler(commands=['start'])
def send_welcome(message):
    auth_status = check_if_is_dean(message.from_user.id)
    if (auth_status == AuthStatus.is_dean):
        bot.send_message(chat_id=message.from_user.id,
                         text=f"You're already verified as the dean of student affairs CU {DSA_EMAIL}. Feel free to continue using the bot Mrs Shola Coker.")
    elif auth_status == AuthStatus.is_not_dean:
        bot.send_message(chat_id=message.from_user.id,
                         text=f"We both know you ain't the dean of student affairs CU. You should not be using this bot smh.")
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            "Authorize me", url=f'{AUTH_URL_BASE}authorize/{message.from_user.id}'))
        bot.send_message(chat_id=message.from_user.id,
                         text="Hello! To access this bot, you need to verify that you're the dean of student affairs Covenant University. Please sign in with your Google account using the button below.", reply_markup=markup)


@bot.message_handler(commands=["send_message"])
def ask_for_message(message: TelegramMessage):
    auth_status = check_if_is_dean(message.from_user.id)
    if (auth_status == AuthStatus.is_dean):
        bot.send_message(chat_id=message.from_user.id,
                         text='Please type in the messages you would like to send to the students.')
        bot.set_state(message.from_user.id, UserState.message)
    elif auth_status == AuthStatus.is_not_dean:
        bot.send_message(chat_id=message.from_user.id,
                         text=f"We both know you ain't the dean of student affairs CU. You should not be using this bot smh.")
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            "Authorize me", url=f'{AUTH_URL_BASE}authorize/{message.from_user.id}'))
        bot.send_message(chat_id=message.from_user.id,
                         text="Hello! To access this bot, you need to verify that you're the dean of student affairs Covenant University. Please sign in with your Google account using the button below.", reply_markup=markup)


# handle dean message to student input
@bot.message_handler(state=UserState.message)
def handle_message(message: TelegramMessage):
    bot.add_data(message.from_user.id, message=message.text)
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(
        "Yes ✅", callback_data="attach_file_yes"), InlineKeyboardButton("No 🚫", callback_data="attach_file_no"))
    bot.send_message(chat_id=message.from_user.id,
                     text="Do you want to attach any file", reply_markup=markup)


@bot.callback_query_handler(state=[UserState.message], func=lambda call: call.data.startswith("attach_file"))
def callback_query(call: CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    bot.set_state(user_id, UserState.attachments)
    if call.data == "attach_file_yes":
        bot.send_message(chat_id=user_id,
                         text='Ok send me the files')
    else:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton(
            "Yes ✅", callback_data="send_message_yes"), InlineKeyboardButton("No 🚫", callback_data="send_message_no"))
        bot.send_message(chat_id=user_id,
                         text='Confirm this is the message you want to send', reply_markup=markup)


# 'text', 'location', 'contact', 'sticker'
@bot.message_handler(content_types=['audio', 'photo', 'voice', 'video', 'document'], state=UserState.attachments)
def handle_attachments(message: TelegramMessage):
    if message.content_type == 'audio':
        file_id = message.audio.file_id
    elif message.content_type == 'photo':
        # Get the highest resolution photo according to chatgpt
        file_id = message.photo[-1].file_id
    elif message.content_type == 'voice':
        file_id = message.voice.file_id
    elif message.content_type == 'video':
        file_id = message.video.file_id
    elif message.content_type == 'document':
        file_id = message.document.file_id

    file_url = bot.get_file_url(file_id=file_id)
    print(file_url)
    bot.add_data(message.from_user.id, attachment=file_url, content_type=message.content_type)
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(
        "Yes ✅", callback_data="send_message_yes"), InlineKeyboardButton("No 🚫", callback_data="send_message_no"))
    bot.send_message(chat_id=message.from_user.id,
                     text='Confirm this is the message you want to send', reply_markup=markup)


@bot.callback_query_handler(state=[UserState.attachments], func=lambda call: call.data.startswith("send_message"))
def callback_query(call: CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == "send_message_yes":
        with bot.retrieve_data(user_id) as data:
            message = data.get('message', 'Unknown')
            attachment = data.get('attachment', None)
            content_type = data.get('content_type', None)
        bot.send_message(chat_id=chat_id,
                         text='Message is sending.....',)
        send_message_to_students(
            Message(text=message, attachment_url=attachment, content_type=content_type), user_id)
        bot.delete_state(user_id, chat_id)
    else:
        bot.reply_to(
            call.message, "Ok....")
        bot.delete_state(user_id, chat_id)


def send_message_to_students(message: Message, user_id):
    url = "https://cugram.onrender.com/message"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    data = message.model_dump()
    response = requests.post(url, headers=headers, json=data)
    if (response.status_code == 200):
        bot.send_message(chat_id=user_id,
                         text='Message sent successfully')
    else:
        bot.send_message(chat_id=user_id,
                         text='Message was unable to be sent')


bot.add_custom_filter(custom_filter=custom_filters.StateFilter(bot))

bot.remove_webhook()

# Set webhook
bot.set_webhook(
    url=BOT_URL_BASE + BOT_TOKEN
)
# bot.polling()
