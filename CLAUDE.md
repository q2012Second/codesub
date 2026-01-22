# codesub - Code Subscription Tool

A Python CLI tool that lets you "subscribe" to file line ranges, detect changes via git diff, and keep subscriptions valid across line shifts and file renames.

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Run CLI
poetry run codesub --help
```

## Project Structure

- `src/codesub/` - Main package
  - `cli.py` - CLI interface (argparse)
  - `models.py` - Data models (Subscription, Anchor, Config)
  - `config_store.py` - JSON config management
  - `git_repo.py` - Git wrapper
  - `diff_parser.py` - Unified diff parsing
  - `detector.py` - Trigger detection and line shift calculation
  - `update_doc.py` - Update document generation
  - `updater.py` - Apply proposals to subscriptions
- `tests/` - Test suite (pytest)

## Usage

```bash
# Initialize in a git repo
codesub init

# Subscribe to a line range
codesub add path/to/file.py:42-50 --label "Important function"

# List subscriptions
codesub list

# Scan for changes (compare baseline to HEAD)
codesub scan --write-updates updates.json

# Apply proposed updates
codesub apply-updates updates.json
```
