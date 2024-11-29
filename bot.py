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

from gmail_api_utils import get_email_details, mark_unmark_message_as_read


load_dotenv()

URL_BASE = os.getenv("URL_BASE")
AUTH_URL_BASE = os.getenv("AUTH_URL_BASE")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
BOT_TOKEN = os.getenv('BOT_TOKEN')
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
    users_ref = db_without_async.collection(USERS_COLLECTION)
    query_ref = users_ref.where(filter=FieldFilter(
        "user_id", "==", f"{message.from_user.id}"))
    docs = query_ref.get()

    if len(docs) != 0:
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
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleAuthTransportRequest())
            else:
                bot.send_message(chat_id=message.from_user.id,
                                 text="Hi here! Please authorize me to set up a Gmail integration.", reply_markup=gen_markup(message.from_user.id))
                return
        bot.send_message(chat_id=message.from_user.id,
                         text=f"You are authorized as {doc['email']}")
        return

    bot.send_message(chat_id=message.from_user.id,
                     text="Hi here! Please authorize me to set up a Gmail integration.", reply_markup=gen_markup(message.from_user.id))


@app.get('/auth-complete/{user_id}')
def on_auth_completed(user_id: str):
    bot.send_message(user_id, text='Integration completed ✅')


@app.post("/push-handlers/receive_messages")
async def receive_messages_handler(request: Request):
    # TODO work on authentication
    envelope = await request.json()

    message_data = envelope["message"]["data"]

    payload = json.loads(base64.b64decode(message_data).decode('utf-8'))
    print(f'payload is => {payload}')

    history_id = payload['historyId']
    recipient_email = payload['emailAddress']

    doc_ref = db_async.collection(USERS_COLLECTION).document(recipient_email)
    doc = await doc_ref.get()
    if not doc.exists:
        return
    doc = doc.to_dict()

    saved_history_id = doc.get('history_id', None)
    doc_credential = doc['credential']
    creds = Credentials(
        token=doc_credential['token'],
        refresh_token=doc_credential['refresh_token'],
        token_uri=doc_credential['token_uri'],
        client_id=doc_credential['client_id'],
        client_secret=doc_credential['client_secret'],
        granted_scopes=doc_credential['granted_scopes'],
    )
    receipient_user_id = doc['user_id']

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthTransportRequest())
        else:
            bot.send_message(chat_id=receipient_user_id,
                             text="Looks like something is wrong with your credentials. Please reauthorize me.", reply_markup=gen_markup(receipient_user_id))
            return

    if not saved_history_id:
        # if there wasn't any saved history id don't send any message since it is the last saved history we use
        # to send the current message
        return

    service = build("gmail", "v1", credentials=creds)
    sender_name, sender_email, subject, body, attachments, message_id = get_email_details(
        service=service, history_id=saved_history_id)

    if not subject and not body and not sender_name and not sender_email and not message_id:
        return

    if doc.get('message_id', None) == message_id:
        return
    data = {
        'history_id': history_id,
        'message_id': message_id,
        'email': recipient_email,
        'user_id': receipient_user_id,
        'credential': {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'granted_scopes': creds.granted_scopes
        },
    }

    doc_ref = db_async.collection(
        USERS_COLLECTION).document(recipient_email)
    await doc_ref.set(data)

    markup = InlineKeyboardMarkup()
    for attachment in attachments:
        if attachment['mimeType'].startswith("image/"):
            markup.add(InlineKeyboardButton(
             f"🖼 {attachment['filename']}", callback_data=f"cb*get_attachment*{attachment['mimeType']}*{message_id}*{attachment['id']}"))
            
        elif attachment['mimeType'] == "application/pdf":
            markup.add(InlineKeyboardButton(
             f"📎 {attachment['filename']}", callback_data=f"cb*get_attachment*{attachment['mimeType']}*{message_id}*{attachment['id']}"))
    
    markup.add(InlineKeyboardButton("Mark as Read", callback_data=f"cb*mark_as_read*{message_id}"))

    bot.send_message(chat_id=receipient_user_id, text=f"""✉️ {sender_name} <{sender_email}>
SUBJECT: {subject}
                     
BODY: {body}""", reply_markup=markup, parse_mode='markdown')

    return JSONResponse(content={"message": "OK"}, status_code=200)


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
        mime_type, email_message_id, attachment_id = call.data.split('*')[2], call.data.split('*')[3], call.data.split('*')[4]
        attachment = service.users().messages().attachments().get(
                    userId='me', messageId=email_message_id, id=attachment_id
                ).execute()
        file_data = BytesIO(base64.urlsafe_b64decode(attachment['data'].encode('UTF-8')))
        # file_data.name = attachment["filename"]

        if mime_type.startswith("image/"):
            bot.send_photo(chat_id=call.message.chat.id, photo=file_data, reply_parameters=ReplyParameters(chat_id=call.message.chat.id))
        elif mime_type == "application/pdf":
            bot.send_document(chat_id=call.message.chat.id, photo=file_data, reply_parameters=ReplyParameters(chat_id=call.message.chat.id))

    elif action == "mark_as_read":
        email_message_id = call.data.split('*')[2]
        
        mark_unmark_message_as_read(
            service=service, message_id=email_message_id, mark_as_read=True)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            "Mark as Unread", callback_data=f"cb*mark_as_unread*{email_message_id}"))
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

    elif action == "mark_as_unread":
        email_message_id = call.data.split('*')[2]
        mark_unmark_message_as_read(
            service=service, message_id=email_message_id, mark_as_read=False)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            "Mark as Read", callback_data=f"cb*mark_as_read*{email_message_id}"))
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)


bot.remove_webhook()

# Set webhook
bot.set_webhook(
    url=URL_BASE + BOT_TOKEN
)

# bot.polling()
