# Application Configuration
# External service URLs and app settings

# API versioning - tracked by clients
API_VERSION = "v2"

# Stripe payment integration
STRIPE_API_URL = "https://api.stripe.com/v1"
STRIPE_WEBHOOK_VERSION = "2024-01-01"

# ShipFast shipping provider
SHIPFAST_API_URL = "https://api.shipfast.io/v3"
SHIPFAST_WEBHOOK_SECRET = "whsec_xxxxx"

# Order processing
MIN_ORDER_AMOUNT = 10.00
MAX_ORDER_ITEMS = 50
FREE_SHIPPING_THRESHOLD = 75.00

# Tax rates by region (decimal)
TAX_RATES = {
    "US-CA": 0.0725,
    "US-NY": 0.08,
    "US-TX": 0.0625,
    "EU": 0.20,
    "DEFAULT": 0.0,
}
