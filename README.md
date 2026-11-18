# 💰 FinTrack — Multi-Currency Python & Flask Expense Tracker

A modern, full-featured, and beginner-friendly **Personal Finance and Expense Tracking Web Application** built with **Python 3**, **Flask**, **SQLite**, **SQLAlchemy**, and **Chart.js**, featuring complete **multi-currency support** with **live exchange rate conversion** and **Decimal-precision financial arithmetic**.

Designed to empower individuals to take complete control of their personal finances across global transactions, **FinTrack** provides real-time income and expense tracking, categorical budgeting, proactive spending limit alerts, financial health metrics, interactive visualizations, multi-currency conversion, and one-click CSV export.

---

## 🌟 Key Features

### 1. 🌍 Comprehensive Multi-Currency Support
- **10 World Currencies Supported:**
  - 🇮🇳 **INR (`₹`)** — Indian Rupee
  - 🇺🇸 **USD (`$`)** — US Dollar
  - 🇪🇺 **EUR (`€`)** — Euro
  - 🇬🇧 **GBP (`£`)** — British Pound
  - 🇦🇪 **AED (`AED `)** — UAE Dirham
  - 🇯🇵 **JPY (`¥`)** — Japanese Yen
  - 🇨🇦 **CAD (`CA$`)** — Canadian Dollar
  - 🇦🇺 **AUD (`A$`)** — Australian Dollar
  - 🇸🇬 **SGD (`S$`)** — Singapore Dollar
  - 🇸🇦 **SAR (`SAR `)** — Saudi Riyal
- **Original Currency & Amount Preservation:** Every transaction and budget maintains its original currency and entered amount in the SQLite database.
- **Decimal-Precision Financial Calculations:** All financial summations, conversions, and balances utilize Python's `Decimal` with `ROUND_HALF_UP` to prevent floating-point rounding errors.
- **Normalized Combined Totals:** Different currencies are **never added directly**. All incoming and outgoing transactions are converted into the user's active/default dashboard currency before calculating combined totals, balances, and analytics.
- **Live Exchange Rate Engine:** Optional automatic live exchange rate synchronization via an open exchange rate API with intelligent 1-hour caching and accurate offline fallback rates.
- **Quick Currency Switcher:** One-click instant currency toggle in the top navigation bar to switch your entire dashboard view on the fly.
- **Application Settings Page:** Dedicated `/settings` portal to select your default dashboard currency and manage live exchange rate synchronization.

### 2. 📊 Modern Executive Dashboard
- **Key Performance Indicators (KPIs):** Real-time summary cards for **Total Lifetime Income**, **Total Lifetime Expenses**, **Current Net Balance**, **Monthly Income**, **Monthly Expenses**, and **Monthly Net Savings**, all displayed in the active dashboard currency.
- **Interactive Multi-Month Overview:** 6-month visual bar comparison of incoming cash flows vs. outflows normalized to the active currency.
- **Monthly Budget Consumption:** Live progress tracker showing the current month's budget utilization percentage, remaining balance, and warning indicators.
- **Top Spending Categories:** Instant breakdown of the month's largest expense drivers with visual progress tracks.
- **Recent Transactions:** Quick-access ledger displaying original currencies (`₹50,000.00`, `$120.00`) and converted equivalents (`≈ $591.72`).

### 3. 💵 Income & Expense Management
- Select currency when adding or modifying transactions.
- Default income categories: *Salary*, *Freelance*, *Investments*, *Gifts*, *Rental Income*, and *Other Income*.
- Default expense categories: *Food*, *Transportation*, *Shopping*, *Education*, *Healthcare*, *Entertainment*, *Bills*, *Rent*, *Travel*, and *Other*.
- **Custom Category Creator:** Add personalized categories with custom color palettes and icon representations.
- Full auditability: edit and remove records anytime.

### 4. 📜 Transaction History & Filtering
- Dedicated transaction management table with sortable columns: Date, Type, Category, Description, and Amount.
- Multi-parameter search & filtering:
  - **Currency Filter:** Filter transactions by specific currency (*All Currencies*, *USD*, *INR*, *EUR*, etc.).
  - Text search across transaction notes and category names.
  - Filter by transaction type (*Income Only*, *Expense Only*, or *All*).
  - Filter by specific Category.
  - Date range filtering (*From Date* and *To Date*).
  - Sorting: *Date (Newest/Oldest)* and *Amount (Highest/Lowest)*.
- Live summary bar showing total records, filtered income, filtered expenses, and net balance in the active dashboard currency.

### 5. 🎯 Smart Budget Management & Multi-Currency Alerts
- Set overall monthly spending caps or target individual expense categories in any chosen currency.
- When calculating spending against a budget, expenses logged in other currencies are automatically converted into the budget's currency using `Decimal` arithmetic.
- **Visual Progress Bars & Dynamic Status Alerts:**
  - 🟢 **Safe (< 80%):** Spending is well within planned allocation.
  - 🟠 **Warning (80% – 99%):** Proactive alert when approaching budget limits.
  - 🔴 **Exceeded (≥ 100%):** Prominent danger banner displaying the exact overrun amount.

