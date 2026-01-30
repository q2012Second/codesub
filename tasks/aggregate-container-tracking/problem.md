# Problem Statement: Aggregate/Container Tracking

## Task Type
**Type:** feature

## Current State

Codesub currently supports two types of subscriptions:

### Line-based subscriptions
Track specific line ranges in files (e.g., `config.py:10-25`). Changes trigger when:
- Hunks overlap the watched line range
- Pure insertions occur within the range (between start and end lines)
- The file is deleted

### Semantic subscriptions
Track individual code constructs by identity (e.g., `auth.py::User.validate`, `config.py::MAX_RETRIES`). The system uses Tree-sitter parsing to extract constructs from source code.

**Supported construct kinds:**
- Python: `variable`, `field`, `method`, `class`, `interface`, `enum`
- Java: `variable`, `field`, `method`, `class`, `interface`, `enum`

**Current indexing behavior:**
The semantic indexer extracts ALL constructs from a file, including all members of classes and enums. For example, indexing `models.py` containing a `User` class extracts:
- `User.id` (field)
- `User.email` (field)
- `User.name` (field)
- `User.validate` (method)

**Current subscription granularity:**
Users can only subscribe to ONE construct at a time. To monitor all members of a class like `User`, they must create separate subscriptions for each field and method:
- `models.py::User.id`
- `models.py::User.email`
- `models.py::User.name`
- `models.py::User.validate`

This is tedious and error-prone, especially for large classes or enums.

**Detection mechanism (per subscription):**
The detector (`/Users/vlad/dev/projects/codesub/src/codesub/detector.py`) performs semantic change detection:
1. Parses the target file at baseline and HEAD
2. Looks for the subscribed construct by qualname and fingerprint hashes
3. Classifies changes as:
   - `STRUCTURAL`: interface_hash changed (type/signature)
   - `CONTENT`: body_hash changed (value/implementation)
   - `MISSING`: construct not found

**Data model:**
The `Subscription` model (`/Users/vlad/dev/projects/codesub/src/codesub/models.py`) has:
- `path`: file path
- `start_line`, `end_line`: line range
- `semantic`: optional `SemanticTarget` with language, kind, qualname, hashes
- `trigger_on_duplicate`: boolean flag (triggers when construct found in multiple files)

## Desired State

Users should be able to subscribe to a **container construct** (class, enum, module) and automatically track ALL its members, triggering when ANY member changes.

**Target syntax:**
```bash
codesub add models.py::User --include-members
codesub add types.py::OrderStatus --include-members
```

**Trigger behavior:**
When scanning, if ANY member of the container has changed, the subscription triggers. The trigger details should report:
- Which specific members changed (qualnames)
- The type of change for each member (STRUCTURAL, CONTENT, MISSING)
- Any new members added since baseline
- Container-level changes (e.g., class renamed, decorators changed)

**Change categories to detect:**

1. **Member modifications:**
   - Field type changed: `User.email: str` → `User.email: str | None` (STRUCTURAL)
   - Field value changed: `User.region = "US-CA"` → `User.region = "EU-DE"` (CONTENT)
   - Method signature changed: `validate(self)` → `validate(self, strict: bool)` (STRUCTURAL)
   - Method body changed: implementation logic updated (CONTENT)

2. **Member additions:**
   - New field added: `User.phone_number: str`
   - New method added: `User.archive()`

3. **Member removals:**
   - Field deleted: `User.region` removed (MISSING)
   - Method deleted: `User.validate` removed (MISSING)

4. **Container-level changes:**
   - Class renamed: `class User` → `class UserAccount`
   - Decorators changed: `@dataclass` → `@dataclass(frozen=True)`
   - Inheritance changed: `class User` → `class User(BaseModel)`

5. **Cross-file movement:**
   - Entire class moved to different file (handled by existing cross-file detection)

**Output format (trigger details):**
```json
{
  "change_type": "AGGREGATE",
  "container_qualname": "User",
  "container_changes": {
    "renamed": false,
    "decorators_changed": false,
    "inheritance_changed": false
  },
  "member_changes": [
    {
      "qualname": "User.email",
      "kind": "field",
      "change_type": "STRUCTURAL",
      "old_hash": "abc123",
      "new_hash": "def456"
    },
    {
      "qualname": "User.phone_number",
      "kind": "field",
      "change_type": "ADDED"
    }
  ],
  "members_removed": ["User.region"],
  "members_added": ["User.phone_number"]
}
```

## Constraints

**Technical constraints:**

1. **Backward compatibility:** Existing single-construct semantic subscriptions must continue to work unchanged. The `include_members` flag is optional.

2. **Language support:** Must work for all languages currently supported by semantic subscriptions (Python, Java).

3. **Performance:** For large classes (50+ members), the scan should not become prohibitively slow. Construct indexing is already cached per file during a scan.

4. **Fingerprint stability:** Member fingerprints (interface_hash, body_hash) must remain stable for unchanged members to avoid false positives.

5. **Line range tracking:** Container subscriptions still need `start_line` and `end_line` for:
   - Display purposes (showing where the container is)
   - Update proposals when container moves
   - Anchor extraction for context

**Semantic constraints:**

