from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Text, TypeDecorator
from sqlalchemy.orm import validates
from typing import Union
import bcrypt

class Base(DeclarativeBase):
 pass

import bcrypt

class PasswordHash:
    def __init__(self, hash_: bytes | str):
        if isinstance(hash_, str):
            hash_ = hash_.encode("utf-8")
        assert len(hash_) == 60, "bcrypt hash should be 60 chars."
        assert hash_.count(b"$") == 3, "bcrypt hash should have 3x '$'."
        self.hash = hash_
        self.rounds = int(self.hash.split(b"$")[2])

    def __eq__(self, candidate: Union[str, bytes, "PasswordHash"]):
        if isinstance(candidate, PasswordHash):
            return self.hash == candidate.hash
        if isinstance(candidate, str):
            candidate = candidate.encode("utf-8")
        return bcrypt.hashpw(candidate, self.hash) == self.hash


    def __repr__(self):
        return f"<{type(self).__name__}>"

    @classmethod
    def new(cls, password: str | bytes, rounds: int):
        if isinstance(password, str):
            password = password.encode("utf-8")
        return cls(bcrypt.hashpw(password, bcrypt.gensalt(rounds)))

    
class Password(TypeDecorator):
    impl = Text

    def __init__(self, rounds=12, **kwds):
        self.rounds = rounds
        super().__init__(**kwds)

    def process_bind_param(self, value, dialect):
        return self._convert(value).hash.decode("utf-8")

    def process_result_value(self, value, dialect):
        if value is not None:
            return PasswordHash(value)

    def validator(self, password):
        return self._convert(password)

    def _convert(self, value):
        if isinstance(value, PasswordHash):
            return value
        elif isinstance(value, (str, bytes)):
            return PasswordHash.new(value, self.rounds)
        elif value is not None:
            raise TypeError(f"Cannot convert {type(value)} to a PasswordHash")


class UserDB(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(primary_key=True, index=True)
    firstname: Mapped[str] = mapped_column(String, nullable=False)
    lastname: Mapped[str] = mapped_column(String, nullable=False)
    username:Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password:Mapped[Password] = mapped_column(Password, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)

    model_config = {
        "from_attributes": True
    }
    
    @validates('password')
    def _validate_password(self, key, password):
        return getattr(type(self), key).type.validator(password)

 