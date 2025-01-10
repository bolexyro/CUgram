# Where I got some info from https://docs.replit.com/additional-resources/google-auth-in-flask

from models.schemas import TelegramUser, User, UserResponse
from models.enums import CloudCollections
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
import google_auth_oauthlib
import firebase_admin
from firebase_admin import credentials, firestore_async
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiohttp

from urllib.parse import parse_qs
import hmac
import hashlib
import json

load_dotenv()

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

FASTAPI_AUTH_SECRET_KEY = os.getenv('FASTAPI_AUTH_SECRET_KEY')
OAUTH_CLIENT_SECRETS_PATH = os.getenv("CLIENT_SECRETS_PATH")
SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
SCOPES = ["https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/userinfo.profile"]
STUDENT_BOT_URL_BASE = os.getenv("STUDENT_BOT_URL_BASE")
DSA_BOT_URL_BASE = os.getenv("DSA_BOT_URL_BASE")
DSA_BOT_SERVER_SECRET_TOKEN = os.getenv("DSA_BOT_SERVER_SECRET_TOKEN")
STUDENT_BOT_SERVER_SECRET_TOKEN = os.getenv("STUDENT_BOT_SERVER_SECRET_TOKEN")
DSA_BOT_TOKEN = os.getenv("DSA_BOT_TOKEN")
OFFICIAL_EMAILS = ["odufuwa.adebola@stu.cu.edu.ng",
                   "dsa@cu.edu.ng", "seald@covenantuniversity.edu.ng"]

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=FASTAPI_AUTH_SECRET_KEY)

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db = firestore_async.client()

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

    url = (DSA_BOT_URL_BASE if is_official else STUDENT_BOT_URL_BASE) + \
        f'auth-complete/{user_id}'
    headers = {
        "Authorization": f"Bearer {DSA_BOT_SERVER_SECRET_TOKEN if is_official else STUDENT_BOT_SERVER_SECRET_TOKEN}"}
    # this request is so that the bot sends the user a confirmation message
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url=url) as response:
            pass
    return RedirectResponse("https://t.me/DSACU_bot" if is_official else "https://t.me/CUgram_bot", status_code=status.HTTP_303_SEE_OTHER)


async def get_user_info(access_token: str) -> User:
    url = "https://www.googleapis.com/oauth2/v3/userinfo"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url=url) as response:
            if response.status == 200:
                user_info = await response.json()
                return User(**user_info)
            else:
                print(
                    f"Failed to fetch user info: {response.status_code} {response.text}")
                return None


@app.get(path="/validate/{init_data}")
async def validate_init_data(init_data: str) -> UserResponse:
    user_data: TelegramUser | None = validate_init_data_signature(init_data)
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
    return UserResponse(email=official.email, name=official.name, refresh_token="this", access_token="that", photo_url=user_data.photo_url)


def validate_init_data_signature(init_data: str) -> bool:
    query_string = init_data

    query_dict = parse_qs(query_string)
    query_dict = {k: v[0]
                  for k, v in query_dict.items()}
    query_dict = {k: query_dict[k] for k in sorted(query_dict)}
    data_check_string = '\n'.join(
        f"{k}={v}" for k, v in sorted(query_dict.items()) if k != 'hash')

    secret_key = hmac.new(b"WebAppData",
                          DSA_BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    received_hash = query_dict.get("hash", None)
    if not received_hash:
        return None

    if expected_hash == received_hash:
        return TelegramUser(**json.loads(query_dict["user"]))
