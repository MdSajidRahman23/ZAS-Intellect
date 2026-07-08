from app.core.db import SessionLocal, init_db
from app.core.security import hash_password
from app.models.database import User


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        users = [
            ("0242220005101027", "Md Sajid Rahman", "sajid@student.diu.edu.bd", "student", "student123"),
            ("0242220005101473", "Zahin Muntaha Khan", "zahin@student.diu.edu.bd", "student", "student123"),
            ("CIS-TEACHER", "DIU Course Teacher", "teacher@diu.edu.bd", "teacher", "teacher123"),
        ]
        for identifier, name, email, role, password in users:
            existing = db.query(User).filter(User.identifier == identifier).first()
            if not existing:
                db.add(User(
                    identifier=identifier,
                    name=name,
                    email=email,
                    role=role,
                    department="CSE",
                    password_hash=hash_password(password),
                ))
        db.commit()
        print("Database ready. Demo users seeded.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
