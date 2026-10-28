from database import Base, engine
from models import Account, Transaction


if __name__ == "__main__":
    try:
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully!")
    finally:
        engine.dispose()