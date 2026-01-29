# Semantic Code Subscriptions - External LLM Review Package

## Instructions

1. **Copy the prompt below** into your chat interface (Claude.ai, ChatGPT, etc.)
2. **Attach the context file**: `chat-context.txt` (in this same directory)
   - Or paste its contents if the interface doesn't support file attachments
3. **Submit** and review the response
4. **Save** the response to `tasks/semantic-subscriptions/plan-revised.md`

---

# Task: Semantic Code Subscriptions for codesub

## Problem Statement

The codesub tool currently tracks code changes using **line-based subscriptions** (e.g., `models.py:42-50`). This approach is fragile because:
- Adding a docstring above a function shifts line numbers, triggering false updates
- Refactoring that moves code to another file loses the subscription entirely
- Users want to track "the `Address.validate_street` method" not "lines 42-50"

We need to upgrade codesub to support **semantic subscriptions** that track code constructs (classes, functions, methods, variables) by identity, not just line numbers.

## Current State

codesub has:
- Line-based `Subscription` model with path, start_line, end_line
- `Detector` that uses git diff hunks to detect overlaps with line ranges
- CLI commands: init, add, list, remove, scan, apply-updates
- REST API for subscription CRUD and scanning
- Config stored in `.codesub/config.json` per repository

## Desired State

Add semantic subscriptions that:
1. **Parse code** using Tree-sitter to extract constructs (classes, functions, methods, variables)
2. **Fingerprint constructs** using multiple hashes:
   - `interface_hash`: kind + parameters + decorators (excludes name) - for rename detection
   - `body_hash`: normalized tokens - for content change detection
3. **Match constructs** across versions using multi-stage pipeline:
   - Stage 1: Exact match (same FQN)
   - Stage 2: Rename/move detection (same fingerprints, different name/location)
4. **Classify changes**:
   - STRUCTURAL: signature changed → TRIGGER notification
   - CONTENT: body changed → TRIGGER notification
   - LOCATION: moved/renamed but same content → UPDATE subscription, no trigger
   - COSMETIC: only formatting/comments → NO action
5. **Maintain backward compatibility** with existing line-based subscriptions

## Constraints

- Start with Python support only (design for Java/Go extension later)
- Use Tree-sitter for parsing (error-tolerant, multi-language)
- Static analysis only - no runtime execution
- Must work with local git repositories
- Keep line-based subscriptions working (don't break existing functionality)

## Review Feedback

The initial plan received the following critical feedback:
1. **Unclear UX**: How does a user create a semantic subscription? Define exact CLI interface
2. **Simplify for MVP**: Start with 2 matching stages (exact + rename-resistant), defer fuzzy matching
3. **Consider unified model**: Extend existing `Subscription` with optional `semantic_target` instead of separate model
4. **Handle parse errors**: Define behavior when construct can't be found due to syntax errors
5. **FQN format**: Define explicit format (e.g., `path/to/file.py::ClassName.method_name`)

## Codebase Context

The attached file `chat-context.txt` contains the relevant source code.

**Key files included:**

1. `src/codesub/models.py` - Current data models (Subscription, Trigger, Proposal, ScanResult)
2. `src/codesub/detector.py` - Current line-based change detection logic
3. `src/codesub/cli.py` - CLI interface (argparse-based)
4. `src/codesub/api.py` - FastAPI REST endpoints
5. `src/codesub/config_store.py` - Config persistence (.codesub/config.json)
6. `src/codesub/git_repo.py` - Git operations wrapper
7. `tasks/semantic_subscriptions_research.md` - Research on approaches
8. `tasks/semantic/review.md` - External research on semantic tracking
9. `tasks/semantic-subscriptions/plan.md` - Initial implementation plan
10. `tasks/semantic-subscriptions/plan-review.md` - Review feedback
11. `research/semantic-code-parsing.md` - Detailed tool research

## Your Task

Review the implementation plan and feedback, then create a **revised implementation plan** that:

1. **Addresses the critical feedback** - Especially UX, simplified scope, and unified model
2. **Follows existing patterns** - Match the coding style and architecture in the context
3. **Is specific** - Include exact file paths, function names, and code snippets
4. **Handles edge cases** - Parse errors, deleted files, malformed code
5. **Defines the MVP scope clearly** - What's in v1 vs deferred to later

Focus on answering these key questions:
1. How does a user specify what construct to subscribe to? (CLI command format)
2. Should we extend `Subscription` or create separate `SemanticSubscription`?
3. What's the simplest fingerprinting approach that provides value?
4. How do we handle parse errors and missing constructs?

## Expected Output Format

```markdown
# Revised Implementation Plan: Semantic Code Subscriptions

## MVP Scope
[What's included vs deferred]

## Design Decisions (Revised)
[Key decisions with rationale]

## User Interface
[Exact CLI commands and API endpoints]

## Data Model Changes
[Specific model changes with code]

## Implementation Steps
[Step-by-step with file paths and code snippets]

## Testing Strategy
[Test cases]

## Edge Cases
[How each is handled]

## Future Work (Deferred)
[What's not in MVP]
```
