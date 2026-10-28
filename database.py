import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


load_dotenv(Path(__file__).with_name(".env"))

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    database=os.environ["DB_NAME"],
)

engine = create_engine(
    database_url,
    connect_args={
        "sslmode": "require",
        "connect_timeout": 10,
    },
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass