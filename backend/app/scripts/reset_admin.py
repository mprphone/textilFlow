"""Repõe admin / admin123 para o ambiente de demonstração."""
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.db import SessionLocal
from app.models import User


def main() -> None:
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        if not user:
            print("admin not found")
            return
        user.password_hash = hash_password("admin123")
        user.must_change_password = False
        user.active = True
        db.commit()
        print("ok")
    finally:
        db.close()


if __name__ == "__main__":
    main()
