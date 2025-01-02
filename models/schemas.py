from pydantic import BaseModel, ConfigDict
import io


class User(BaseModel):
    email: str
    name: str


class Message(BaseModel):
    text: str
    user: User
    attachments: list["Attachment"] | None = None


class Attachment(BaseModel):
    url: str
    content_type: str
    file_id: str

class DownloadedAttachment(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    # model_config = ConfigDict(arbitrary_types_allowed=True)
    file: io.BytesIO
    content_type: str
