# codesub

Subscribe to file line ranges and detect changes via git diff.

## Installation

```bash
poetry install
```

## Usage

```bash
# Initialize in a git repository
codesub init

# Subscribe to a line range
codesub add path/to/file.py:42-50 --label "Important function"

# List subscriptions
codesub list

# Scan for changes
codesub scan

# Apply proposed updates
codesub apply-updates updates.json
```

## Commands

- `codesub init` - Initialize codesub in the repository
- `codesub add <location>` - Add a subscription to a line range
- `codesub list` - List all subscriptions
- `codesub remove <id>` - Remove a subscription
- `codesub scan` - Scan for changes and report triggers/proposals
- `codesub apply-updates <file>` - Apply update proposals
