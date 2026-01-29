# Context for Semantic Subscriptions Implementation

## Research Documents

### tasks/semantic_subscriptions_research.md
- Problem reformulation: line-based subscriptions are fragile
- Desired: track semantic constructs (classes, functions, variables)
- Comparison of approaches: Tree-sitter + Fingerprinting recommended
- Multi-hash fingerprinting: interface_hash, body_hash, body_hash_normalized, doc_hash

### tasks/semantic/review.md
- External LLM research on semantic tracking
- Recommends Tree-sitter for parsing (robust error recovery)
- Multi-stage matching pipeline: exact → rename-resistant → move detection → fuzzy
- Construct schema: kind, name, container, qualname, range, hashes, parse_quality
- Change classification: structural, content, cosmetic, location

### research/semantic-code-parsing.md
- Detailed tool comparisons and code examples
- Tree-sitter queries for Python constructs
- Fingerprinting implementation strategies

## Existing Codebase

### src/codesub/models.py
Current models:
- `Subscription`: path, start_line, end_line, label, description, anchors, active
- `Anchor`: context_before, lines, context_after
- `Trigger`: subscription_id, path, reasons, matching_hunks
- `Proposal`: subscription_id, old/new path/start/end, reasons, confidence, shift
- `ScanResult`: triggers, proposals, unchanged

### src/codesub/detector.py
Current detection:
- Uses git diff hunks to detect overlaps with line ranges
- Calculates line shifts for non-triggered subscriptions
- Returns Trigger for overlaps, Proposal for shifts/renames

### src/codesub/cli.py
Commands:
- init, add, list, remove, scan, apply-updates, serve
- projects: list, add, remove
- scan-history: clear

### src/codesub/api.py
REST endpoints for subscriptions, projects, scans, apply-updates

## Key Integration Points

1. **Subscription Model**: Add optional `semantic_target` field
2. **Detector**: Add semantic-aware detection alongside line-based
3. **CLI**: New command to add semantic subscription (`codesub add-semantic`)
4. **API**: New endpoint for semantic subscriptions

## Dependencies to Add

- `tree-sitter` - Core parsing library
- `tree-sitter-python` - Python grammar
- (future) `tree-sitter-java`, `tree-sitter-go`
