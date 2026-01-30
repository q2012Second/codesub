# How to Use These Files

## Quick Start

1. Open Claude.ai (or your preferred chat interface)
2. Attach `chat-context.txt` as a file
3. Copy the contents of `chat-prompt.md` into the message
4. Send and review the response

## Files in This Directory

| File | Purpose |
|------|---------|
| `chat-context.txt` | Source code context (40K tokens) - attach to chat |
| `chat-prompt.md` | Review prompt - copy to chat message |
| `plan.md` | The implementation plan being reviewed |
| `problem.md` | The original problem statement |
| `plan-review.md` | Previous automated review results |
| `state.json` | Workflow state checkpoint |

## After Review

Once you receive feedback:

1. If **APPROVED**: Return here and say "proceed with implementation"
2. If **NEEDS CHANGES**: Share the feedback and I'll revise the plan

---

# Review Prompt

*(Copy everything below this line to your chat)*

---

# Task: Review Implementation Plan for Aggregate/Container Tracking

## Problem Statement

Add `--include-members` flag to semantic subscriptions that tracks a container (class/enum) and triggers when ANY member changes:

```bash
codesub add auth.py::User --include-members  # Trigger if any User.* changes
```

## User Requirements (already decided)

1. **Private members** (`_field`): Optional flag `--include-private`, disabled by default
2. **Nested classes**: Yes, tracked as members
3. **Module-level aggregation**: Not supported (out of scope)
4. **New member detection**: Must detect new members as triggers
5. **Reporting**: Only changed members, but include "parent" subscription reference
6. **Decorator changes**: Optional flag `--track-decorators`, enabled by default

## What I Need You To Do

Review the implementation plan in the attached context file (`chat-context.txt`) and provide feedback on:

### 1. Correctness
- Are the code snippets correct and complete?
- Will the detector integration work as described?
- Are there any bugs in the member extraction logic?

### 2. Completeness
- Are any steps missing?
- Are edge cases properly handled?
- Is the testing strategy sufficient?

### 3. Architecture
- Do the design decisions make sense?
- Are there simpler approaches?
- Any concerns about the data model changes?

### 4. Risks
- What could go wrong during implementation?
- Are there backward compatibility concerns?
- Performance implications?

## Codebase Context

The attached file `chat-context.txt` contains:

1. **`tasks/aggregate-container-tracking/plan.md`** - The implementation plan to review
2. **`tasks/aggregate-container-tracking/problem.md`** - The problem statement
3. **`src/codesub/models.py`** - Current data models (Subscription, SemanticTarget, Trigger)
4. **`src/codesub/detector.py`** - Current detection logic (`_check_semantic`)
5. **`src/codesub/cli.py`** - Current CLI implementation
6. **`src/codesub/api.py`** - Current REST API
7. **`src/codesub/updater.py`** - Current proposal application logic
8. **`src/codesub/semantic/python_indexer.py`** - Python construct extraction
9. **`src/codesub/semantic/java_indexer.py`** - Java construct extraction
10. **`src/codesub/semantic/indexer_protocol.py`** - Indexer protocol definition
11. **`src/codesub/semantic/construct.py`** - Construct dataclass

## Expected Output

Please provide:

1. **Overall Assessment**: Is the plan ready for implementation? (APPROVED / NEEDS CHANGES)

2. **Issues Found** (if any):
   - Severity (Critical/Major/Minor)
   - Description of the issue
   - Suggested fix

3. **Suggestions** (optional):
   - Improvements that could be made
   - Alternative approaches worth considering

4. **Questions** (if any):
   - Clarifications needed before implementation
