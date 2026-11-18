import csv
import io
import os
import secrets
from calendar import month_name
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta

from flask import (
    Flask, abort, flash, redirect, render_template, request,
    Response, session, url_for
)
from sqlalchemy import extract, func
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from currency_service import currency_service, SUPPORTED_CURRENCIES
from models import Budget, Category, Setting, Transaction, db

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)


# -----------------------------------------------------------------------------
# CSRF PROTECTION & SECURITY HELPERS
# -----------------------------------------------------------------------------
def get_csrf_token():
    """Generate or retrieve a session CSRF token."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(24)
    return session['csrf_token']


@app.before_request
def csrf_protect():
    """Enforce CSRF token validation on all state-changing HTTP methods."""
    if app.config.get('TESTING') and not app.config.get('WTF_CSRF_ENABLED', True):
        return None
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
        session_token = session.get('csrf_token')
        if not session_token or not token or not secrets.compare_digest(session_token, token):
            app.logger.warning("CSRF validation failed for path: %s", request.path)
            flash('Security validation failed (invalid or expired CSRF token). Please try again.', 'error')
            return redirect(request.referrer or url_for('dashboard'))


# -----------------------------------------------------------------------------
# CURRENCY & SETTINGS HELPERS
# -----------------------------------------------------------------------------
def get_default_currency() -> str:
    """Retrieve the application's default currency setting."""
    try:
        curr = Setting.get('default_currency', 'USD')
        return curr if curr in SUPPORTED_CURRENCIES else 'USD'
    except Exception:
        return 'USD'


def is_live_rates_enabled() -> bool:
    """Check if live exchange rate fetching is enabled."""
    try:
        val = Setting.get('use_live_rates', 'true')
        return val.lower() in ('true', '1', 'yes')
    except Exception:
        return True


def get_active_currency() -> str:
    """
    Determine the active currency for the current session/request.
    Priority:
    1. Query parameter ?currency=XYZ (updates session)
    2. Session stored 'active_currency'
    3. Default application currency setting
    """
    param_curr = request.args.get('currency', '').strip().upper()
    if param_curr and param_curr in SUPPORTED_CURRENCIES:
        session['active_currency'] = param_curr
        return param_curr

    session_curr = session.get('active_currency')
    if session_curr and session_curr in SUPPORTED_CURRENCIES:
        return session_curr

    default_curr = get_default_currency()
    session['active_currency'] = default_curr
    return default_curr


@app.context_processor
def inject_globals():
    """Make common variables available to all templates."""
    today = date.today()
    active_curr = get_active_currency()
    active_symbol = currency_service.get_symbol(active_curr)
    default_curr = get_default_currency()

    return {
        'csrf_token': get_csrf_token(),
        'supported_currencies': SUPPORTED_CURRENCIES,
        'active_currency': active_curr,
        'active_currency_symbol': active_symbol,
        'default_currency': default_curr,
        'currency_symbol': active_symbol,  # Backwards compatibility
        'current_year': today.year,
        'current_month': today.month,
        'current_date_str': today.strftime('%Y-%m-%d'),
        'month_names': {i: month_name[i] for i in range(1, 13)},
        'rate_info': currency_service.get_rate_info()
    }


@app.template_filter('currency')
def currency_filter(value, curr_code=None):
    """
    Format numeric value or Decimal as currency.
    If curr_code is omitted, uses the active session currency.
    """
    if curr_code is None:
        curr_code = get_active_currency()
    return currency_service.format_currency(value, curr_code)


@app.template_filter('convert')
def convert_filter(amount, from_curr, to_curr=None):
    """Template filter to convert between currencies."""
    if to_curr is None:
        to_curr = get_active_currency()
    use_live = is_live_rates_enabled()
    converted = currency_service.convert(amount, from_curr, to_curr, use_live=use_live)
    return currency_service.format_currency(converted, to_curr)


@app.template_filter('format_date')
def date_filter(value, fmt='%b %d, %Y'):
    """Format date object or string."""
    if not value:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return value
    return value.strftime(fmt)


# -----------------------------------------------------------------------------
# DATABASE SEEDING & MIGRATION
# -----------------------------------------------------------------------------
DEFAULT_EXPENSE_CATEGORIES = [
    {'name': 'Food', 'icon': 'utensils', 'color': '#F97316'},
    {'name': 'Transportation', 'icon': 'car', 'color': '#3B82F6'},
    {'name': 'Shopping', 'icon': 'bag-shopping', 'color': '#EC4899'},
    {'name': 'Education', 'icon': 'graduation-cap', 'color': '#8B5CF6'},
    {'name': 'Healthcare', 'icon': 'heart-pulse', 'color': '#EF4444'},
    {'name': 'Entertainment', 'icon': 'film', 'color': '#F59E0B'},
    {'name': 'Bills', 'icon': 'file-invoice-dollar', 'color': '#6366F1'},
    {'name': 'Rent', 'icon': 'house', 'color': '#0EA5E9'},
    {'name': 'Travel', 'icon': 'plane', 'color': '#14B8A6'},
    {'name': 'Other', 'icon': 'ellipsis', 'color': '#64748B'},
]

DEFAULT_INCOME_CATEGORIES = [
    {'name': 'Salary', 'icon': 'briefcase', 'color': '#10B981'},
    {'name': 'Freelance', 'icon': 'laptop-code', 'color': '#06B6D4'},
    {'name': 'Investments', 'icon': 'chart-line', 'color': '#84CC16'},
    {'name': 'Gifts', 'icon': 'gift', 'color': '#D946EF'},
    {'name': 'Rental Income', 'icon': 'building-user', 'color': '#22C55E'},
    {'name': 'Other Income', 'icon': 'coins', 'color': '#14B8A6'},
]


def init_db():
    """Create tables and populate default categories and settings if none exist."""
    db.create_all()

    # Seed default categories
    if Category.query.count() == 0:
        for cat in DEFAULT_EXPENSE_CATEGORIES:
            db.session.add(Category(
                name=cat['name'],
                type='expense',
                icon=cat['icon'],
                color=cat['color'],
                is_default=True
            ))
        for cat in DEFAULT_INCOME_CATEGORIES:
            db.session.add(Category(
                name=cat['name'],
                type='income',
                icon=cat['icon'],
                color=cat['color'],
                is_default=True
            ))
        db.session.commit()
        app.logger.info("Initialized database with default categories.")

    # Safe Schema Migrations for existing databases
    migrate_db()


def migrate_db():
    """
    Safely inspect and apply schema migrations for existing databases without data loss:
    - Adds 'currency' column to transactions if missing
    - Adds 'currency' column to budgets if missing
    - Initializes default settings
    """
    try:
        with db.engine.connect() as conn:
            # Check transactions table
            res_tx = conn.exec_driver_sql("PRAGMA table_info(transactions)").fetchall()
            tx_cols = [r[1] for r in res_tx]
            if 'currency' not in tx_cols:
                conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN currency VARCHAR(3) DEFAULT 'USD'")
                conn.exec_driver_sql("UPDATE transactions SET currency = 'USD' WHERE currency IS NULL OR currency = ''")
                conn.commit()
                app.logger.info("Migrated transactions table: added currency column.")

            # Check budgets table
            res_bg = conn.exec_driver_sql("PRAGMA table_info(budgets)").fetchall()
            bg_cols = [r[1] for r in res_bg]
            if 'currency' not in bg_cols:
                conn.exec_driver_sql("ALTER TABLE budgets ADD COLUMN currency VARCHAR(3) DEFAULT 'USD'")
                conn.exec_driver_sql("UPDATE budgets SET currency = 'USD' WHERE currency IS NULL OR currency = ''")
                conn.commit()
                app.logger.info("Migrated budgets table: added currency column.")

        # Ensure default settings exist
        if not Setting.get('default_currency'):
            Setting.set('default_currency', 'USD')
        if not Setting.get('use_live_rates'):
            Setting.set('use_live_rates', 'true')

    except Exception as e:
        app.logger.error("Database migration check encountered an error: %s", str(e))


# -----------------------------------------------------------------------------
# APPLICATION ROUTES
# -----------------------------------------------------------------------------

