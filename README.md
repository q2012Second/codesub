# codesub

Subscribe to code sections and get notified when they change.

## What is codesub?

codesub is a code monitoring tool that lets you track specific sections of code across your codebase. When tracked code changes, codesub detects it and tells you exactly what changed and why.

## Subscription Types

### Line-Based Subscriptions

Track specific line ranges in files. Useful for monitoring configuration blocks, critical code sections, or any code you reference in external documentation.

**Example targets:**
- `config.py:10-25` — Track lines 10 through 25
- `src/api.py:100` — Track a single line

When lines around your subscription shift (due to code added/removed elsewhere in the file), codesub automatically proposes updated line numbers to keep your subscription accurate.

### Semantic Subscriptions

Track code constructs by their identity, not their location. Semantic subscriptions follow functions, classes, methods, and variables even as they move around the file or get refactored.

**Example targets:**
- `auth.py::User.validate` — Track a method
- `config.py::API_VERSION` — Track a constant
- `models.py::User.email` — Track a class field
- `types.py::Status.PENDING` — Track an enum member

**Supported constructs (Python):**
- Functions and methods
- Classes
- Module-level variables and constants
- Class fields and properties
- Enum members
- Dataclass fields
- TypedDict fields

Semantic subscriptions survive refactoring—if a function moves to a different line, gets reformatted, or has code added around it, the subscription stays attached to the right construct.

## Change Detection

When you scan for changes, codesub compares your baseline (usually the last commit or a branch like `main`) against the current state and identifies which subscriptions were affected.

### Change Classifications

**For line-based subscriptions:**
- **Triggered**: Lines within the subscribed range were modified
- **Line shift**: Code above the subscription changed, shifting line numbers (auto-update available)

**For semantic subscriptions:**
- **Structural change**: The interface changed—type annotations, method signatures, function parameters
- **Content change**: The implementation changed—function body, constant value, field default
- **Missing**: The construct was deleted from the codebase
- **Renamed**: The construct was renamed (update proposal available)

## Viewing Subscriptions

### List View

See all your subscriptions at a glance:
- Subscription ID and label
- Target (file path and line range or qualified name)
- Status (active/inactive)
- Subscription type (line-based or semantic)

### Detail View

Dive into a specific subscription to see:
- Full target information
- Current line range (with code preview)
- Anchors (context lines that help track position)
- For semantic subscriptions: construct kind, qualified name, fingerprints
- Description and metadata

## Scanning for Changes

A scan compares two git refs and reports which subscriptions were triggered:

- **Default scan**: Compare configured baseline to HEAD
- **Commit range**: Compare any two commits
- **Merge request**: Compare a feature branch against its target

### Scan Results

Each scan produces a report showing:
- Total subscriptions checked
- Number triggered
- For each triggered subscription:
  - What changed (lines modified, construct altered)
  - Change classification (structural/content/missing)
  - Proposed updates (if line shifts detected)

### Update Proposals

When code changes cause line numbers to shift, codesub proposes updated subscription ranges. You can:
- Review the proposals
- Apply them automatically
- Apply selectively (dry-run first)

## Multi-Project Support

Manage subscriptions across multiple repositories from a single interface:

- **Project registration**: Add any git repository with codesub initialized
- **Project switching**: Quickly switch between projects
- **Independent configs**: Each project maintains its own subscriptions and baseline
- **Centralized scanning**: Run scans across projects from one place

## Scan History

Every scan is stored for later review:

- **Browse past scans**: See when scans ran and what was detected
- **Compare over time**: Track how subscriptions have been affected across commits
- **Audit trail**: Keep a record of what changed and when

## Web Interface

The web UI provides a visual way to manage everything:

**Dashboard:**
- Project selector
- Subscription list with status indicators
- Quick scan button

**Subscription Management:**
- Add/remove subscriptions
- Filter by status (active, inactive, triggered)
- Bulk operations

**Scan Interface:**
- Run scans with custom base/target refs
- View triggered subscriptions highlighted
- Apply update proposals with one click

**History Browser:**
- Timeline of past scans
- Detailed view of each scan result
- Clear old history

## Use Cases

### External API Contracts

Track response schemas from external services. When Stripe or another provider changes their API, you need to update your code accordingly—codesub alerts you when these structures change.

