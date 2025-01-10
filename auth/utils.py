import aiohttp
from models.schemas import TelegramUser, User

from urllib.parse import parse_qs
import hmac
import hashlib
import json

import jwt
from datetime import datetime, timedelta, timezone

# Secret key to sign the JWT
SECRET_KEY = "your_secret_key"


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


def validate_init_data_signature(init_data: str, bot_token: str) -> bool:
    query_string = init_data

    query_dict = parse_qs(query_string)
    query_dict = {k: v[0]
                  for k, v in query_dict.items()}
    query_dict = {k: query_dict[k] for k in sorted(query_dict)}
    data_check_string = '\n'.join(
        f"{k}={v}" for k, v in sorted(query_dict.items()) if k != 'hash')

    secret_key = hmac.new(b"WebAppData",
                          bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    received_hash = query_dict.get("hash", None)
    if not received_hash:
        return None

    if expected_hash == received_hash:
        return TelegramUser(**json.loads(query_dict["user"]))


def generate_jwt(*, payload: dict = {}, secret: str, algorithm: str = "HS256", expires_delta: timedelta = timedelta(minutes=30)) -> str:
    """
    Generate a JWT token.

    :param payload: The data to include in the token.
    :param secret: The secret key for signing the token.
    :param algorithm: The hashing algorithm (default: HS256).
    :param expiration_minutes: Token expiration time in minutes.
    :return: Encoded JWT token.
    """
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, secret, algorithm)


def decode_jwt(token: str, secret: str, algorithms: list = ["HS256"]) -> dict:
    """
    Decode a JWT token.

    :param token: The encoded JWT token.
    :param secret: The secret key for verifying the token.
    :param algorithms: A list of allowed hashing algorithms.
    :return: Decoded token payload.
    """
    try:
        decoded = jwt.decode(token, secret, algorithms=algorithms)
        return decoded
    except jwt.ExpiredSignatureError:
        raise Exception("Token has expired.")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token.")

