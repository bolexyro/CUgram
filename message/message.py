from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from auth.utils import decode_jwt
import firebase_admin
from firebase_admin import credentials, firestore_async
from typing import Annotated
import os
from dotenv import load_dotenv

load_dotenv()


SERVICE_ACCOUNT_KEY_PATH = os.getenv("SERVICE_ACCOUNT_KEY_PATH")
JWT_SIGNING_SECRET_KEY = os.getenv("JWT_SIGNING_SECRET_KEY")

security = HTTPBearer()

app = FastAPI()

firebase_cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
firebase_admin.initialize_app(firebase_cred)
db = firestore_async.client()


def verify_access_token(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    try:
        decode_jwt(token=credentials.credentials,
                   secret=JWT_SIGNING_SECRET_KEY)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.post("/message/rich", dependencies=[Depends(verify_access_token)])
async def create_rich_message():
    """
    Endpoint to create a rich message from a text editor.
    """
    print("rich message endpoint reached how can I help you")
