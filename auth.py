from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
import google_auth_oauthlib
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthTransportRequest
import firebase_admin
from firebase_admin import credentials, firestore_async


load_dotenv()

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

SECRET_KEY = os.getenv('SECRET_KEY')
OAUTH_CLIENT_SECRETS_PATH = os.getenv("CLIENT_SECRETS_PATH")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db = firestore_async.client()

@app.get(path='/')
async def index():
    return 'welcome'


@app.get("/authorize/{user_id}")
async def authorize(user_id: str, request: Request):
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        OAUTH_CLIENT_SECRETS_PATH, scopes=SCOPES)

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

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(OAUTH_CLIENT_SECRETS_PATH,
                                                                   scopes=SCOPES, state=state)

    flow.redirect_uri = request.url_for('oauth2callback')
    authorization_response = str(request.url)
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials
    service = build("gmail", "v1", credentials=credentials)
    request = {
    'labelIds': ['INBOX'],
    'topicName': 'projects/cugram-442817/topics/EmailService',
    'labelFilterBehavior': 'INCLUDE'
}

    service.users().watch(userId='me', body=request).execute()
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
    return RedirectResponse('https://t.me/CUgram_bot', status_code=status.HTTP_303_SEE_OTHER)


def check_granted_scopes(credentials):
    features = {}
    if 'https://www.googleapis.com/auth/gmail.readonly' in credentials['granted_scopes']:
        features['mail'] = True
    else:
        features['mail'] = False
    return features

