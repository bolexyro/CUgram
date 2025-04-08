from pydantic import BaseModel, model_serializer
import io


class User(BaseModel):
    email: str
    name: str


class UserResponse(User):
    photo_url: str | None = None
    access_token: str
    refresh_token: str


class Message(BaseModel):
    text: str
    user: User
    attachments: list["Attachment"] | None = None


class Attachment(BaseModel):
    url: str
    content_type: str
    file_id: str | None = None
    file_name: str

    @model_serializer
    def ser_model(self):
        return {"url": self.url, "content_type": self.content_type, "file_name": self.file_name}


class DownloadedAttachment(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    # model_config = ConfigDict(arbitrary_types_allowed=True)
    file: io.BytesIO
    content_type: str


class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
