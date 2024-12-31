import base64
from io import BytesIO
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyParameters
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthTransportRequest
import firebase_admin
from firebase_admin import credentials, firestore_async, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
import json
from pydantic import BaseModel
from utils.gmail_api_utils import extract_body_and_attachments, get_email_details, mark_unmark_message_as_read


class Message(BaseModel):
    text: str


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
        except:
            pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("cb"))
def callback_query(call: CallbackQuery):
    action = call.data.split('*')[1]
    users_ref = db_without_async.collection(USERS_COLLECTION)
    query_ref = users_ref.where(filter=FieldFilter(
        "user_id", "==", f"{call.from_user.id}"))
    docs = query_ref.get()
    if len(docs) == 0:
        return
    doc = docs[0].to_dict()
    doc_credential = doc['credential']
    creds = Credentials(
        token=doc_credential['token'],
        refresh_token=doc_credential['refresh_token'],
        token_uri=doc_credential['token_uri'],
        client_id=doc_credential['client_id'],
        client_secret=doc_credential['client_secret'],
        granted_scopes=doc_credential['granted_scopes'],
    )
    service = build("gmail", "v1", credentials=creds)
    if action == "get_attachment":
        mime_type, email_message_id, index = call.data.split(
            '*')[2], call.data.split('*')[3], call.data.split('*')[4]
        message = service.users().messages().get(
            userId="me", id=email_message_id, format="full").execute()
        body, attachments = extract_body_and_attachments(message)
        print(f'attachment here {attachments}')
        print(
            f'index - {index}, mime_type - {mime_type}, message_id - {email_message_id}')
        attachment = service.users().messages().attachments().get(
            userId='me', messageId=email_message_id, id=attachments[index]['id']
        ).execute()
        print(f'attachment {attachment}')
        file_data = BytesIO(base64.urlsafe_b64decode(
            attachment['data'].encode('UTF-8')))
        # file_data.name = attachment["filename"]
        print(f'there is a valid file_data {mime_type}')
        if mime_type.startswith("image/"):
            bot.send_photo(chat_id=call.message.chat.id, photo=file_data,
                           reply_parameters=ReplyParameters(chat_id=call.message.chat.id))
        elif mime_type == "application/pdf":
            bot.send_document(chat_id=call.message.chat.id, photo=file_data,
                              reply_parameters=ReplyParameters(chat_id=call.message.chat.id))


bot.remove_webhook()

# Set webhook
bot.set_webhook(
    url=BOT_URL_BASE + BOT_TOKEN
)

# bot.polling()