@app.route('/')
def dashboard():
    """Modern Dashboard overview converting all combined totals to active currency."""
    active_curr = get_active_currency()
    use_live = is_live_rates_enabled()
    today = date.today()
    first_of_month = date(today.year, today.month, 1)
    if today.month == 12:
        next_month = date(today.year + 1, 1, 1)
    else:
        next_month = date(today.year, today.month + 1, 1)

    # Fetch all transactions to compute multi-currency totals using Decimal
    all_transactions = Transaction.query.all()

    total_income_dec = Decimal('0.00')
    total_expenses_dec = Decimal('0.00')
    monthly_income_dec = Decimal('0.00')
    monthly_expenses_dec = Decimal('0.00')

    # Category expense accumulation for current month
    cat_month_expenses = {}  # {category_id: Decimal}

    for tx in all_transactions:
        # Convert each transaction to dashboard active currency using Decimal
        tx_amt = Decimal(str(tx.amount))
        conv_amt = currency_service.convert(tx_amt, tx.currency, active_curr, use_live=use_live)

        if tx.type == 'income':
            total_income_dec += conv_amt
            if first_of_month <= tx.date < next_month:
                monthly_income_dec += conv_amt
        elif tx.type == 'expense':
            total_expenses_dec += conv_amt
            if first_of_month <= tx.date < next_month:
                monthly_expenses_dec += conv_amt
                cat_month_expenses[tx.category_id] = cat_month_expenses.get(tx.category_id, Decimal('0.00')) + conv_amt

    current_balance_dec = total_income_dec - total_expenses_dec
    monthly_balance_dec = monthly_income_dec - monthly_expenses_dec

    # Recent Transactions (latest 6)
    recent_transactions_raw = Transaction.query\
        .order_by(Transaction.date.desc(), Transaction.id.desc())\
        .limit(6).all()

    recent_transactions = []
    for tx in recent_transactions_raw:
        tx_amt = Decimal(str(tx.amount))
        converted = currency_service.convert(tx_amt, tx.currency, active_curr, use_live=use_live)
        recent_transactions.append({
            'tx': tx,
            'original_formatted': currency_service.format_currency(tx_amt, tx.currency),
            'converted_formatted': currency_service.format_currency(converted, active_curr),
            'needs_conversion': (tx.currency.upper() != active_curr.upper())
        })

    # Current Month Budget Overview
    total_budget_row = Budget.query.filter_by(
        category_id=None,
        year=today.year,
        month=today.month
    ).first()

    cat_budgets = Budget.query.filter(
        Budget.category_id.isnot(None),
        Budget.year == today.year,
        Budget.month == today.month
    ).all()

    effective_budget_dec = Decimal('0.00')
    if total_budget_row:
        effective_budget_dec = currency_service.convert(
            Decimal(str(total_budget_row.amount)),
            total_budget_row.currency,
            active_curr,
            use_live=use_live
        )
    else:
        for b in cat_budgets:
            effective_budget_dec += currency_service.convert(
                Decimal(str(b.amount)),
                b.currency,
                active_curr,
                use_live=use_live
            )

    budget_percent = 0.0
    if effective_budget_dec > Decimal('0.00'):
        budget_percent = float(min(round((monthly_expenses_dec / effective_budget_dec) * 100, 1), Decimal('100.0')))

    # Top spending categories this month
    top_categories = []
    if cat_month_expenses:
        sorted_cats = sorted(cat_month_expenses.items(), key=lambda item: item[1], reverse=True)[:5]
        for cat_id, total_spent in sorted_cats:
            cat_obj = db.session.get(Category, cat_id)
            if cat_obj:
                top_categories.append({
                    'name': cat_obj.name,
                    'color': cat_obj.color,
                    'icon': cat_obj.icon,
                    'total': total_spent
                })

    # 6-Month Income vs Expense Bar Chart Data (converted to active_curr)
    months_labels = []
    months_income = []
    months_expense = []

    for i in range(5, -1, -1):
        target_date = today - relativedelta(months=i)
        y, m = target_date.year, target_date.month
        start_d = date(y, m, 1)
        end_d = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)

        m_txs = [t for t in all_transactions if start_d <= t.date < end_d]
        m_inc = sum((currency_service.convert(Decimal(str(t.amount)), t.currency, active_curr, use_live=use_live) for t in m_txs if t.type == 'income'), Decimal('0.00'))
        m_exp = sum((currency_service.convert(Decimal(str(t.amount)), t.currency, active_curr, use_live=use_live) for t in m_txs if t.type == 'expense'), Decimal('0.00'))

        months_labels.append(target_date.strftime('%b %Y'))
        months_income.append(float(m_inc))
        months_expense.append(float(m_exp))

    return render_template(
        'index.html',
        total_income=total_income_dec,
        total_expenses=total_expenses_dec,
        current_balance=current_balance_dec,
        monthly_income=monthly_income_dec,
        monthly_expenses=monthly_expenses_dec,
        monthly_balance=monthly_balance_dec,
        recent_transactions=recent_transactions,
        effective_budget=effective_budget_dec,
        budget_percent=budget_percent,
        top_categories=top_categories,
        chart_data={
            'labels': months_labels,
            'income': months_income,
            'expense': months_expense
        }
    )


@app.route('/transactions')
def transactions_list():
    """Transaction management page with currency filter, search, date range, and pagination."""
    active_curr = get_active_currency()
    use_live = is_live_rates_enabled()
    query = Transaction.query

    # Filters
    t_type = request.args.get('type', '').strip().lower()
    category_id = request.args.get('category_id', '').strip()
    selected_curr = request.args.get('currency', '').strip().upper()
    search = request.args.get('search', '').strip()
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    sort_by = request.args.get('sort', 'date_desc').strip()

    if t_type in ('income', 'expense'):
        query = query.filter(Transaction.type == t_type)

    if category_id.isdigit():
        query = query.filter(Transaction.category_id == int(category_id))

    if selected_curr and selected_curr in SUPPORTED_CURRENCIES:
        query = query.filter(Transaction.currency == selected_curr)

    if search:
        query = query.filter(
            (Transaction.description.ilike(f'%{search}%')) |
            (Transaction.category.has(Category.name.ilike(f'%{search}%')))
        )

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(Transaction.date >= start_date)
        except ValueError:
            flash('Invalid start date filter format (use YYYY-MM-DD).', 'warning')

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(Transaction.date <= end_date)
        except ValueError:
            flash('Invalid end date filter format (use YYYY-MM-DD).', 'warning')

    # Sorting
    if sort_by == 'date_asc':
        query = query.order_by(Transaction.date.asc(), Transaction.id.asc())
    elif sort_by == 'amount_desc':
        query = query.order_by(Transaction.amount.desc())
    elif sort_by == 'amount_asc':
        query = query.order_by(Transaction.amount.asc())
    else:  # date_desc default
        query = query.order_by(Transaction.date.desc(), Transaction.id.desc())

    # Calculate filtered summary metrics converting each transaction to active_curr
    all_filtered = query.all()
    filtered_income_dec = Decimal('0.00')
    filtered_expense_dec = Decimal('0.00')

    for t in all_filtered:
        amt_dec = Decimal(str(t.amount))
        conv_amt = currency_service.convert(amt_dec, t.currency, active_curr, use_live=use_live)
        if t.type == 'income':
            filtered_income_dec += conv_amt
        elif t.type == 'expense':
            filtered_expense_dec += conv_amt

    filtered_net_dec = filtered_income_dec - filtered_expense_dec
    filtered_count = len(all_filtered)

    # Simple pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    total_pages = max(1, (filtered_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_transactions_raw = all_filtered[start_idx:end_idx]

    page_transactions = []
    for tx in page_transactions_raw:
        tx_amt = Decimal(str(tx.amount))
        converted = currency_service.convert(tx_amt, tx.currency, active_curr, use_live=use_live)
        page_transactions.append({
            'tx': tx,
            'original_formatted': currency_service.format_currency(tx_amt, tx.currency),
            'converted_formatted': currency_service.format_currency(converted, active_curr),
            'needs_conversion': (tx.currency.upper() != active_curr.upper())
        })

    categories = Category.query.order_by(Category.name.asc()).all()

    return render_template(
        'transactions.html',
        transactions=page_transactions,
        categories=categories,
        filtered_count=filtered_count,
        filtered_income=filtered_income_dec,
        filtered_expense=filtered_expense_dec,
        filtered_net=filtered_net_dec,
        current_page=page,
        total_pages=total_pages,
        selected_type=t_type,
        selected_category=category_id,
        selected_currency=selected_curr,
        search_query=search,
        start_date=start_date_str,
        end_date=end_date_str,
        selected_sort=sort_by
    )


