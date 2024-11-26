import base64
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
import google_auth_oauthlib
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthTransportRequest
import firebase_admin
from firebase_admin import credentials, firestore_async
import json


load_dotenv()

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'


SECRET_KEY = os.getenv('SECRET_KEY')
PUBSUB_VERIFICATION_TOKEN = "your_verification_token"
URL_BASE = os.getenv("URL_BASE")

CLIENT_SECRETS_PATH = os.getenv("CLIENT_SECRETS_PATH")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(cred)
db = firestore_async.client()


@app.get(path='/')
async def index():
    return 'welcome'


@app.get("/authorize/{user_id}")
async def authorize(user_id: str, request: Request):
    print(request.url_for('oauth2callback'))

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_PATH, scopes=SCOPES)

    flow.redirect_uri = request.url_for('oauth2callback')

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        login_hint='hint@example.com',
        prompt='consent')

    request.session['state'] = state
    request.session['user_id'] = user_id
    return RedirectResponse(authorization_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get(path='/oauth2callback')
async def oauth2callback(request: Request):

    error = request.query_params.get("error")
    if error:
        raise HTTPException(
            status_code=400, detail=f"OAuth 2.0 Error: {error}")

    state = request.session.get('state', False)
    user_id = request.session.get('user_id', None)

    if not state and not user_id:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(CLIENT_SECRETS_PATH,
                                                                   scopes=SCOPES, state=state)

    flow.redirect_uri = request.url_for('oauth2callback')
    authorization_response = str(request.url)
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials
    service = build("gmail", "v1", credentials=credentials)
    email = service.users().getProfile(userId='me').execute()['emailAddress']

    data = {
        'user_id': user_id,
        'email': email,
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'granted_scopes': credentials.granted_scopes}

    doc_ref = db.collection("users").document(email)
    await doc_ref.set(data)

    # TODO you can show them an error if they denied an important scope, if you have multiple scopes
    # features = check_granted_scopes(credentials)
    return data


def check_granted_scopes(credentials):
    features = {}
    if 'https://www.googleapis.com/auth/gmail.readonly' in credentials['granted_scopes']:
        features['mail'] = True
    else:
        features['mail'] = False
    return features


@app.post("/push-handlers/receive_messages")
async def receive_messages_handler(request: Request):
    # TODO work on authentication
    envelope = await request.json()

    message_data = envelope["message"]["data"]

    payload = base64.b64decode(message_data)
    print(f'envelope is => {envelope}')
    print(f'payload is => {payload}')

    data_str = payload.decode('utf-8')

    # Parse the JSON string into a Python dictionary
    parsed_data = json.loads(data_str)

    # Access the historyId
    history_id = parsed_data['historyId']
    recipient_email = parsed_data['emailAddress']

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
        # else:
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
   
    service = build("gmail", "v1", credentials=creds)


    # Step 1: Get message history
    history = service.users().history().list(
        userId='me', startHistoryId=history_id).execute()
    message_id = history['history'][0]['messagesAdded'][0]['message']['id']
    # Step 2: Get the message
    message = service.users().messages().get(
        userId='me', id=message_id, format='full').execute()

    # Step 3: Decode the message body
    for part in message['payload']['parts']:
        if part['mimeType'] == 'text/plain':  # or 'text/html' for HTML content
            body = base64.urlsafe_b64decode(
                part['body']['data']).decode('utf-8')
            print("Email Body:")
            print(body)
            bot.send_message(chat_id=receipient_user_id,
                             text=body)

    return JSONResponse(content={"message": "OK"}, status_code=200)


# Bot related stuff

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


def gen_markup(user_id: str):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton(
        "Authorize me", url=f'{URL_BASE}authorize/{user_id}'))
    return markup


@bot.message_handler(commands=['start'])
def send_welcome(message):
    global bolexyro_message_id
    bolexyro_message_id = message.from_user.id
    bot.send_message(chat_id=message.from_user.id,
                     text="Hi here! Please authorize me to set up a Gmail integration.", reply_markup=gen_markup(message.from_user.id))


# bot.remove_webhook()

# # Set webhook
# bot.set_webhook(
#     url=URL_BASE + BOT_TOKEN
# )

# bot.polling()
