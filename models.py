"""SQLAlchemy tables.

SQLite by default (``data/copilot.db``). Set ``DATABASE_URL`` to a Postgres
connection string to run the same schema on Supabase; nothing else changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    rules: Mapped["RuleRow"] = relationship(back_populates="account", uselist=False, cascade="all, delete-orphan")
    positions: Mapped[list["PositionRow"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    journal: Mapped[list["JournalRow"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    closed_trades: Mapped[list["ClosedTradeRow"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class RuleRow(Base):
    __tablename__ = "rule_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    max_position_pct: Mapped[float] = mapped_column(Float, default=0.10)
    daily_loss_limit: Mapped[float] = mapped_column(Float, default=500.0)
    max_premium_at_risk: Mapped[float] = mapped_column(Float, default=750.0)
    max_margin_pct: Mapped[float] = mapped_column(Float, default=0.20)
    min_holding_days: Mapped[int] = mapped_column(Integer, default=3)
    loss_streak_trigger: Mapped[int] = mapped_column(Integer, default=3)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=30)
    plan_required: Mapped[bool] = mapped_column(Boolean, default=True)
    max_trades_per_day: Mapped[int] = mapped_column(Integer, default=8)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    account: Mapped[Account] = relationship(back_populates="rules")


class PositionRow(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    symbol: Mapped[str] = mapped_column(String(16))
    asset_type: Mapped[str] = mapped_column(String(8), default="stock")
    contract: Mapped[str] = mapped_column(String(64), default="")
    qty: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    stop_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_hold_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    template: Mapped[str] = mapped_column(String(40), default="discretionary")

    account: Mapped[Account] = relationship(back_populates="positions")


class JournalRow(Base):
    """One row per evaluated order, whether it was routed, held, or imported."""

    __tablename__ = "journal"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    symbol: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    asset_type: Mapped[str] = mapped_column(String(8), default="stock")
    contract: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(16), default="copilot")  # copilot | broker_import
    outcome: Mapped[str] = mapped_column(String(8))                    # PASS | REVIEW | BLOCK
    headline_rule: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    plan_template: Mapped[str] = mapped_column(String(40), default="discretionary")
    plan_stop_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    planned_risk: Mapped[float] = mapped_column(Float, default=0.0)
    routed: Mapped[bool] = mapped_column(Boolean, default=False)
    fill_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    broker: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    rule_break: Mapped[bool] = mapped_column(Boolean, default=False)   # a routed or imported fill that breached a rule

    account: Mapped[Account] = relationship(back_populates="journal")


class ClosedTradeRow(Base):
    __tablename__ = "closed_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    closed_at: Mapped[datetime] = mapped_column(DateTime)
    symbol: Mapped[str] = mapped_column(String(16))
    asset_type: Mapped[str] = mapped_column(String(8), default="stock")
    qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    realized_pnl: Mapped[float] = mapped_column(Float)

    account: Mapped[Account] = relationship(back_populates="closed_trades")
