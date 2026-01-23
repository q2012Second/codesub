# Mock Repository

**This is a mock repository included with codesub for testing and demonstration purposes.**

It contains sample Python files that you can use to try out codesub's subscription and change detection features without setting up your own project.

## Setup

The easiest way to set up the mock repo is using the task command:

```bash
task mock:init
```

This will:
1. Initialize git (rename `.git_template` to `.git`)
2. Register the project with codesub
3. Create a sample subscription for the database config (lines 5-9)

### Manual Setup

Alternatively, initialize manually:

```bash
cd mock_repo
mv .git_template .git
codesub projects add ./mock_repo --name "Mock Repo"
```

## File Structure

```
mock_repo/
├── config.py          # Constants and settings
├── models.py          # Data models: User, Product, Order
├── utils.py           # Utility functions
├── api/
│   ├── __init__.py
│   └── routes.py      # API route definitions
└── services/
    ├── __init__.py
    ├── auth.py        # Authentication service
    └── database.py    # Database connection
```

## Suggested Subscriptions

Try subscribing to these code sections:

| File | Lines | Description |
|------|-------|-------------|
| config.py | 5-9 | Database settings |
| config.py | 12-15 | API configuration |
| models.py | 9-17 | User dataclass |
| models.py | 20-32 | Product dataclass |
| utils.py | 8-10 | hash_password function |
| services/auth.py | 16-28 | login method |
| api/routes.py | 22-25 | list_users route |

After adding subscriptions, try modifying some files and running a scan to see how codesub detects changes.
