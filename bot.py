import base64
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthTransportRequest
import firebase_admin
from firebase_admin import credentials, firestore_async
import json


load_dotenv()

URL_BASE = os.getenv("URL_BASE")
AUTH_URL_BASE = os.getenv("AUTH_URL_BASE")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
BOT_TOKEN = os.getenv('BOT_TOKEN')


app = FastAPI()
bot = telebot.TeleBot(BOT_TOKEN)

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db = firestore_async.client()


def gen_markup(user_id: str):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton(
        "Authorize me", url=f'{AUTH_URL_BASE}authorize/{user_id}'))
    return markup


@app.post(path=f"/{BOT_TOKEN}")
def process_webhook_text_pay_bot(update: dict):
    """
    Process webhook calls for textpay
    """
    if update:
        update = telebot.types.Update.de_json(update)
        bot.process_new_updates([update])
    else:
        return


@bot.message_handler(commands=['start'])
def send_welcome(message):
    # TODO check if their details already exists in the db
    bot.send_message(chat_id=message.from_user.id,
                     text="Hi here! Please authorize me to set up a Gmail integration.", reply_markup=gen_markup(message.from_user.id))


@app.post("/push-handlers/receive_messages")
async def receive_messages_handler(request: Request):
    # TODO work on authentication
    envelope = await request.json()

    message_data = envelope["message"]["data"]

    payload = json.loads(base64.b64decode(message_data).decode('utf-8'))
    print(f'payload is => {payload}')

    history_id = payload['historyId']
    recipient_email = payload['emailAddress']

    doc_ref = db.collection("users").document(recipient_email)
    doc = await doc_ref.get()
    doc = doc.to_dict()
    creds = Credentials(
        token=doc['token'],
        refresh_token=doc['refresh_token'],
        token_uri=doc['token_uri'],
        client_id=doc['client_id'],
        client_secret=doc['client_secret'],
        granted_scopes=doc['granted_scopes']
    )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthTransportRequest())
        else:
            # TODO send a message on the bot that they need to authorize, and a button to take them to the authorizaton site
            pass
        #     flow = InstalledAppFlow.from_client_secrets_file(
        #         "credentials.json", SCOPES
        #     )
        data = {
            'email': recipient_email,
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'granted_scopes': creds.granted_scopes}

        doc_ref = db.collection("users").document(recipient_email)
        await doc_ref.set(data)

    doc_ref = db.collection("users").document(recipient_email)
    doc = await doc_ref.get()
    receipient_user_id = doc.to_dict()['user_id']

    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton("Mark as Read"))

    bot.send_message(chat_id=receipient_user_id, text="""✉️ Someone <someone@gmail.com>
    SUBJECT
                     
    YOU HAVE A NEW MAIL""", reply_markup=markup)

    # TODO this code block is causing too many errors, so find a way to solve getting the body of the message
    # service = build("gmail", "v1", credentials=creds)
    # Step 1: Get message history
    # history = service.users().history().list(
    #     userId='me', startHistoryId=history_id).execute()
    # message_id = history['history'][0]['messagesAdded'][0]['message']['id']
    # # Step 2: Get the message
    # message = service.users().messages().get(
    #     userId='me', id=message_id, format='full').execute()

    # # Step 3: Decode the message body
    # for part in message['payload']['parts']:
    #     if part['mimeType'] == 'text/plain':  # or 'text/html' for HTML content
    #         body = base64.urlsafe_b64decode(
    #             part['body']['data']).decode('utf-8')

    #         bot.send_message(chat_id=receipient_user_id,
    #                          text=body)

    return JSONResponse(content={"message": "OK"}, status_code=200)


bot.remove_webhook()

# Set webhook
bot.set_webhook(
    url=URL_BASE + BOT_TOKEN
)

# bot.polling()
