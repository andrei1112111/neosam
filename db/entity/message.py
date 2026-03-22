import datetime
from peewee import (
    AutoField,
    CharField,
    BooleanField,
    DateTimeField,
    ForeignKeyField,
    TextField,
)

from db.entity.basemodel import BaseModel
from db.entity.chat import Chat
from db.entity.user import User


class Message(BaseModel):
    id = AutoField()
    chat = ForeignKeyField(Chat, backref="messages", on_delete="CASCADE")
    sender = ForeignKeyField(User, backref="sent_messages", on_delete="CASCADE")

    text = TextField(null=True)

    # Ответ на другое сообщение
    reply_to = ForeignKeyField(
        "self",
        null=True,
        backref="replies",
        on_delete="SET NULL"
    )

    sent_at = DateTimeField(default=datetime.datetime.now)
    delivered_at = DateTimeField(null=True)
    read_at = DateTimeField(null=True)

    is_delivered = BooleanField(default=False)
    is_read = BooleanField(default=False)
    is_edited = BooleanField(default=False)
    edited_at = DateTimeField(null=True)
    is_deleted = BooleanField(default=False)
    deleted_at = DateTimeField(null=True)

    class Meta:
        table_name = "messages"
        indexes = (
            (("chat", "sent_at"), False),
            (("chat", "is_read", "sent_at"), False),
            (("chat", "is_deleted", "sent_at"), False),
        )


class MessageReaction(BaseModel):
    """
    Реакция пользователя на сообщение.
    """
    id = AutoField()
    message = ForeignKeyField(Message, backref="reactions", on_delete="CASCADE")
    user = ForeignKeyField(User, backref="message_reactions", on_delete="CASCADE")
    reaction = CharField(max_length=32)
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "message_reactions"
        indexes = (
            (("message", "user", "reaction"), True),
        )
