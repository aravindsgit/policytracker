"""Fill the database with invented clients and policies: python seed.py [--reset]"""
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models import Base, Client, Policy, SessionLocal, engine, init_db

FIRST = ["Asha", "Ravi", "Meera", "Kiran", "Sanjay", "Divya", "Arjun", "Latha", "Imran", "Neha"]
LAST = ["Rao", "Reddy", "Sharma", "Iyer", "Khan", "Patel", "Naidu", "Menon", "Das", "Singh"]
TYPES = ["Life", "Health", "Motor", "Home", "Travel"]
INSURERS = ["Acme Assurance", "Northwind Insurance", "Bluebird Life", "Harbor General"]

if "--reset" in sys.argv:
    Base.metadata.drop_all(engine)
init_db()
random.seed(7)
today = date.today()
with SessionLocal() as db:
    if db.scalar(select(Client.id)):
        raise SystemExit("Database already has data. Run with --reset to start over.")
    number = 1000
    for i in range(30):
        client = Client(name=f"{random.choice(FIRST)} {random.choice(LAST)}", email=f"client{i + 1}@example.com",
                        phone=f"90000{i:05d}")
        db.add(client)
        db.flush()
        for _ in range(random.choice([1, 2, 2, 3])):
            number += 1
            end = today + timedelta(days=random.choice([3, 9, 16, 25, 29, 45, 90, 200, 300, -20]))
            db.add(Policy(client_id=client.id, policy_number=f"POL-{number}", type=random.choice(TYPES),
                          insurer=random.choice(INSURERS), premium=Decimal(random.randint(2000, 90000)) / 10 * 10,
                          start_date=end - timedelta(days=365), end_date=end,
                          status="lapsed" if end < today else random.choice(["active"] * 4 + ["cancelled"])))
    db.commit()
    print("Seeded 30 invented clients and their policies.")