@app.route('/transactions/add', methods=['GET', 'POST'])
def add_transaction():
    """Add a new income or expense transaction with currency selection."""
    active_curr = get_active_currency()

    if request.method == 'POST':
        t_type = request.form.get('type', '').strip().lower()
        amount_raw = request.form.get('amount', '').strip()
        currency_code = request.form.get('currency', active_curr).strip().upper()
        category_id_raw = request.form.get('category_id', '').strip()
        description = request.form.get('description', '').strip()
        date_raw = request.form.get('date', '').strip()

        errors = []
        if t_type not in ('income', 'expense'):
            errors.append('Transaction type must be either Income or Expense.')

        if currency_code not in SUPPORTED_CURRENCIES:
            errors.append(f"Invalid currency '{currency_code}'. Supported: {', '.join(SUPPORTED_CURRENCIES.keys())}")

        try:
            amount = Decimal(amount_raw)
            if amount <= Decimal('0.00'):
                errors.append('Amount must be greater than zero.')
            elif amount.as_tuple().exponent < -2:
                errors.append('Amount cannot have more than 2 decimal places.')
        except Exception:
            errors.append('Please provide a valid numeric amount.')

        if not category_id_raw.isdigit():
            errors.append('Please select a valid category.')
        else:
            category = db.session.get(Category, int(category_id_raw))
            if not category:
                errors.append('Selected category does not exist.')
            elif category.type != 'both' and category.type != t_type:
                errors.append(f"Category '{category.name}' cannot be used for {t_type} transactions.")

        try:
            t_date = datetime.strptime(date_raw, '%Y-%m-%d').date() if date_raw else date.today()
        except ValueError:
            errors.append('Invalid date format. Please use YYYY-MM-DD.')

        if errors:
            for err in errors:
                flash(err, 'error')
            categories = Category.query.order_by(Category.name.asc()).all()
            return render_template(
                'add_transaction.html',
                categories=categories,
                form_data=request.form,
                preselected_type=t_type or 'expense',
                preselected_currency=currency_code
            ), 400

        try:
            new_tx = Transaction(
                type=t_type,
                amount=float(amount),
                currency=currency_code,
                category_id=int(category_id_raw),
                description=description[:255],
                date=t_date
            )
            db.session.add(new_tx)
            db.session.commit()
            formatted_saved = currency_service.format_currency(amount, currency_code)
            flash(f"Successfully recorded {t_type.capitalize()} of {formatted_saved} ({currency_code})!", 'success')
            return redirect(url_for('transactions_list'))
        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.error("Database error saving transaction: %s", str(e))
            flash('A database error occurred while saving the transaction. Please try again.', 'error')

    preselected_type = request.args.get('type', 'expense').strip().lower()
    if preselected_type not in ('income', 'expense'):
        preselected_type = 'expense'

    categories = Category.query.order_by(Category.name.asc()).all()
    return render_template(
        'add_transaction.html',
        categories=categories,
        form_data={'date': date.today().strftime('%Y-%m-%d'), 'currency': active_curr},
        preselected_type=preselected_type,
        preselected_currency=active_curr
    )


