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

### Code Review Automation

Track critical code paths and get notified in PRs when they change. Integrates with CI to flag changes that need extra review attention.

### Documentation Sync

When documentation references specific line numbers or code sections, subscribe to those sections. You'll know immediately when the code changes and docs need updating.

### Security Monitoring

Subscribe to authentication logic, authorization checks, cryptographic operations, and other security-sensitive code. Any modification triggers a review.

### Onboarding

Create subscriptions for the most important parts of your codebase with descriptive labels. New team members can quickly find and understand critical code.

### API Stability

Track public interfaces, exported functions, and API contracts. Structural changes to these subscriptions indicate breaking changes that need versioning attention.

### Refactoring Safety

Before a large refactoring, subscribe to key behaviors and outputs. Scan after refactoring to verify the important parts still exist and have the expected signatures.

## Symbol Discovery

Not sure what to subscribe to? Use symbol discovery to explore available constructs in any file:

- List all functions, classes, methods, and variables
- Filter by construct kind (function, method, class, etc.)
- Search by name pattern
- See the qualified name to use for subscriptions

## License

MIT
