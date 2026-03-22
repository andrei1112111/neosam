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


class User(BaseModel):
    id = AutoField()
    username = CharField(max_length=100)
    # I2P destination может быть значительно длиннее 255 символов.
    address = CharField(unique=True, max_length=1024)

    is_online = BooleanField(default=False)
    last_seen = DateTimeField(default=datetime.datetime.now)
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "users"


class MyProfile(BaseModel):
    """
    Информация о текущем пользователе приложения.
    """
    id = AutoField()
    user = ForeignKeyField(User, backref="my_profile", unique=True, on_delete="CASCADE")
    display_name = CharField(max_length=150, null=True)
    bio = TextField(null=True)

    class Meta:
        table_name = "my_profile"
