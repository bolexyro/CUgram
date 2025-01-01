from enum import Enum

class AuthStatus(Enum):
    is_dean = 1
    is_not_dean = 2
    does_not_exist = 3

class ContentType(Enum):
    audio = "audio"
    photo = "photo"
    voice = "voice"
    video = "video"
    document = "document"