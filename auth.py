# Where I got some info from https://docs.replit.com/additional-resources/google-auth-in-flask

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
import google_auth_oauthlib
import firebase_admin
from firebase_admin import credentials, firestore_async
import requests

from pydantic import BaseModel

class User(BaseModel):
    picture: str | None = None
    email: str

load_dotenv()

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

FASTAPI_AUTH_SECRET_KEY = os.getenv('FASTAPI_AUTH_SECRET_KEY')
OAUTH_CLIENT_SECRETS_PATH = os.getenv("CLIENT_SECRETS_PATH")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
SCOPES = ["https://www.googleapis.com/auth/userinfo.email"]
STUDENT_BOT_URL_BASE = os.getenv("STUDENT_BOT_URL_BASE")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=FASTAPI_AUTH_SECRET_KEY)

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

    authorization_url, state = flow.authorization_url()

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
    user = get_user_info(credentials.token)

    data = {
        'email': user.email,
    }

    doc_ref = db.collection("users").document(user_id)
    await doc_ref.set(data)

    url = STUDENT_BOT_URL_BASE + f'auth-complete/{user_id}'
    # this request is so that the bot sends the user a confirmation message
    requests.get(url=url)
    return RedirectResponse('https://t.me/CUgram_bot', status_code=status.HTTP_303_SEE_OTHER)


def get_user_info(access_token: str) -> User:
    response = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={
       "Authorization": f"Bearer {access_token}"
   })
    if response.status_code == 200:
        user_info = response.json()
        return User(**user_info)
    else:
        print(f"Failed to fetch user info: {response.status_code} {response.text}")
        return None
