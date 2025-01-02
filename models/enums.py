from enum import Enum


class ContentType(Enum):
    audio = "audio"
    photo = "photo"
    voice = "voice"
    video = "video"
    document = "document"


class CloudCollections(Enum):
    students = "students"
    officials = "officials"
