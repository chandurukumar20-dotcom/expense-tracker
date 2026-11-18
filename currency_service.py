import json
import logging
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# SUPPORTED CURRENCIES METADATA
# -----------------------------------------------------------------------------
SUPPORTED_CURRENCIES = {
    'USD': {'code': 'USD', 'symbol': '$', 'name': 'US Dollar'},
    'INR': {'code': 'INR', 'symbol': '₹', 'name': 'Indian Rupee'},
    'EUR': {'code': 'EUR', 'symbol': '€', 'name': 'Euro'},
    'GBP': {'code': 'GBP', 'symbol': '£', 'name': 'British Pound'},
    'AED': {'code': 'AED', 'symbol': 'AED ', 'name': 'UAE Dirham'},
    'JPY': {'code': 'JPY', 'symbol': '¥', 'name': 'Japanese Yen'},
    'CAD': {'code': 'CAD', 'symbol': 'CA$', 'name': 'Canadian Dollar'},
    'AUD': {'code': 'AUD', 'symbol': 'A$', 'name': 'Australian Dollar'},
    'SGD': {'code': 'SGD', 'symbol': 'S$', 'name': 'Singapore Dollar'},
    'SAR': {'code': 'SAR', 'symbol': 'SAR ', 'name': 'Saudi Riyal'},
}

# Accurate baseline fallback rates (Base: USD = 1.0)
FALLBACK_RATES = {
    'USD': Decimal('1.0000'),
    'INR': Decimal('84.5000'),
    'EUR': Decimal('0.9200'),
    'GBP': Decimal('0.7900'),
    'AED': Decimal('3.6725'),
    'JPY': Decimal('154.5000'),
    'CAD': Decimal('1.4000'),
    'AUD': Decimal('1.5300'),
    'SGD': Decimal('1.3400'),
    'SAR': Decimal('3.7500'),
}


class CurrencyService:
    """Manages currency conversions, live exchange rate synchronization, and formatting."""

    def __init__(self):
        self._cached_rates = dict(FALLBACK_RATES)
        self._last_fetched = None
        self._source = 'Default Baseline Rates'
        self._cache_ttl_seconds = 3600  # 1 hour cache

    @property
    def supported_currencies(self):
        return SUPPORTED_CURRENCIES

    def get_symbol(self, currency_code: str) -> str:
        """Return currency symbol or currency code as fallback."""
        if not currency_code:
            return '$'
        code = currency_code.upper()
        return SUPPORTED_CURRENCIES.get(code, {}).get('symbol', f"{code} ")

    def get_name(self, currency_code: str) -> str:
        """Return human-readable currency name."""
        code = (currency_code or 'USD').upper()
        return SUPPORTED_CURRENCIES.get(code, {}).get('name', code)

    def to_decimal(self, amount) -> Decimal:
        """Safely convert any numeric type to Decimal."""
        if isinstance(amount, Decimal):
            return amount
        if amount is None or amount == '':
            return Decimal('0.00')
        try:
            return Decimal(str(amount))
        except Exception:
            return Decimal('0.00')

    def get_rates(self, force_refresh: bool = False, use_live: bool = True) -> dict:
        """
        Retrieve exchange rates against USD base.
        Fetches live rates from open exchange API if cache is stale and live rates are enabled.
        """
        if not use_live:
            return dict(self._cached_rates)

        now = datetime.now(timezone.utc)
        is_cache_fresh = (
            self._last_fetched is not None and
            (now - self._last_fetched).total_seconds() < self._cache_ttl_seconds
        )

        if not force_refresh and is_cache_fresh:
            return dict(self._cached_rates)

        # Attempt to fetch live exchange rates
        try:
            url = 'https://open.er-api.com/v6/latest/USD'
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'FinTrackExpenseTracker/2.0'}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    api_rates = data.get('rates', {})
                    new_rates = {}
                    for code in SUPPORTED_CURRENCIES.keys():
                        if code in api_rates:
                            new_rates[code] = Decimal(str(api_rates[code]))
                        else:
                            new_rates[code] = self._cached_rates.get(code, FALLBACK_RATES[code])

                    self._cached_rates = new_rates
                    self._last_fetched = now
                    self._source = 'Live Exchange API (open.er-api.com)'
                    logger.info("Successfully refreshed live exchange rates: %s", new_rates)
                    return dict(self._cached_rates)
        except Exception as e:
            logger.warning("Could not fetch live exchange rates (%s); using cached/fallback rates.", str(e))
            if not self._last_fetched:
                self._source = 'Offline Fallback Rates'

        return dict(self._cached_rates)

    def convert(
        self,
        amount,
        from_currency: str,
        to_currency: str,
        use_live: bool = True
    ) -> Decimal:
        """
        Convert an amount from one currency to another using Decimal arithmetic.
        """
        from_code = (from_currency or 'USD').upper()
        to_code = (to_currency or 'USD').upper()

        amount_dec = self.to_decimal(amount)

        if from_code == to_code:
            return amount_dec.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        rates = self.get_rates(use_live=use_live)

        rate_from = rates.get(from_code, FALLBACK_RATES.get(from_code, Decimal('1.0')))
        rate_to = rates.get(to_code, FALLBACK_RATES.get(to_code, Decimal('1.0')))

        if rate_from <= 0:
            rate_from = Decimal('1.0')

        # Convert to USD first, then to target currency
        usd_value = amount_dec / rate_from
        converted = usd_value * rate_to

        return converted.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def format_currency(
        self,
        amount,
        currency_code: str,
        include_code: bool = False
    ) -> str:
        """
        Format an amount with the corresponding currency symbol and commas.
        Example: ₹1,500.00 or $45.20
        """
        code = (currency_code or 'USD').upper()
        symbol = self.get_symbol(code)
        amount_dec = self.to_decimal(amount)

        formatted_num = f"{amount_dec:,.2f}"

        if include_code:
            return f"{symbol}{formatted_num} {code}"
        return f"{symbol}{formatted_num}"

    def get_rate_info(self) -> dict:
        """Return information about the current exchange rate status."""
        rates = self.get_rates()
        return {
            'source': self._source,
            'last_fetched': self._last_fetched.strftime('%Y-%m-%d %H:%M:%S UTC') if self._last_fetched else 'Offline Fallback',
            'rates': {k: float(v) for k, v in rates.items()}
        }


# Global singleton instance
currency_service = CurrencyService()
