"""Database tables and connection."""
import os
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def database_url():
    url = os.getenv("DATABASE_URL", "sqlite:///./policy_tracker.db")
    # Neon and others give postgresql://; SQLAlchemy needs the psycopg driver named.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


_url = database_url()
engine = create_engine(
    _url,
    pool_pre_ping=True,  # reconnect if the database paused while idle
    pool_recycle=300,
    connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    created_at: Mapped[date] = mapped_column(Date, default=date.today)
    policies: Mapped[list["Policy"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="Policy.end_date"
    )


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    policy_number: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(100))
    insurer: Mapped[str] = mapped_column(String(100))
    premium: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    notes: Mapped[str] = mapped_column(String(1000), default="")
    client: Mapped[Client] = relationship(back_populates="policies")


def init_db():
    Base.metadata.create_all(engine)
