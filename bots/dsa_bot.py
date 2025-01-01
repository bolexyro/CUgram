import os
from dotenv import load_dotenv
import telebot
from telebot import custom_filters
from telebot.types import Message as TelegramMessage, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telebot.storage import StateMemoryStorage
from fastapi import FastAPI
import requests
import firebase_admin
from firebase_admin import credentials, firestore_async, firestore

import sys
# Get the current script's directory
current_dir = os.path.dirname(os.path.abspath(__file__))

# Get the parent directory
parent_dir = os.path.dirname(current_dir)

# Append the parent directory to sys.path
sys.path.append(parent_dir)

from models.enums import AuthStatus
from models.states import UserState
from models.schemas import Message, Attachment

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


@bot.message_handler(commands=["cancel"])
def cancel_operation(message: TelegramMessage):
    bot.delete_state(message.from_user.id, message.chat.id)
    bot.send_message(chat_id=message.from_user.id, text="operation canceled")


def send_message_and_restart_message_handler(message: TelegramMessage, is_authenticated=False):
    auth_status = AuthStatus.is_dean if is_authenticated else check_if_is_dean(
        message.from_user.id)
    if auth_status == AuthStatus.is_dean:
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


@bot.message_handler(commands=["send_message"])
def ask_for_message(message: TelegramMessage):
    send_message_and_restart_message_handler(message)


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
        bot.send_message(
            chat_id=user_id, text='Please send your attachments now. When you\'re done, type /done to confirm. 🚀')
    else:
        show_confirmation_message(user_id)


def show_confirmation_message(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(
        "Yes ✅", callback_data="send_message_yes"), InlineKeyboardButton("No 🚫", callback_data="send_message_no"))
    bot.send_message(chat_id=user_id,
                     text='Confirm this is the message you want to send')
    bot.send_message(chat_id=user_id, text="⬇️⬇️⬇️⬇️⬇️⬇️⬇️")
    with bot.retrieve_data(user_id) as data:
        message: str = data.get('message', 'Unknown')
        attachments: list[Attachment] = data.get('attachments', [])

    bot.send_message(chat_id=user_id,
                     text=message, reply_markup=markup if len(attachments) == 0 else None)

    for index, attachment in enumerate(attachments):
        is_last_attachment = index == len(attachments) - 1

        if attachment.content_type == 'audio':
            bot.send_audio(user_id, audio=attachment.file_id,
                           reply_markup=markup if is_last_attachment else None)
        elif attachment.content_type == 'photo':
            bot.send_photo(user_id, photo=attachment.file_id,
                           reply_markup=markup if is_last_attachment else None)
        elif attachment.content_type == 'voice':
            bot.send_voice(user_id, voice=attachment.file_id,
                           reply_markup=markup if is_last_attachment else None)
        elif attachment.content_type == 'video':
            bot.send_video(user_id, video=attachment.file_id,
                           reply_markup=markup if is_last_attachment else None)
        elif attachment.content_type == 'document':
            bot.send_document(
                user_id, document=attachment.file_id, reply_markup=markup if is_last_attachment else None)


@bot.message_handler(commands=['done'], state=UserState.attachments)
def handle_attachment_complete(message: TelegramMessage):
    show_confirmation_message(user_id=message.from_user.id)


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
    user_id = message.from_user.id
    with bot.retrieve_data(user_id) as data:
        attachments: list = data.get('attachments', [])

    attachments.append(Attachment(
        url=file_url, content_type=message.content_type, file_id=file_id))
    bot.add_data(message.from_user.id, attachments=attachments)


@bot.callback_query_handler(state=[UserState.attachments], func=lambda call: call.data.startswith("send_message"))
def callback_query(call: CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if call.data == "send_message_yes":
        with bot.retrieve_data(user_id) as data:
            message = data.get('message', 'Unknown')
            attachments = data.get('attachments', None)
        bot.send_message(chat_id=chat_id,
                         text='Message is sending.....',)
        send_message_to_students(
            Message(text=message, attachments=attachments), user_id)
        bot.delete_state(user_id, chat_id)
        with bot.retrieve_data(user_id) as data:
            message = data.get('message', 'Unknown')
            attachments = data.get('attachments', None)
    else:
        bot.send_message(
            user_id, "Ok.... click on /restart to restart or /cancel to cancel")
        bot.set_state(user_id, UserState.cancel_or_restart)


@bot.message_handler(commands=["restart"], state=[UserState.cancel_or_restart])
def restart_handler(message: TelegramMessage):
    send_message_and_restart_message_handler(message, is_authenticated=True)


def send_message_to_students(message: Message, user_id):
    url = "https://cugram.onrender.com/message"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    data = message.model_dump(exclude="file_id")
    print(data)
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