1. **Container definition:** Only certain construct kinds can be containers:
   - Python: `class`, `enum` (can have members)
   - Java: `class`, `interface`, `enum`
   - NOT: `variable`, `field`, `method` (these ARE members, not containers)

2. **Member definition:** What qualifies as a "member"?
   - For classes: fields and methods (including static, class, property)
   - For enums: enum constants/values
   - Nested classes are members
   - Module-level items are NOT members of the module

3. **Trigger semantics:** Should trigger if:
   - ANY member has STRUCTURAL or CONTENT change
   - ANY member is MISSING (removed)
   - ANY new member is ADDED
   - Container itself has structural changes (rename, decorators, inheritance)

4. **Unchanged containers:** If the container and all its members are unchanged (only cosmetic changes like whitespace), the subscription should remain in `unchanged`, not trigger.

**UI/UX constraints:**

1. **CLI clarity:** The `--include-members` flag should be clearly documented in `codesub add --help`.

2. **Listing:** `codesub list` should indicate when a subscription is aggregate/container-based.

3. **Symbols command:** `codesub symbols` should continue to list individual constructs, but potentially add a flag to show "containable" constructs.

## Acceptance Criteria

- [ ] Users can create container subscriptions with `codesub add path::Container --include-members`
- [ ] Container subscriptions trigger when ANY member changes (STRUCTURAL, CONTENT, MISSING, or ADDED)
- [ ] Trigger details include a list of specific members that changed, with their change types
- [ ] Container subscriptions do NOT trigger for unchanged containers (even if scanned)
- [ ] Existing single-construct semantic subscriptions continue to work unchanged
- [ ] The `include_members` flag is optional and defaults to `false` (current behavior)
- [ ] API endpoint `POST /api/subscriptions` accepts `include_members` parameter
- [ ] Subscription JSON schema includes `include_members: bool` field
- [ ] Attempting to use `--include-members` on a non-container construct (field, method) returns clear error
- [ ] Container subscriptions work for both Python and Java
- [ ] Update proposals correctly update line ranges when containers move in the file
- [ ] Cross-file movement detection works for containers with members

## Affected Areas

**Core detection logic:**
- `/Users/vlad/dev/projects/codesub/src/codesub/detector.py` - `_check_semantic()` method needs container-aware logic
- `/Users/vlad/dev/projects/codesub/src/codesub/models.py` - `Subscription` model needs `include_members` field
- `/Users/vlad/dev/projects/codesub/src/codesub/models.py` - `Trigger` details format for aggregate changes

**Subscription creation:**
- `/Users/vlad/dev/projects/codesub/src/codesub/cli.py` - `cmd_add()` needs `--include-members` flag
- `/Users/vlad/dev/projects/codesub/src/codesub/cli.py` - `_add_semantic_subscription()` validation for container kinds
- `/Users/vlad/dev/projects/codesub/src/codesub/api.py` - `SubscriptionCreateRequest` schema

**Semantic indexing:**
- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/python_indexer.py` - May need helper to get all members of a container
- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/java_indexer.py` - May need helper to get all members of a container
- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/indexer_protocol.py` - Consider adding `get_container_members()` protocol method

**Display and formatting:**
- `/Users/vlad/dev/projects/codesub/src/codesub/utils.py` - `format_subscription()` should show container status
- `/Users/vlad/dev/projects/codesub/src/codesub/update_doc.py` - Formatting of aggregate trigger details

**Tests:**
- New test file: `tests/test_container_subscriptions.py`
- Integration tests for Python and Java container tracking
- Edge cases: empty classes, single-member enums, nested classes

## Questions

1. **Granularity of "new member" detection:** Should adding a new member always trigger, or only if it's a "public" member (not starting with `_` in Python)?

2. **Decorators on members:** If a method decorator changes (e.g., `@property` → `@staticmethod`), should this be considered a STRUCTURAL change at the member level, or should it trigger at the container level as a "member role changed"?

3. **Nested classes:** If a class contains a nested class, should the nested class be considered a "member" for aggregate tracking? Or should nested classes require their own subscription?

4. **Module-level aggregation:** Should we support `--include-members` for an entire module/file (tracking all top-level constructs)? Or is this scope creep?

5. **Baseline member snapshot:** Should we store the list of member qualnames at subscription creation time, or dynamically discover them at scan time? Storing at creation allows detection of "new members added", but makes the subscription data larger.

6. **Partial matching:** If a class has 20 members and only 1 changed, should the trigger report all 20 members (with 19 marked "unchanged") or only the 1 that changed? The former is more informative but verbose.

---

## File References

All file paths referenced in this document are absolute paths within the project:
- `/Users/vlad/dev/projects/codesub/src/codesub/models.py` - Data models
- `/Users/vlad/dev/projects/codesub/src/codesub/detector.py` - Change detection logic
- `/Users/vlad/dev/projects/codesub/src/codesub/cli.py` - CLI interface
- `/Users/vlad/dev/projects/codesub/src/codesub/api.py` - REST API
- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/python_indexer.py` - Python construct extraction
- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/java_indexer.py` - Java construct extraction
- `/Users/vlad/dev/projects/codesub/src/codesub/utils.py` - Utility functions
- `/Users/vlad/dev/projects/codesub/src/codesub/update_doc.py` - Update document generation
