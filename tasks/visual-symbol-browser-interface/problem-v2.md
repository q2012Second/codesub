# Problem Statement: Code Browser Selection UX Refinement

## Task Type
**Type:** enhancement

## User Request

Improve the code browser selection UX:
1. **Line selection via line numbers only** - Clicking line numbers selects lines, not clicking code
2. **Multi-line selection** - Click line number, shift-click another to select range
3. **Semantic selection via constructs only** - Clicking highlighted constructs selects them
4. **Only highlight trackable constructs** - Don't highlight classes (they can't be tracked)

## Current State

The current `CodeViewerPanel` implementation:
- Clicking anywhere on a row triggers selection
- If clicking a construct's start line, it selects the construct
- If shift-clicking, it selects a line range
- All constructs from the indexer are highlighted, including classes

**Problems:**
1. Confusion between line selection and construct selection (both triggered by row click)
2. Classes are highlighted but can't actually be subscribed to
3. No clear visual distinction between "click here for lines" vs "click here for construct"

## Desired State

Clear separation of selection modes:

**Line Selection (via line number gutter):**
- Click a line number → select that single line
- Shift-click another line number → extend selection to range
- Visual: Line numbers are clearly clickable (hover effect)
- Result: `path:line` or `path:start-end`

**Semantic Selection (via construct spans):**
- Only trackable constructs are highlighted (variables, fields, methods - NOT classes)
- Click on highlighted construct text → select that construct
- Visual: Construct text is highlighted with hover effect
- Result: `path::QualifiedName`

**Non-interaction:**
- Clicking on non-highlighted code does nothing (or clears selection)

## Trackable Constructs

Based on Python indexer behavior, trackable constructs are:
- `variable` - Module-level variables/constants
- `field` - Class fields
- `method` - Class methods and functions

**NOT trackable (should not be highlighted):**
- `class` - Class definitions
- `interface` - Interface definitions
- `enum` - Enum definitions

## Acceptance Criteria

- [ ] Line numbers have hover effect and are clearly clickable
- [ ] Clicking a line number selects that line (shows `path:N`)
- [ ] Shift-clicking a line number extends selection (shows `path:N-M`)
- [ ] Only trackable constructs (variable, field, method) are highlighted
- [ ] Clicking a highlighted construct selects it (shows `path::QualName`)
- [ ] Clicking non-highlighted code clears selection or does nothing
- [ ] Clear visual distinction between line selection and construct selection