```bash
codesub add "schemas/external.py::StripePaymentIntent.status" --label "Stripe payment status"
```

**What gets tracked:**
```python
@dataclass
class StripePaymentIntent:
    """Response from Stripe POST /v1/payment_intents"""
    id: str
    amount: int
    currency: str
    status: str       # <-- TRACKED: "requires_payment_method", "succeeded", etc.
    client_secret: str
    created: int
```

If `status` changes type (e.g., `str` → `PaymentStatus`) → **STRUCTURAL change**
If the field is removed → **MISSING**

### Public API Schemas

Track your own API response structures. Changes here are breaking changes for frontend/mobile clients.

```bash
codesub add "schemas/api.py::PricingBreakdown.total" --label "Pricing total field"
```

**What gets tracked:**
```python
@dataclass
class PricingBreakdown:
    """Price breakdown returned to clients"""
    subtotal: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal    # <-- TRACKED: Frontend displays this to users
```

If `total: Decimal` → `total: float` → **STRUCTURAL change** (type changed)

### Business Logic

Track revenue-critical calculations and validation rules.

```bash
codesub add "services/order.py::OrderService.calculate_pricing" --label "Pricing calculation"
```

**What gets tracked:**
```python
def calculate_pricing(self, items: list[OrderItem], user: User) -> PricingBreakdown:
    """Calculate order totals including tax and shipping."""
    subtotal = sum(item.subtotal for item in items)

    # Tax calculation based on user region
    tax_rate = TAX_RATES.get(user.region, TAX_RATES["DEFAULT"])
    tax = subtotal * Decimal(str(tax_rate))

    # Free shipping over threshold
    if subtotal >= Decimal(str(FREE_SHIPPING_THRESHOLD)):
        shipping = Decimal("0.00")
    else:
        shipping = self.SHIPPING_RATE

    total = subtotal + tax + shipping
    ...
```

If the method body changes → **CONTENT change**
If the signature changes → **STRUCTURAL change**
If the method is deleted → **MISSING**

### Configuration

Track settings that affect integrations and business rules.

```bash
codesub add "config.py::FREE_SHIPPING_THRESHOLD" --label "Free shipping threshold"
codesub add "config.py::TAX_RATES" --label "Tax rates"
```

**What gets tracked:**
```python
# Order processing
FREE_SHIPPING_THRESHOLD = 75.00   # <-- TRACKED: Affects shipping calculation

# Tax rates by region
TAX_RATES = {                     # <-- TRACKED: Affects tax calculation
    "US-CA": 0.0725,
    "US-NY": 0.08,
    "US-TX": 0.0625,
    "EU": 0.20,
    "DEFAULT": 0.0,
}
```

If `FREE_SHIPPING_THRESHOLD = 75.00` → `100.00` → **CONTENT change**

### Security-Sensitive Code

Track authentication, authorization, and cryptographic code.

```bash
codesub add "auth/service.py::AuthService.validate_token" --label "Token validation"
codesub add "auth/service.py::AuthService.hash_password" --label "Password hashing"
```

Any modification to these methods triggers review.

### Line-Based: Documentation References

When docs reference specific lines, track those ranges:

```bash
codesub add "config.py:20-27" --label "Tax rates (referenced in docs)"
```

If code is added above line 20, codesub proposes updating to `config.py:22-29`.

## Symbol Discovery

Not sure what to subscribe to? Use symbol discovery to explore available constructs in any file:

- List all functions, classes, methods, and variables
- Filter by construct kind (function, method, class, etc.)
- Search by name pattern
- See the qualified name to use for subscriptions

## Try It Out

The `mock_repo/` directory contains a sample e-commerce API you can experiment with:

```bash
# Set up the mock repository
task mock:init

# View the created subscriptions
cd mock_repo && codesub list
```

This creates 11 subscriptions tracking:
- **External API schemas** - Stripe payment status, webhook event types
- **Public API schemas** - Pricing breakdown, order response fields
- **Business logic** - Pricing calculation, order validation methods
- **Configuration** - API version, shipping threshold, tax rates

Try making changes and scanning:

```bash
# Make a change (e.g., edit FREE_SHIPPING_THRESHOLD in config.py)
# Then scan
codesub scan

# Output shows: CONTENT change detected in "Free shipping threshold"
```

See `mock_repo/README.md` for detailed examples of each change type.

## License

MIT