@app.route('/transactions/<int:tx_id>/edit', methods=['GET', 'POST'])
def edit_transaction(tx_id):
    """Edit an existing transaction with currency support."""
    tx = db.get_or_404(Transaction, tx_id)

    if request.method == 'POST':
        t_type = request.form.get('type', '').strip().lower()
        amount_raw = request.form.get('amount', '').strip()
        currency_code = request.form.get('currency', tx.currency).strip().upper()
        category_id_raw = request.form.get('category_id', '').strip()
        description = request.form.get('description', '').strip()
        date_raw = request.form.get('date', '').strip()

        errors = []
        if t_type not in ('income', 'expense'):
            errors.append('Transaction type must be either Income or Expense.')

        if currency_code not in SUPPORTED_CURRENCIES:
            errors.append(f"Invalid currency '{currency_code}'. Supported: {', '.join(SUPPORTED_CURRENCIES.keys())}")

        try:
            amount = Decimal(amount_raw)
            if amount <= Decimal('0.00'):
                errors.append('Amount must be greater than zero.')
        except Exception:
            errors.append('Please provide a valid numeric amount.')

        if not category_id_raw.isdigit():
            errors.append('Please select a valid category.')
        else:
            category = db.session.get(Category, int(category_id_raw))
            if not category:
                errors.append('Selected category does not exist.')
            elif category.type != 'both' and category.type != t_type:
                errors.append(f"Category '{category.name}' cannot be used for {t_type} transactions.")

        try:
            t_date = datetime.strptime(date_raw, '%Y-%m-%d').date()
        except ValueError:
            errors.append('Invalid date format. Please use YYYY-MM-DD.')

        if errors:
            for err in errors:
                flash(err, 'error')
            categories = Category.query.order_by(Category.name.asc()).all()
            return render_template(
                'add_transaction.html',
                categories=categories,
                form_data=request.form,
                is_edit=True,
                transaction=tx,
                preselected_type=t_type,
                preselected_currency=currency_code
            ), 400

        try:
            tx.type = t_type
            tx.amount = float(amount)
            tx.currency = currency_code
            tx.category_id = int(category_id_raw)
            tx.description = description[:255]
            tx.date = t_date
            db.session.commit()
            flash('Transaction updated successfully.', 'success')
            return redirect(url_for('transactions_list'))
        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.error("Database error updating transaction: %s", str(e))
            flash('Database error while updating the transaction.', 'error')

    categories = Category.query.order_by(Category.name.asc()).all()
    form_data = {
        'type': tx.type,
        'amount': f"{tx.amount:.2f}",
        'currency': tx.currency,
        'category_id': str(tx.category_id),
        'description': tx.description or '',
        'date': tx.date.strftime('%Y-%m-%d')
    }
    return render_template(
        'add_transaction.html',
        categories=categories,
        form_data=form_data,
        is_edit=True,
        transaction=tx,
        preselected_type=tx.type,
        preselected_currency=tx.currency
    )


