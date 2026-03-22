import datetime
from peewee import (
    AutoField,
    DateTimeField,
    ForeignKeyField,
    Check,
)

from db.entity.basemodel import BaseModel
from db.entity.user import User


class Chat(BaseModel):
    """
    Только p2p чат
    """
    id = AutoField()
    user1 = ForeignKeyField(User, backref="chats_as_user1", on_delete="CASCADE")
    user2 = ForeignKeyField(User, backref="chats_as_user2", on_delete="CASCADE")
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "chats"
        constraints = [
            Check("user1_id != user2_id"),
        ]
        indexes = (
            (("user1", "user2"), True),
        )

    @staticmethod
    def normalize_users(user_a, user_b):
        if user_a.id == user_b.id:
            raise ValueError("Нельзя создать чат с самим собой")
        return sorted([user_a, user_b], key=lambda u: u.id)

    @classmethod
    def get_or_create_private_chat(cls, user_a, user_b):
        user1, user2 = cls.normalize_users(user_a, user_b)
        chat, created = cls.get_or_create(user1=user1, user2=user2)
        return chat, created
