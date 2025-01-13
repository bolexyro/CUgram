# Where I got some info from https://docs.replit.com/additional-resources/google-auth-in-flask

from models.schemas import TelegramUser, User, UserResponse
from models.enums import CloudCollections
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from telebot import async_telebot
import os
from dotenv import load_dotenv
import google_auth_oauthlib
import firebase_admin
from firebase_admin import credentials, firestore_async
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiohttp
from auth.utils import get_user_info, validate_init_data_signature, generate_jwt
from datetime import timedelta

load_dotenv()

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

FASTAPI_AUTH_SECRET_KEY = os.getenv('FASTAPI_AUTH_SECRET_KEY')
OAUTH_CLIENT_SECRETS_PATH = os.getenv("CLIENT_SECRETS_PATH")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")

DSA_BOT_TOKEN = os.getenv('DSA_BOT_TOKEN')
STUDENT_BOT_TOKEN = os.getenv('STUDENT_BOT_TOKEN')

JWT_SIGNING_SECRET_KEY = os.getenv("JWT_SIGNING_SECRET_KEY")
ACCESS_TOKEN_EXPIRATION_DELTA = timedelta(hours=2)
REFRESH_TOKEN_EXPIRATION_DELTA = timedelta(weeks=1)

SCOPES = ["https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/userinfo.profile"]
OFFICIAL_EMAILS = ["odufuwa.adebola@stu.cu.edu.ng",
                   "dsa@cu.edu.ng", "seald@covenantuniversity.edu.ng"]

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=FASTAPI_AUTH_SECRET_KEY)

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db = firestore_async.client()

student_bot = async_telebot.AsyncTeleBot(STUDENT_BOT_TOKEN)
dsa_bot = async_telebot.AsyncTeleBot(DSA_BOT_TOKEN)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get(path='/')
async def index():
    return 'welcome'


@app.get("/authorize/{user_id}")
async def authorize(*, user_id: str, is_official: bool = False, request: Request):
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        OAUTH_CLIENT_SECRETS_PATH, scopes=SCOPES)

    flow.redirect_uri = request.url_for('oauth2callback')

    authorization_url, state = flow.authorization_url()

    request.session['state'] = state
    request.session['user_id'] = user_id
    if is_official:
        request.session["is_official"] = True
    return RedirectResponse(authorization_url, status_code=status.HTTP_303_SEE_OTHER)


@app.get(path='/oauth2callback')
async def oauth2callback(request: Request):
    error = request.query_params.get("error")
    if error:
        # TODO redirect them to an error page
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
    user = await get_user_info(credentials.token)
    is_official = request.session.get("is_official", False)

    request.session.clear()

    if is_official and user.email not in OFFICIAL_EMAILS:
        return templates.TemplateResponse(name="not_student.html", request=request, context={
            "user_id": user_id,
            "is_official": is_official
        })

    if not is_official and user.email.endswith("@stu.cu.edu.ng") == False:
        return templates.TemplateResponse(name="not_student.html", request=request, context={
            "user_id": user_id,
            "is_official": is_official
        })

    data = user.model_dump(exclude_none=True)

    doc_ref = db.collection(
        CloudCollections.officials.value if is_official else CloudCollections.students.value).document(user_id)
    await doc_ref.set(data)

    if is_official:
        await dsa_bot.send_message(
            user_id, text='Thank you for verifying your Covenant University email! You\'re now authorized to use the bot and receive messages.✅')
    else:
        await student_bot.send_message(
            user_id, text='Thank you for verifying your Covenant University email! You\'re now authorized to use the bot and receive messages. ✅')

    return RedirectResponse("https://t.me/DSACU_bot" if is_official else "https://t.me/CUgram_bot", status_code=status.HTTP_303_SEE_OTHER)


@app.get(path="/validate/{init_data}")
async def validate_init_data(init_data: str) -> UserResponse:
    user_data: TelegramUser | None = validate_init_data_signature(
        init_data, DSA_BOT_TOKEN)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Invalid data signature. Access forbidden.")
    print(user_data)
    official_ref = db.collection(
        CloudCollections.officials.value).document(str(user_data.id))

    official = await official_ref.get()

    if not official.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Access denied. Please verify your administrative position at Covenant University"
            "by authenticating through the bot before accessing this mini app.")

    official = User(**official.to_dict())

    access_token = generate_jwt(
        secret=JWT_SIGNING_SECRET_KEY, expires_delta=ACCESS_TOKEN_EXPIRATION_DELTA)
    refresh_token = generate_jwt(
        secret=JWT_SIGNING_SECRET_KEY, expires_delta=REFRESH_TOKEN_EXPIRATION_DELTA)
    return UserResponse(email=official.email, name=official.name, refresh_token=refresh_token, access_token=access_token, photo_url=user_data.photo_url)


@app.post(path="/refresh")
def refresh_access_token(refresh_token: str):
    pass