@app.route('/transactions/<int:tx_id>/delete', methods=['POST'])
def delete_transaction(tx_id):
    """Delete a transaction with confirmation."""
    tx = db.get_or_404(Transaction, tx_id)
    try:
        amount_formatted = currency_service.format_currency(tx.amount, tx.currency)
        tx_type = tx.type
        db.session.delete(tx)
        db.session.commit()
        flash(f"Deleted {tx_type} transaction of {amount_formatted} ({tx.currency}).", 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        app.logger.error("Database error deleting transaction: %s", str(e))
        flash('Could not delete transaction due to database error.', 'error')

    return redirect(request.referrer or url_for('transactions_list'))


@app.route('/budgets', methods=['GET', 'POST'])
def budgets():
    """Budget Management page with multi-currency support and accurate conversion."""
    active_curr = get_active_currency()
    use_live = is_live_rates_enabled()
    today = date.today()

    # Handle Budget Add or Update
    if request.method == 'POST':
        category_id_raw = request.form.get('category_id', '').strip()
        currency_code = request.form.get('currency', active_curr).strip().upper()
        year_raw = request.form.get('year', str(today.year)).strip()
        month_raw = request.form.get('month', str(today.month)).strip()
        amount_raw = request.form.get('amount', '').strip()

        errors = []
        if currency_code not in SUPPORTED_CURRENCIES:
            currency_code = active_curr

        try:
            year = int(year_raw)
            month = int(month_raw)
            if not (1 <= month <= 12) or not (2000 <= year <= 2100):
                errors.append('Invalid month or year selected.')
        except ValueError:
            errors.append('Month and year must be integers.')

        try:
            amount = Decimal(amount_raw)
            if amount <= Decimal('0.00'):
                errors.append('Budget amount must be strictly greater than zero.')
        except Exception:
            errors.append('Please provide a valid budget amount.')

        category_id = None
        cat = None
        if category_id_raw and category_id_raw.isdigit():
            category_id = int(category_id_raw)
            cat = db.session.get(Category, category_id)
            if not cat or cat.type == 'income':
                errors.append('Budget can only be assigned to expense categories or total.')

        if errors:
            for err in errors:
                flash(err, 'error')
        else:
            try:
                existing_budget = Budget.query.filter_by(
                    category_id=category_id,
                    year=year,
                    month=month
                ).first()

                cat_title = cat.name if cat else 'Total Monthly'
                formatted_amt = currency_service.format_currency(amount, currency_code)

                if existing_budget:
                    existing_budget.amount = float(amount)
                    existing_budget.currency = currency_code
                    flash(f"Updated budget for {cat_title} to {formatted_amt} ({currency_code})!", 'success')
                else:
                    new_budget = Budget(
                        category_id=category_id,
                        year=year,
                        month=month,
                        amount=float(amount),
                        currency=currency_code
                    )
                    db.session.add(new_budget)
                    flash(f"Set new budget for {cat_title} ({month_name[month]} {year}) of {formatted_amt} ({currency_code})!", 'success')

                db.session.commit()
                return redirect(url_for('budgets', year=year, month=month))
            except SQLAlchemyError as e:
                db.session.rollback()
                app.logger.error("Database error saving budget: %s", str(e))
                flash('Database error while saving the budget.', 'error')

    # Selected month & year for display
    try:
        selected_year = int(request.args.get('year', today.year))
        selected_month = int(request.args.get('month', today.month))
        if not (1 <= selected_month <= 12):
            selected_month = today.month
    except (ValueError, TypeError):
        selected_year = today.year
        selected_month = today.month

    # Date range for target month
    start_d = date(selected_year, selected_month, 1)
    if selected_month == 12:
        end_d = date(selected_year + 1, 1, 1)
    else:
        end_d = date(selected_year, selected_month + 1, 1)

    # Fetch expenses for target month to compute multi-currency spent amounts
    month_expenses = Transaction.query.filter(
        Transaction.type == 'expense',
        Transaction.date >= start_d,
        Transaction.date < end_d
    ).all()

    # 1. Fetch overall monthly budget if set
    overall_budget_obj = Budget.query.filter_by(
        category_id=None,
        year=selected_year,
        month=selected_month
    ).first()

    # 2. Fetch category budgets
    cat_budgets = Budget.query.filter(
        Budget.category_id.isnot(None),
        Budget.year == selected_year,
        Budget.month == selected_month
    ).all()

    # Build category budget items with accurate currency conversion
    budget_items = []
    total_budgeted_in_active_curr = Decimal('0.00')

    for b in cat_budgets:
        b_amount_dec = Decimal(str(b.amount))
        # Sum spent converting each expense to the budget's currency
        spent_in_b_curr = Decimal('0.00')
        for tx in month_expenses:
            if tx.category_id == b.category_id:
                amt_dec = Decimal(str(tx.amount))
                spent_in_b_curr += currency_service.convert(amt_dec, tx.currency, b.currency, use_live=use_live)

        remaining_in_b_curr = b_amount_dec - spent_in_b_curr
        percent = float(round((spent_in_b_curr / b_amount_dec * 100), 1)) if b_amount_dec > Decimal('0.00') else 0.0

        status = 'safe'
        if percent >= 100:
            status = 'exceeded'
        elif percent >= 80:
            status = 'warning'

        total_budgeted_in_active_curr += currency_service.convert(b_amount_dec, b.currency, active_curr, use_live=use_live)

        budget_items.append({
            'budget': b,
            'category': b.category,
            'currency': b.currency,
            'currency_symbol': currency_service.get_symbol(b.currency),
            'amount': b_amount_dec,
            'spent': spent_in_b_curr,
            'remaining': remaining_in_b_curr,
            'percent': percent,
            'status': status
        })

    # Overall Monthly Budget Summary
    overall_budget_currency = overall_budget_obj.currency if overall_budget_obj else active_curr
    if overall_budget_obj:
        overall_budget_amount_dec = Decimal(str(overall_budget_obj.amount))
    else:
        overall_budget_amount_dec = total_budgeted_in_active_curr

    # Sum total month expenses converted to the overall budget currency
    overall_spent_dec = Decimal('0.00')
    for tx in month_expenses:
        amt_dec = Decimal(str(tx.amount))
        overall_spent_dec += currency_service.convert(amt_dec, tx.currency, overall_budget_currency, use_live=use_live)

    overall_remaining_dec = overall_budget_amount_dec - overall_spent_dec if overall_budget_amount_dec > Decimal('0.00') else Decimal('0.00')
    overall_percent = float(round((overall_spent_dec / overall_budget_amount_dec * 100), 1)) if overall_budget_amount_dec > Decimal('0.00') else 0.0

    overall_status = 'safe'
    if overall_budget_amount_dec > Decimal('0.00'):
        if overall_percent >= 100:
            overall_status = 'exceeded'
        elif overall_percent >= 80:
            overall_status = 'warning'

    expense_categories = Category.query.filter(Category.type.in_(['expense', 'both']))\
        .order_by(Category.name.asc()).all()

    return render_template(
        'budgets.html',
        selected_year=selected_year,
        selected_month=selected_month,
        selected_month_name=month_name[selected_month],
        overall_budget_obj=overall_budget_obj,
        overall_budget_currency=overall_budget_currency,
        overall_budget_symbol=currency_service.get_symbol(overall_budget_currency),
        overall_budget_amount=overall_budget_amount_dec,
        overall_spent=overall_spent_dec,
        overall_remaining=overall_remaining_dec,
        overall_percent=overall_percent,
        overall_status=overall_status,
        budget_items=budget_items,
        expense_categories=expense_categories
    )


@app.route('/budgets/<int:b_id>/delete', methods=['POST'])
def delete_budget(b_id):
    """Delete a budget entry."""
    budget = db.get_or_404(Budget, b_id)
    year, month = budget.year, budget.month
    cat_title = budget.category.name if budget.category else 'Total Monthly'

    try:
        db.session.delete(budget)
        db.session.commit()
        flash(f"Removed budget for {cat_title}.", 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        app.logger.error("Database error deleting budget: %s", str(e))
        flash('Could not delete budget due to a database error.', 'error')

    return redirect(url_for('budgets', year=year, month=month))


@app.route('/analytics')
def analytics():
    """Interactive Analytics and Reports converting multi-currency transactions to active currency."""
    active_curr = get_active_currency()
    use_live = is_live_rates_enabled()
    today = date.today()
    period = request.args.get('period', 'this_month')
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()

    # Determine date range based on period
    if period == 'this_month':
        start_date = date(today.year, today.month, 1)
        end_date = today
    elif period == 'last_month':
        last_m = today - relativedelta(months=1)
        start_date = date(last_m.year, last_m.month, 1)
        end_date = date(today.year, today.month, 1) - timedelta(days=1)
    elif period == 'last_3_months':
        start_date = (today - relativedelta(months=2)).replace(day=1)
        end_date = today
    elif period == 'this_year':
        start_date = date(today.year, 1, 1)
        end_date = today
    elif period == 'all_time':
        earliest_tx = db.session.query(func.min(Transaction.date)).scalar()
        start_date = earliest_tx or (today - relativedelta(months=12))
        end_date = today
    elif period == 'custom':
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else (today - relativedelta(months=1))
        except ValueError:
            start_date = today - relativedelta(months=1)
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
        except ValueError:
            end_date = today
    else:
        period = 'this_month'
        start_date = date(today.year, today.month, 1)
        end_date = today

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    # Query period transactions
    period_txs = Transaction.query.filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).all()

    total_income_dec = Decimal('0.00')
    total_expenses_dec = Decimal('0.00')
    cat_period_expenses = {}  # {category_id: {'total': Decimal, 'count': int}}

    for tx in period_txs:
        amt_dec = Decimal(str(tx.amount))
        conv_amt = currency_service.convert(amt_dec, tx.currency, active_curr, use_live=use_live)

        if tx.type == 'income':
            total_income_dec += conv_amt
        elif tx.type == 'expense':
            total_expenses_dec += conv_amt
            if tx.category_id not in cat_period_expenses:
                cat_period_expenses[tx.category_id] = {'total': Decimal('0.00'), 'count': 0}
            cat_period_expenses[tx.category_id]['total'] += conv_amt
            cat_period_expenses[tx.category_id]['count'] += 1

    total_savings_dec = total_income_dec - total_expenses_dec
    savings_rate = 0.0
    if total_income_dec > Decimal('0.00'):
        savings_rate = float(round((total_savings_dec / total_income_dec * 100), 1))
    if savings_rate < 0:
        savings_rate = 0.0

    days_in_period = max(1, (end_date - start_date).days + 1)
    daily_average_expense_dec = (total_expenses_dec / Decimal(str(days_in_period))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Highest spending category
    highest_cat = None
    category_breakdown = []
    pie_labels = []
    pie_data = []
    pie_colors = []

    if cat_period_expenses:
        sorted_cat_list = sorted(cat_period_expenses.items(), key=lambda x: x[1]['total'], reverse=True)
        top_cat_id, top_cat_info = sorted_cat_list[0]
        top_cat_obj = db.session.get(Category, top_cat_id)
        if top_cat_obj:
            pct = float(round((top_cat_info['total'] / total_expenses_dec * 100), 1)) if total_expenses_dec > Decimal('0.00') else 0.0
            highest_cat = {
                'name': top_cat_obj.name,
                'color': top_cat_obj.color,
                'icon': top_cat_obj.icon,
                'total': top_cat_info['total'],
                'percent': pct
            }

        for cat_id, info in sorted_cat_list:
            cat_obj = db.session.get(Category, cat_id)
            if cat_obj:
                share = float(round((info['total'] / total_expenses_dec * 100), 1)) if total_expenses_dec > Decimal('0.00') else 0.0
                category_breakdown.append({
                    'name': cat_obj.name,
                    'color': cat_obj.color,
                    'icon': cat_obj.icon,
                    'total': info['total'],
                    'count': info['count'],
                    'share': share
                })
                pie_labels.append(cat_obj.name)
                pie_data.append(float(info['total']))
                pie_colors.append(cat_obj.color)

    # 12-Month Spending & Income Trend Line & Bar Data (converted to active_curr)
    all_txs = Transaction.query.all()
    trend_labels = []
    trend_income = []
    trend_expense = []

    for i in range(11, -1, -1):
        target_month_date = today - relativedelta(months=i)
        y, m = target_month_date.year, target_month_date.month
        m_start = date(y, m, 1)
        m_end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)

        month_tx_subset = [t for t in all_txs if m_start <= t.date < m_end]
        m_inc = sum((currency_service.convert(Decimal(str(t.amount)), t.currency, active_curr, use_live=use_live) for t in month_tx_subset if t.type == 'income'), Decimal('0.00'))
        m_exp = sum((currency_service.convert(Decimal(str(t.amount)), t.currency, active_curr, use_live=use_live) for t in month_tx_subset if t.type == 'expense'), Decimal('0.00'))

        trend_labels.append(target_month_date.strftime('%b %y'))
        trend_income.append(float(m_inc))
        trend_expense.append(float(m_exp))

    return render_template(
        'analytics.html',
        period=period,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        total_income=total_income_dec,
        total_expenses=total_expenses_dec,
        total_savings=total_savings_dec,
        savings_rate=savings_rate,
        daily_average_expense=daily_average_expense_dec,
        highest_cat=highest_cat,
        category_breakdown=category_breakdown,
        pie_chart={
            'labels': pie_labels,
            'data': pie_data,
            'colors': pie_colors
        },
        trend_chart={
            'labels': trend_labels,
            'income': trend_income,
            'expense': trend_expense
        }
    )


@app.route('/export/csv')
def export_csv():
    """Export transactions as CSV preserving original currency and amount."""
    query = Transaction.query

    t_type = request.args.get('type', '').strip().lower()
    category_id = request.args.get('category_id', '').strip()
    selected_curr = request.args.get('currency', '').strip().upper()
    search = request.args.get('search', '').strip()
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()

    if t_type in ('income', 'expense'):
        query = query.filter(Transaction.type == t_type)

    if category_id.isdigit():
        query = query.filter(Transaction.category_id == int(category_id))

    if selected_curr and selected_curr in SUPPORTED_CURRENCIES:
        query = query.filter(Transaction.currency == selected_curr)

    if search:
        query = query.filter(
            (Transaction.description.ilike(f'%{search}%')) |
            (Transaction.category.has(Category.name.ilike(f'%{search}%')))
        )

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(Transaction.date >= start_date)
        except ValueError:
            pass

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            query = query.filter(Transaction.date <= end_date)
        except ValueError:
            pass

    transactions = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()

    # Generate CSV in memory
    si = io.StringIO()
    writer = csv.writer(si)
    # Header including Currency
    writer.writerow(['Transaction ID', 'Date', 'Type', 'Category', 'Original Amount', 'Currency', 'Description', 'Created At'])

    for tx in transactions:
        writer.writerow([
            tx.id,
            tx.date.strftime('%Y-%m-%d'),
            tx.type.capitalize(),
            tx.category.name if tx.category else 'Uncategorized',
            f"{tx.amount:.2f}",
            tx.currency,
            tx.description or '',
            tx.created_at.strftime('%Y-%m-%d %H:%M:%S') if tx.created_at else ''
        ])

    output = si.getvalue()
    filename = f"transactions_{date.today().strftime('%Y%m%d')}.csv"

    return Response(
        output,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


# -----------------------------------------------------------------------------
# APPLICATION SETTINGS & CURRENCY SWITCHING
# -----------------------------------------------------------------------------

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Application Settings view for Default Currency and Live Rates configuration."""
    if request.method == 'POST':
        default_curr = request.form.get('default_currency', '').strip().upper()
        use_live_raw = request.form.get('use_live_rates') == 'on'

        if default_curr in SUPPORTED_CURRENCIES:
            Setting.set('default_currency', default_curr)
            session['active_currency'] = default_curr
            flash(f"Default dashboard currency updated to {default_curr} ({SUPPORTED_CURRENCIES[default_curr]['symbol']}).", 'success')
        else:
            flash('Invalid currency selected.', 'error')

        Setting.set('use_live_rates', 'true' if use_live_raw else 'false')
        return redirect(url_for('settings'))

    current_default = get_default_currency()
    live_rates_on = is_live_rates_enabled()
    rates_info = currency_service.get_rate_info()

    return render_template(
        'settings.html',
        current_default=current_default,
        live_rates_on=live_rates_on,
        rates_info=rates_info,
        supported_currencies=SUPPORTED_CURRENCIES
    )


@app.route('/settings/refresh-rates', methods=['POST'])
def refresh_rates():
    """Manually trigger fresh live exchange rate synchronization."""
    currency_service.get_rates(force_refresh=True, use_live=True)
    info = currency_service.get_rate_info()
    flash(f"Exchange rates refreshed successfully from {info['source']}!", 'success')
    return redirect(request.referrer or url_for('settings'))


@app.route('/set-currency/<curr_code>')
def set_active_currency(curr_code):
    """Quick currency switcher for topbar / header."""
    code = (curr_code or '').strip().upper()
    if code in SUPPORTED_CURRENCIES:
        session['active_currency'] = code
        flash(f"Switched dashboard view to {code} ({SUPPORTED_CURRENCIES[code]['symbol']}).", 'info')

    next_url = request.args.get('next')
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/categories/add', methods=['POST'])
def add_category():
    """Create a new custom category."""
    name = request.form.get('name', '').strip()
    c_type = request.form.get('type', 'expense').strip().lower()
    color = request.form.get('color', '#6366F1').strip()
    icon = request.form.get('icon', 'tag').strip()

    if not name:
        flash('Category name cannot be empty.', 'error')
        return redirect(request.referrer or url_for('dashboard'))

    if c_type not in ('expense', 'income', 'both'):
        c_type = 'expense'

    existing = Category.query.filter(
        func.lower(Category.name) == name.lower(),
        Category.type == c_type
    ).first()

    if existing:
        flash(f"Category '{name}' already exists for {c_type}.", 'warning')
        return redirect(request.referrer or url_for('dashboard'))

    try:
        new_cat = Category(
            name=name,
            type=c_type,
            color=color or '#6366F1',
            icon=icon or 'tag',
            is_default=False
        )
        db.session.add(new_cat)
        db.session.commit()
        flash(f"Custom category '{name}' created successfully!", 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        app.logger.error("Database error creating category: %s", str(e))
        flash('Database error creating custom category.', 'error')

    return redirect(request.referrer or url_for('dashboard'))


@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 Not Found."""
    return render_template('base.html', not_found=True), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server Error."""
    db.session.rollback()
    return render_template('base.html', server_error=True), 500


# Automatically initialize DB tables & migrations on startup
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='127.0.0.1', port=port, debug=True)
