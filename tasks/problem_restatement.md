# Code Change Subscription System - Problem Restatement

## Context

In a microservice architecture with multiple teams (e.g., Python and Java services), services often have **indirect dependencies** that aren't explicitly tracked.

**Example scenario:**
- A Java service defines `Address.street` with a max length of 100 characters, exposed via CRUD API
- A Python service consumes `Address.street` via RabbitMQ and stores it in its database
- When requirements change (street length → 120 chars), the Java team updates their code
- The Python team may not be informed, leading to potential data truncation or errors

## Problem Statement

There is no mechanism for developers to be notified when code they depend on (in other repositories/services) changes. Cross-team communication is unreliable.

## Proposed Solution

A **subscription-based notification system** that:
1. Allows developers to subscribe to specific code locations in any repository
2. Analyzes merge request diffs to detect changes affecting subscriptions
3. Notifies subscribers when their tracked code changes

## POC Scope

Build a CLI tool that demonstrates the core concept with **line-based subscriptions**.

### Functional Requirements

1. **Subscription Management**
   - Subscribe to specific lines in specific files
   - Store subscriptions in a local configuration file
   - Support multiple subscriptions

2. **Change Detection**
   - Given a git diff, determine if any subscribed lines were modified
   - Output which subscriptions were triggered

3. **Subscription Maintenance**
   - When unrelated changes shift line numbers (additions/deletions above subscribed lines), the subscription should remain valid
   - Generate a "subscription update" document that proposes new line numbers
   - If applied, the subscription continues tracking the same logical code

4. **File Rename Handling**
   - If a subscribed file is renamed, detect this and propose subscription update

### Technical Constraints

- **Static analysis only** — no runtime execution of the target codebase
- **Language agnostic** — works with any text file (future: language-aware parsing)
- **Local operation** — works with local git repositories

### Input/Output

**Inputs:**
- Path to a git repository
- Subscription configuration file
- Git diff (from MR or commit range)

**Outputs:**
- List of triggered subscriptions (subscribed code was changed)
- List of subscription updates needed (line numbers shifted, file renamed)

### Example Workflow

```
1. Developer subscribes to `services/address/models.py:42-45` (the Address validation constants)

2. MR is created that modifies that file

3. Tool analyzes the diff:
   - If lines 42-45 were modified → trigger notification
   - If lines 1-30 had additions (pushing 42-45 to 52-55) → propose subscription update

4. Developer reviews triggered subscriptions and applies updates
```

## Future Considerations (Out of POC Scope)

- Subscribe to language constructs (classes, functions, constants) instead of lines
- Cross-repository subscriptions
- Integration with CI/CD pipelines
- Web UI for subscription management
- Notification channels (email, Slack, etc.)
