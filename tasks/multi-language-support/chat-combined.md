# Multi-Language Support - External LLM Context

## Instructions

1. Copy the contents of `chat-prompt.md` to your external LLM (Claude.ai, ChatGPT, etc.)
2. Attach or paste the contents of `chat-context.txt` (contains ~28k tokens of source code)
3. Get the implementation plan response
4. Save the response to `tasks/multi-language-support/external-plan.md`
5. Return to Claude Code to compile both plans

## Files in this directory

```
tasks/multi-language-support/
├── chat-context.txt    # Repomix output with source code (28,739 tokens)
├── chat-prompt.md      # Prompt to paste into external LLM
├── chat-combined.md    # This file - instructions
└── external-plan.md    # Save external LLM response here
```

## Quick Copy Commands

```bash
# Copy prompt to clipboard (macOS)
cat tasks/multi-language-support/chat-prompt.md | pbcopy

# Copy context to clipboard (macOS) - may be too large for some clipboards
cat tasks/multi-language-support/chat-context.txt | pbcopy
```

## After Getting External Plan

Once you have the external LLM's plan saved to `external-plan.md`, return to Claude Code and say:

> Compile the ideas from my plan and the external plan in `tasks/multi-language-support/external-plan.md`, then proceed to implementation.

---

## Original Plan (Claude Code)

The plan created by Claude Code is at:
`/Users/vlad/.claude/plans/quizzical-knitting-riddle.md`

Key aspects of the current plan:
- Protocol-based `LanguageIndexer` abstraction
- Registry pattern with `get_indexer(path)` factory
- Self-registration pattern (indexers register themselves at module load)
- Java support: classes, interfaces, enums, fields, methods, constructors
- 4 implementation phases: Foundation, Java Indexer, Integration, Testing
