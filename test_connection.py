# import os
# from pathlib import Path

# from dotenv import load_dotenv
# from sqlalchemy import URL, create_engine, text


# load_dotenv(Path(__file__).with_name(".env"))


# database_url = URL.create(
#     drivername="postgresql+psycopg",
#     username=os.environ["DB_USER"],
#     password=os.environ["DB_PASSWORD"],
#     host=os.environ["DB_HOST"],
#     port=int(os.environ["DB_PORT"]),
#     database=os.environ["DB_NAME"],
# )


# engine = create_engine(
#     database_url,
#     connect_args={
#         "sslmode": "require",
#         "connect_timeout": 10,
#     },
#     pool_pre_ping=True,
# )

# try:
#     with engine.connect() as connection:
#         result = connection.execute(text("SELECT 1")).scalar_one()
#         print(f"Database connected successfully! Result: {result}")
# finally:
#     engine.dispose()


from sqlalchemy import text

from database import engine


try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()
        print(f"Database connected successfully! Result: {result}")
finally:
    engine.dispose()