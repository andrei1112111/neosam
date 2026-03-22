from .db import db
from .entity.settings import Settings
from .entity.chat import Chat
from .entity.message import Message, MessageReaction
from .entity.user import User, MyProfile



db.connect()
db.create_tables([Settings, User, MyProfile, Chat, Message, MessageReaction])

__all__ = [
    "Settings", "Chat", "Message", "MessageReaction", "User", "MyProfile"
]
