from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from core.config import settings
from contextlib import asynccontextmanager
import firebase_admin
from firebase_admin import credentials

cred = credentials.Certificate(settings.service_account_key_path)
firebase_admin.initialize_app(cred)

from src.auth.router import auth_router
from src.bots import student_bot
from src.bots.student_bot import student_bot_router
from src.bots.dsa_bot import dsa_bot, dsa_bot_router
from src.message.router import message_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await dsa_bot.remove_webhook()
    await dsa_bot.set_webhook(url=f"{settings.server_url_base}/dsa_bot/{settings.dsa_bot_token}")
    await student_bot.bot.remove_webhook()
    await student_bot.bot.set_webhook(url=f"{settings.server_url_base}/student_bot/{settings.student_bot_token}")
    yield

app = FastAPI(lifespan=lifespan)


app.add_middleware(SessionMiddleware,
                   secret_key=settings.fastapi_session_secret_key)

app.mount("/static", StaticFiles(directory="static"), name="static")


app.include_router(auth_router)
app.include_router(student_bot_router)
app.include_router(dsa_bot_router)
app.include_router(message_router)