### 6. 📈 Analytics & Financial Reports
- Multi-period filtering: *This Month*, *Last Month*, *Last 3 Months*, *This Year*, *All Time*, and *Custom Date Range*.
- Key financial indicators: Net Savings, Savings Rate percentage (`(Income - Expenses) / Income * 100%`), Daily Average Outflow, and Top Spending Category.
- Visual charts:
  - **12-Month Cash Flow Bar Chart:** Income vs Expenses side-by-side.
  - **Category-wise Expense Distribution:** Interactive doughnut/pie chart with percentage breakdowns.
  - **Monthly Spending Trend:** Smooth curved line chart displaying spending trajectory over time.
- Detailed Category Breakdown Table with item count, total dollars spent, and share percentage.

### 7. 📤 One-Click CSV Export
- Export complete transaction ledgers into standard `.csv` format.
- Output columns: `Transaction ID`, `Date`, `Type`, `Category`, `Original Amount`, `Currency`, `Description`, and `Created At`.
- Respects active filter queries (including currency filters).

### 8. 🔒 Security & Data Integrity
- Robust session-based CSRF protection on all mutating requests (`POST`).
- Strict server-side input validation (amounts must be strictly positive, valid dates, type matching).
- Native HTML5 `<dialog>` confirmation modals before destructive deletions.
- **Safe Automatic Database Migration:** Automatic schema migration on startup detects existing tables and safely adds `currency` columns and settings without losing or modifying existing transaction records.

---

## 🛠️ Technology Stack

| Layer | Technologies Used |
|---|---|
| **Backend Framework** | Python 3.11+, Flask 3.x |
| **Database & ORM** | SQLite 3, Flask-SQLAlchemy 3.x, SQLAlchemy 2.x |
| **Arithmetic Precision** | Python `decimal.Decimal` with `ROUND_HALF_UP` |
| **Exchange Rate Service** | Live Exchange API (`open.er-api.com`) with offline fallback cache |
| **Frontend UI** | Semantic HTML5, Modern CSS3 (CSS Variables, Flexbox, Grid), JavaScript (ES6+) |
| **Visualizations** | Chart.js 4.4+ (Responsive canvases, interactive tooltips) |
| **Icons & Typography** | Font Awesome 6.5+, Google Inter font family |
| **Configuration** | Python-dotenv, Environment Variables |
| **Testing** | Python `unittest` test suite (17 automated tests) |

---

## 📁 Project Structure

```text
expense-tracker/
│
├── app.py                  # Main Flask application, routes, controllers & filters
├── models.py               # SQLAlchemy models (Transaction, Category, Budget, Setting)
├── currency_service.py     # Live exchange rate engine, conversion & Decimal formatting
├── config.py               # Configuration settings and environment variables
├── requirements.txt        # Production dependencies
├── .env.example            # Sample environment variable template
├── .gitignore              # Files and directories excluded from Git
├── README.md               # Complete project documentation
├── test_app.py             # Automated unit and integration test suite (17 tests)
│
├── instance/               # SQLite persistent database storage
│   └── expense_tracker.db  # SQLite database file (migrated automatically)
│
├── templates/              # Reusable Jinja2 HTML templates
│   ├── base.html           # Master layout: sidebar, topbar currency switcher & modals
│   ├── index.html          # Executive Dashboard view
│   ├── add_transaction.html# Add & Edit transaction form view with currency selection
│   ├── transactions.html   # Transaction history with currency filtering & CSV export
│   ├── budgets.html        # Budget management with multi-currency conversion
│   ├── analytics.html      # Visual reports, Chart.js graphs & category table
│   └── settings.html       # Application settings: default currency & exchange rates
│
└── static/                 # Static assets
    ├── css/
    │   └── style.css       # Complete responsive CSS styling system
    └── js/
        └── script.js       # Client-side interactions, modals & UI helpers
```

---

## 🚀 Installation & Setup Guide

### 1. Prerequisites
Ensure you have **Python 3.9+** installed on your machine. Check by running:
```bash
python --version
```

### 2. Navigate to Project Directory
```bash
cd expense-tracker
```

### 3. Create and Activate a Virtual Environment

#### On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### On Windows (Command Prompt):
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
```

#### On macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables (Optional)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

---

## ▶️ Running the Application

Start the Flask development server:
```bash
python app.py
```

Once started, open your web browser and navigate to:
```text
http://127.0.0.1:5000
```

> **Note on Migration:** If you have existing transactions from an earlier version, FinTrack automatically detects and migrates your SQLite database safely upon startup, preserving all existing records.

---

## 🧪 Running Automated Tests

A comprehensive suite of 17 unit and integration tests is included to verify core routes, database models, multi-currency conversions, calculations, validations, and CSV exports:

```bash
python -m unittest test_app.py -v
```

All 17 tests verify:
- Default category auto-seeding
- Income and Expense record creation with currency selection (INR, EUR, etc.)
- Multi-currency normalization: ensuring differing currencies are converted with `Decimal` rather than added directly
- Currency filtering in transaction history
- Transaction editing across currencies
- Budget allocations with multi-currency expense conversion
- Default currency configuration in Settings
- Quick currency switcher functionality
- CSV export containing the `Currency` and `Original Amount` columns
- All 10 required currencies metadata and symbols
- Input validations and category type compatibility
- Analytics calculations with multi-currency records

---

## 📄 License
This project is open-source and available under the **MIT License**.
