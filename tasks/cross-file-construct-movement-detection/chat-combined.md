# External Chat Review - Cross-File Construct Movement Detection

## Instructions

1. Copy the contents of `chat-prompt.md` to your external chat (Claude.ai, ChatGPT, etc.)
2. Attach `chat-context.txt` as a file, OR paste its contents after the prompt
3. Get the review response
4. Save any feedback to this directory

## Files in this directory

```
tasks/cross-file-construct-movement-detection/
├── problem.md          # Problem statement
├── plan.md             # Implementation plan (approved)
├── plan-review.md      # Internal plan review
├── chat-context.txt    # Repomix output with source code (~26k tokens)
├── chat-prompt.md      # Prompt to paste into external chat
├── chat-combined.md    # This file - instructions
└── state.json          # Workflow state
```

## Quick Start

```bash
# Copy prompt to clipboard (macOS)
cat tasks/cross-file-construct-movement-detection/chat-prompt.md | pbcopy

# Or view the files
cat tasks/cross-file-construct-movement-detection/chat-prompt.md
```

## After External Review

If the external LLM provides feedback or suggests changes:

1. Save the response to `external-review.md` in this directory
2. Update `plan.md` if revisions are needed
3. Continue with implementation when ready
