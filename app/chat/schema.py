from pydantic import BaseModel

class ChatMessage(BaseModel):
    messages:str
    thread_id:str
    title:str|None = None