from datetime import datetime, date
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint
from currency_service import currency_service

db = SQLAlchemy()

class Setting(db.Model):
    """Application and user settings storage."""
    __tablename__ = 'settings'

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f'<Setting {self.key}={self.value}>'

    @classmethod
    def get(cls, key: str, default: str = None) -> str:
        """Fetch setting value by key with a fallback default."""
        row = db.session.get(cls, key)
        return row.value if row else default

    @classmethod
    def set(cls, key: str, value: str):
        """Insert or update a setting value."""
        row = db.session.get(cls, key)
        if not row:
            row = cls(key=key, value=str(value))
            db.session.add(row)
        else:
            row.value = str(value)
        db.session.commit()


class Category(db.Model):
    """Category model for classifying income and expense transactions."""
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'expense', 'income', or 'both'
    icon = db.Column(db.String(50), nullable=False, default='tag')
    color = db.Column(db.String(20), nullable=False, default='#6366F1')
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    transactions = db.relationship('Transaction', backref='category', lazy=True, cascade='all, delete-orphan')
    budgets = db.relationship('Budget', backref='category', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        UniqueConstraint('name', 'type', name='uq_category_name_type'),
    )

    def __repr__(self):
        return f'<Category {self.name} ({self.type})>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'icon': self.icon,
            'color': self.color,
            'is_default': self.is_default
        }


class Transaction(db.Model):
    """Transaction model storing income and expense records."""
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    type = db.Column(db.String(20), nullable=False)  # 'income' or 'expense'
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    description = db.Column(db.String(255), nullable=True, default='')
    date = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint('amount > 0', name='check_amount_positive'),
        CheckConstraint("type IN ('income', 'expense')", name='check_transaction_type'),
    )

    def __repr__(self):
        return f'<Transaction #{self.id} {self.type.upper()}: {self.currency} {self.amount} ({self.date})>'

    @property
    def formatted_amount(self):
        sign = '+' if self.type == 'income' else '-'
        formatted = currency_service.format_currency(self.amount, self.currency)
        return f"{sign}{formatted}"

    @property
    def currency_symbol(self):
        return currency_service.get_symbol(self.currency)

    @property
    def amount_decimal(self) -> Decimal:
        return Decimal(str(self.amount))

    def to_dict(self):
        return {
            'id': self.id,
            'amount': self.amount,
            'currency': self.currency,
            'currency_symbol': self.currency_symbol,
            'type': self.type,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else 'Uncategorized',
            'category_color': self.category.color if self.category else '#64748B',
            'category_icon': self.category.icon if self.category else 'tag',
            'description': self.description or '',
            'date': self.date.strftime('%Y-%m-%d') if self.date else '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


class Budget(db.Model):
    """Budget model for monthly budget tracking across categories or overall."""
    __tablename__ = 'budgets'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=True)  # NULL represents overall total monthly budget
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1 - 12
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint('amount > 0', name='check_budget_amount_positive'),
        CheckConstraint('month >= 1 AND month <= 12', name='check_budget_valid_month'),
        UniqueConstraint('category_id', 'year', 'month', name='uq_budget_category_month_year'),
    )

    def __repr__(self):
        cat = self.category.name if self.category else 'Total'
        return f'<Budget {cat} {self.year}-{self.month:02d}: {self.currency} {self.amount}>'

    @property
    def currency_symbol(self):
        return currency_service.get_symbol(self.currency)

    @property
    def amount_decimal(self) -> Decimal:
        return Decimal(str(self.amount))

    def to_dict(self):
        return {
            'id': self.id,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else 'Overall Monthly Budget',
            'year': self.year,
            'month': self.month,
            'amount': self.amount,
            'currency': self.currency,
            'currency_symbol': self.currency_symbol,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }
