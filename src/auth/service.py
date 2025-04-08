from datetime import timedelta
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import google_auth_oauthlib
from firebase_admin import firestore_async
from core.config import settings
from core.enums import CloudCollections
from telebot import async_telebot
import aiohttp
from core.schemas import User

ACCESS_TOKEN_EXPIRATION_DELTA = timedelta(hours=2)
REFRESH_TOKEN_EXPIRATION_DELTA = timedelta(weeks=1)


class AuthService:
    def __init__(self, db: firestore_async.AsyncClient, student_bot: async_telebot.AsyncTeleBot, dsa_bot: async_telebot.AsyncTeleBot):
        self.db = db
        self.student_bot = student_bot
        self.dsa_bot = dsa_bot

    async def authorize(self, user_id: str, is_official: bool, request: Request):
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            settings.client_secrets_path, scopes=settings.scopes
        )

        flow.redirect_uri = request.url_for("oauth2callback")

        authorization_url, state = flow.authorization_url()

        request.session["state"] = state
        request.session["user_id"] = user_id
        if is_official:
            request.session["is_official"] = True
        return RedirectResponse(authorization_url, status_code=status.HTTP_303_SEE_OTHER)

    async def oauth2callback(self, request: Request, templates: Jinja2Templates):
        state = request.session.get("state", False)
        user_id = request.session.get("user_id", None)
        is_official = request.session.get("is_official", False)
        request.session.clear()

        if not state and not user_id:
            return templates.TemplateResponse(
                name="error_page.html",
                request=request,
                context={"error_message": "Invalid state parameter",
                         "close_on_click": True},
            )

        error = request.query_params.get("error")
        if error:
            return templates.TemplateResponse(
                name="error_page.html",
                request=request,
                context={"error_message": error, "user_id": user_id, "is_official": is_official},
            )

        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            settings.client_secrets_path, scopes=settings.scopes, state=state
        )

        flow.redirect_uri = request.url_for("oauth2callback")
        authorization_response = str(request.url)
        flow.fetch_token(authorization_response=authorization_response)

        credentials = flow.credentials
        user = await AuthService.get_google_user_info(credentials.token)

        if is_official and user.email not in settings.official_emails:
            return templates.TemplateResponse(
                name="not_student.html",
                request=request,
                context={"user_id": user_id, "is_official": is_official},
            )

        if not is_official and user.email.endswith("@stu.cu.edu.ng") == False:
            return templates.TemplateResponse(
                name="not_student.html",
                request=request,
                context={"user_id": user_id, "is_official": is_official},
            )

        data = user.model_dump(exclude_none=True)

        doc_ref = self.db.collection(
            CloudCollections.officials.value
            if is_official
            else CloudCollections.students.value
        ).document(user_id)
        await doc_ref.set(data)

        try:
            if is_official:
                await self.dsa_bot.send_message(
                    user_id,
                    text="Thank you for verifying your Covenant University email! You're now authorized to use the bot and receive messages.✅",
                )
            else:
                await self.student_bot.send_message(
                    user_id,
                    text="Thank you for verifying your Covenant University email! You're now authorized to use the bot and receive messages. ✅",
                )
        except Exception as e:
            # if the user id is not found
            pass

        return RedirectResponse(
            "https://t.me/DSACU_bot" if is_official else "https://t.me/CUgram_bot",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @staticmethod
    async def get_google_user_info(access_token: str) -> User:
        url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url=url) as response:
                    response.raise_for_status()
                    user_info = await response.json()
                    return User(**user_info)

        except aiohttp.ClientResponseError as e:
            print(
                f"Failed to fetch user info: {e.status} {e.message}")
            return None
