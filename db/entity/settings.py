from peewee import (
    AutoField,
    CharField,
    BooleanField
)

from db.entity.basemodel import BaseModel


class Settings(BaseModel):
    id = AutoField()
    theme = CharField(max_length=32)
    initialized = BooleanField(default=False)

    class Meta:
        table_name = "settings"
