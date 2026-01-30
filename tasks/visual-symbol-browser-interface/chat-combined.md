# How to Use These Files for External Plan Review

## Files Generated

```
tasks/visual-symbol-browser-interface/
├── chat-context.txt    # Repomix output with source code (27k tokens)
├── chat-prompt.md      # Full prompt with plan to review
└── chat-combined.md    # This file - instructions
```

## Usage Instructions

### Option 1: Claude.ai / ChatGPT with File Upload

1. Go to Claude.ai or ChatGPT
2. Upload `chat-context.txt` as an attachment
3. Copy the entire contents of `chat-prompt.md` into the message
4. Send and get the review

### Option 2: Single Message (if context fits)

1. Copy contents of `chat-prompt.md`
2. Add a separator like `---`
3. Copy contents of `chat-context.txt`
4. Paste everything into the chat

### Option 3: API Call

```python
import anthropic

client = anthropic.Anthropic()

with open("chat-context.txt") as f:
    context = f.read()

with open("chat-prompt.md") as f:
    prompt = f.read()

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    messages=[
        {"role": "user", "content": f"{prompt}\n\n---\n\n# Codebase Context\n\n{context}"}
    ]
)
print(message.content[0].text)
```

## After Getting the Review

1. Save the response to `tasks/visual-symbol-browser-interface/external-review.md`
2. Compare with `plan-review.md` (internal review)
3. Address any issues before implementation

## Context Files Included

| File | Purpose | Tokens |
|------|---------|--------|
| `src/codesub/api.py` | API endpoint patterns | 6,116 |
| `src/codesub/cli.py` | CLI symbols command | 5,467 |
| `tests/test_api.py` | Test patterns | 2,615 |
| `src/codesub/models.py` | Data models | 2,565 |
| `frontend/src/components/FileBrowserModal.tsx` | Modal pattern | 1,883 |
| + 8 more files | Types, indexers, etc. | ~8,500 |

**Total: ~27k tokens**
