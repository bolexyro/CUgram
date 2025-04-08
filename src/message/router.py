from fastapi import Depends, HTTPException, status, APIRouter
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.auth.utils import decode_jwt
from firebase_admin import firestore_async
from typing import Annotated
from core.config import settings

security = HTTPBearer()

message_router = APIRouter(prefix="/message", tags=["message"])

db = firestore_async.client()


def verify_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
):
    try:
        decode_jwt(
            token=credentials.credentials, secret=settings.jwt_signing_secret_key
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@message_router.post("/rich", dependencies=[Depends(verify_access_token)])
async def create_rich_message():
    """
    Endpoint to create a rich message from a text editor.
    """
    print("rich message endpoint reached how can I help you")
