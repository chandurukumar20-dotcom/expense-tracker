import os
import unittest
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from app import app, db, init_db
from currency_service import currency_service, SUPPORTED_CURRENCIES
from models import Budget, Category, Setting, Transaction


class ExpenseTrackerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test_expense_tracker.db'

        with app.app_context():
            db.create_all()
            init_db()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        test_db = os.path.join(app.root_path, 'test_expense_tracker.db')
        if os.path.exists(test_db):
            try:
                os.remove(test_db)
            except OSError:
                pass

    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        with self.app.app_context():
            Transaction.query.delete()
            Budget.query.delete()
            # Reset default setting
            Setting.set('default_currency', 'USD')
            Setting.set('use_live_rates', 'true')
            db.session.commit()

        # Reset session
        with self.client.session_transaction() as sess:
            sess['active_currency'] = 'USD'

    def test_default_categories_seeded(self):
        """Verify default expense and income categories are created."""
        with self.app.app_context():
            categories = Category.query.all()
            self.assertGreaterEqual(len(categories), 16)
            expense_cats = [c.name for c in categories if c.type == 'expense']
            self.assertIn('Food', expense_cats)
            self.assertIn('Transportation', expense_cats)
            self.assertIn('Rent', expense_cats)

            income_cats = [c.name for c in categories if c.type == 'income']
            self.assertIn('Salary', income_cats)
            self.assertIn('Freelance', income_cats)

    def test_dashboard_route_loads(self):
        """Verify dashboard loads with HTTP 200."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Financial Dashboard', response.data)
        self.assertIn(b'Current Balance', response.data)

    def test_add_income_with_currency(self):
        """Test recording an income transaction in INR."""
        with self.app.app_context():
            salary_cat = Category.query.filter_by(name='Salary', type='income').first()
            salary_cat_id = salary_cat.id

        response = self.client.post('/transactions/add', data={
            'type': 'income',
            'amount': '75000.00',
            'currency': 'INR',
            'category_id': str(salary_cat_id),
            'description': 'Software Engineer Salary',
            'date': date.today().strftime('%Y-%m-%d')
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'75,000.00', response.data)

        with self.app.app_context():
            tx = Transaction.query.first()
            self.assertIsNotNone(tx)
            self.assertEqual(tx.amount, 75000.00)
            self.assertEqual(tx.currency, 'INR')
            self.assertEqual(tx.type, 'income')
            self.assertEqual(tx.currency_symbol, '\u20b9')

    def test_add_expense_with_currency(self):
        """Test recording an expense transaction in EUR."""
        with self.app.app_context():
            food_cat = Category.query.filter_by(name='Food', type='expense').first()
            food_cat_id = food_cat.id

        response = self.client.post('/transactions/add', data={
            'type': 'expense',
            'amount': '45.50',
            'currency': 'EUR',
            'category_id': str(food_cat_id),
            'description': 'Bistro Lunch',
            'date': date.today().strftime('%Y-%m-%d')
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'45.50', response.data)

        with self.app.app_context():
            tx = Transaction.query.filter_by(type='expense').first()
            self.assertIsNotNone(tx)
            self.assertEqual(tx.amount, 45.50)
            self.assertEqual(tx.currency, 'EUR')
            self.assertEqual(tx.currency_symbol, '\u20ac')

    def test_multi_currency_totals_converted_properly(self):
        """
        Verify that different currencies are NOT added directly,
        but converted to dashboard active currency using Decimal arithmetic.
        """
        today = date.today()
        with self.app.app_context():
            salary_cat = Category.query.filter_by(name='Salary').first()
            food_cat = Category.query.filter_by(name='Food').first()

            # Income: 1000 USD
            db.session.add(Transaction(type='income', amount=1000.0, currency='USD', category_id=salary_cat.id, date=today))
            # Expense: 100 EUR
            db.session.add(Transaction(type='expense', amount=100.0, currency='EUR', category_id=food_cat.id, date=today))
            db.session.commit()

        # View in USD
        res_usd = self.client.get('/?currency=USD')
        self.assertEqual(res_usd.status_code, 200)

        # Expected EUR -> USD conversion: 100 EUR is roughly ~108-110 USD, NOT 100 USD!
        # And Balance is 1000 USD - ~109 USD = ~891 USD, definitely NOT 1000 - 100 = 900!
        with self.app.app_context():
            rate_eur = currency_service.get_rates()['EUR']
            eur_in_usd = (Decimal('100.00') / Decimal(str(rate_eur))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            expected_balance = Decimal('1000.00') - eur_in_usd
            expected_bal_str = f"${expected_balance:,.2f}"
            self.assertIn(expected_bal_str.encode('utf-8'), res_usd.data)

    def test_currency_filtering_in_transactions(self):
        """Test filtering transaction history by currency."""
        today = date.today()
        with self.app.app_context():
            salary_cat = Category.query.filter_by(name='Salary').first()
            food_cat = Category.query.filter_by(name='Food').first()

            db.session.add(Transaction(type='income', amount=50000.0, currency='INR', description='Rupee Salary', category_id=salary_cat.id, date=today))
            db.session.add(Transaction(type='expense', amount=120.0, currency='USD', description='Dollar Expense', category_id=food_cat.id, date=today))
            db.session.add(Transaction(type='expense', amount=300.0, currency='AED', description='Dirham Expense', category_id=food_cat.id, date=today))
            db.session.commit()

        # Filter by currency=INR
        res_inr = self.client.get('/transactions?currency=INR')
        self.assertIn(b'Rupee Salary', res_inr.data)
        self.assertNotIn(b'Dollar Expense', res_inr.data)
        self.assertNotIn(b'Dirham Expense', res_inr.data)

        # Filter by currency=AED
        res_aed = self.client.get('/transactions?currency=AED')
        self.assertIn(b'Dirham Expense', res_aed.data)
        self.assertNotIn(b'Rupee Salary', res_aed.data)

    def test_edit_transaction_currency(self):
        """Test editing a transaction's currency and amount."""
        with self.app.app_context():
            food_cat = Category.query.filter_by(name='Food').first()
            food_cat_id = food_cat.id
            tx = Transaction(type='expense', amount=50.0, currency='USD', category_id=food_cat_id, description='Lunch', date=date.today())
            db.session.add(tx)
            db.session.commit()
            tx_id = tx.id

        response = self.client.post(f'/transactions/{tx_id}/edit', data={
            'type': 'expense',
            'amount': '42.00',
            'currency': 'GBP',
            'category_id': str(food_cat_id),
            'description': 'London Pub Lunch',
            'date': date.today().strftime('%Y-%m-%d')
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            updated_tx = db.session.get(Transaction, tx_id)
            self.assertEqual(updated_tx.amount, 42.00)
            self.assertEqual(updated_tx.currency, 'GBP')
            self.assertEqual(updated_tx.currency_symbol, '\u00a3')

    def test_budget_multi_currency_conversion(self):
        """Test that budget spending converts multi-currency expenses to budget currency."""
        today = date.today()
        with self.app.app_context():
            food_cat = Category.query.filter_by(name='Food').first()
            food_cat_id = food_cat.id

            # Expense 1: 50 USD
            db.session.add(Transaction(type='expense', amount=50.0, currency='USD', category_id=food_cat_id, date=today))
            db.session.commit()

        # Set Food Budget in EUR: 100 EUR
        res_budget = self.client.post('/budgets', data={
            'category_id': str(food_cat_id),
            'currency': 'EUR',
            'month': str(today.month),
            'year': str(today.year),
            'amount': '100.00'
        }, follow_redirects=True)

        self.assertEqual(res_budget.status_code, 200)
        self.assertIn(b'100.00', res_budget.data)

        # Spent should reflect the 50 USD converted to EUR, not raw 50!
        with self.app.app_context():
            rate_eur = currency_service.get_rates()['EUR']
            spent_in_eur = (Decimal('50.00') * Decimal(str(rate_eur))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            spent_str = f"{spent_in_eur:,.2f}"
            self.assertIn(spent_str.encode('utf-8'), res_budget.data)

    def test_settings_page_and_default_currency_update(self):
        """Test Settings route and updating default currency."""
        res_get = self.client.get('/settings')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b'Default Dashboard Currency', res_get.data)
        self.assertIn(b'Current Exchange Rates', res_get.data)

        # Update default currency to INR
        res_post = self.client.post('/settings', data={
            'default_currency': 'INR',
            'use_live_rates': 'on'
        }, follow_redirects=True)

        self.assertEqual(res_post.status_code, 200)
        self.assertIn(b'Default dashboard currency updated to INR', res_post.data)

        with self.app.app_context():
            self.assertEqual(Setting.get('default_currency'), 'INR')
            self.assertEqual(Setting.get('use_live_rates'), 'true')

    def test_quick_currency_switcher(self):
        """Test the topbar quick currency switcher endpoint."""
        res = self.client.get('/set-currency/AED', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess['active_currency'], 'AED')

    def test_csv_export_includes_currency_column(self):
        """Test that CSV export contains the currency column and original amount."""
        today = date.today()
        with self.app.app_context():
            salary_cat = Category.query.filter_by(name='Salary').first()
            food_cat = Category.query.filter_by(name='Food').first()

            db.session.add(Transaction(type='income', amount=85000.0, currency='INR', description='Salary Transfer', category_id=salary_cat.id, date=today))
            db.session.add(Transaction(type='expense', amount=35.0, currency='USD', description='Lunch Cafe', category_id=food_cat.id, date=today))
            db.session.commit()

        response = self.client.get('/export/csv')
        self.assertEqual(response.status_code, 200)
        csv_text = response.data.decode('utf-8')

        self.assertIn('Transaction ID,Date,Type,Category,Original Amount,Currency,Description,Created At', csv_text)
        self.assertIn('85000.00', csv_text)
        self.assertIn('INR', csv_text)
        self.assertIn('35.00', csv_text)
        self.assertIn('USD', csv_text)

    def test_supported_currencies_metadata(self):
        """Verify all 10 required currencies are defined with valid symbols."""
        required = ['INR', 'USD', 'EUR', 'GBP', 'AED', 'JPY', 'CAD', 'AUD', 'SGD', 'SAR']
        for curr in required:
            self.assertIn(curr, SUPPORTED_CURRENCIES)
            symbol = currency_service.get_symbol(curr)
            self.assertTrue(len(symbol) > 0)

    def test_validation_rejects_negative_or_zero_amount(self):
        """Verify validation rejects zero or negative amounts."""
        with self.app.app_context():
            food_cat = Category.query.filter_by(name='Food').first()
            food_cat_id = food_cat.id

        response = self.client.post('/transactions/add', data={
            'type': 'expense',
            'amount': '-25.00',
            'currency': 'USD',
            'category_id': str(food_cat_id),
            'description': 'Negative amount',
            'date': date.today().strftime('%Y-%m-%d')
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Amount must be greater than zero', response.data)

    def test_custom_category_creation(self):
        """Test creating a custom category."""
        response = self.client.post('/categories/add', data={
            'name': 'Cryptocurrency',
            'type': 'both',
            'color': '#F59E0B',
            'icon': 'coins'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            cat = Category.query.filter_by(name='Cryptocurrency').first()
            self.assertIsNotNone(cat)
            self.assertEqual(cat.type, 'both')


    def test_analytics_multi_currency(self):
        """Test analytics page multi-currency normalization and metrics."""
        today = date.today()
        with self.app.app_context():
            salary_cat = Category.query.filter_by(name='Salary').first()
            shopping_cat = Category.query.filter_by(name='Shopping').first()

            # Income: 2000 USD
            db.session.add(Transaction(type='income', amount=2000.0, currency='USD', category_id=salary_cat.id, date=today))
            # Expense: 50000 INR
            db.session.add(Transaction(type='expense', amount=50000.0, currency='INR', category_id=shopping_cat.id, date=today))
            db.session.commit()

        # View analytics in USD
        response = self.client.get('/analytics?period=this_month&currency=USD')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Savings Rate:', response.data)
        self.assertIn(b'Shopping', response.data)

    def test_delete_transaction(self):
        """Test deleting a transaction with multi-currency amount."""
        with self.app.app_context():
            food_cat = Category.query.filter_by(name='Food').first()
            tx = Transaction(type='expense', amount=150.0, currency='AED', category_id=food_cat.id, description='Dinner', date=date.today())
            db.session.add(tx)
            db.session.commit()
            tx_id = tx.id

        response = self.client.post(f'/transactions/{tx_id}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Deleted expense transaction', response.data)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Transaction, tx_id))

    def test_validation_rejects_category_type_mismatch(self):
        """Verify an expense cannot use an income category."""
        with self.app.app_context():
            salary_cat = Category.query.filter_by(name='Salary', type='income').first()
            salary_cat_id = salary_cat.id

        response = self.client.post('/transactions/add', data={
            'type': 'expense',
            'amount': '100.00',
            'currency': 'USD',
            'category_id': str(salary_cat_id),
            'description': 'Mismatched category',
            'date': date.today().strftime('%Y-%m-%d')
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b'cannot be used for expense transactions', response.data)


if __name__ == '__main__':
    unittest.main()
