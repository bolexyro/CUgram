# Where I got some info from https://docs.replit.com/additional-resources/google-auth-in-flask

from fastapi import Depends, Request, APIRouter
from telebot import async_telebot
import os
from firebase_admin import firestore_async
from fastapi.templating import Jinja2Templates
# from auth.utils import get_user_info, validate_init_data_signature, generate_jwt
from datetime import timedelta
from core.config import settings
from .service import AuthService

ACCESS_TOKEN_EXPIRATION_DELTA = timedelta(hours=2)
REFRESH_TOKEN_EXPIRATION_DELTA = timedelta(weeks=1)

auth_router = APIRouter(prefix="/auth", tags=["auth"])

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

db = firestore_async.client()

student_bot = async_telebot.AsyncTeleBot(settings.student_bot_token)
dsa_bot = async_telebot.AsyncTeleBot(settings.dsa_bot_token)


templates = Jinja2Templates(directory="templates")


def get_auth_service():
    return AuthService(db, student_bot, dsa_bot)


@auth_router.get("/authorize/{user_id}")
async def authorize(*, user_id: str, is_official: bool = False, auth_service: AuthService = Depends(get_auth_service), request: Request):
    return await auth_service.authorize(user_id, is_official, request)


@auth_router.get(path="/oauth2callback")
async def oauth2callback(request: Request, auth_service: AuthService = Depends(get_auth_service)):
    return await auth_service.oauth2callback(request, templates)


# @app.get(path="/validate/{init_data}")
# async def validate_init_data(init_data: str) -> UserResponse:
#     user_data: TelegramUser | None = validate_init_data_signature(
#         init_data, settings.dsa_bot_token
#     )
#     if not user_data:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Invalid data signature. Access forbidden.",
#         )
#     print(user_data)
#     official_ref = db.collection(CloudCollections.officials.value).document(
#         str(user_data.id)
#     )

#     official = await official_ref.get()

#     if not official.exists:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Access denied. Please verify your administrative position at Covenant University"
#             "by authenticating through the bot before accessing this mini app.",
#         )

#     official = User(**official.to_dict())

#     access_token = generate_jwt(
#         secret=settings.jwt_signing_secret_key,
#         expires_delta=ACCESS_TOKEN_EXPIRATION_DELTA,
#     )
#     refresh_token = generate_jwt(
#         secret=settings.jwt_signing_secret_key,
#         expires_delta=REFRESH_TOKEN_EXPIRATION_DELTA,
#     )
#     return UserResponse(
#         email=official.email,
#         name=official.name,
#         refresh_token=refresh_token,
#         access_token=access_token,
#         photo_url=user_data.photo_url,
#     )


# @app.post(path="/refresh")
# def refresh_access_token(refresh_token: str):
#     pass
