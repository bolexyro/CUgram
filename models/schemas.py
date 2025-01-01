from pydantic import BaseModel

class User(BaseModel):
    picture: str | None = None
    email: str
    
class Message(BaseModel):
    text: str
    attachment: str | None = None
    content_type: str | None = None
