# Problem Statement: Inheritance-Aware Change Detection

## Task Type
**Type:** feature

## Current State

The codesub tool currently supports semantic subscriptions that track code constructs (classes, methods, fields, etc.) using Tree-sitter parsing. The system can detect when subscribed constructs change through fingerprint-based tracking:

### Existing Semantic Tracking Capabilities

**Construct Indexing** (`src/codesub/semantic/`):
- Python and Java indexers extract constructs from source code
- Each construct has an `interface_hash` (signature/type) and `body_hash` (implementation)
- For classes, the `interface_hash` includes decorators and base classes/inheritance info
  - Python: `/Users/vlad/dev/projects/codesub/src/codesub/semantic/python_indexer.py:457-462` - base classes stored in annotation field
  - Java: `/Users/vlad/dev/projects/codesub/src/codesub/semantic/java_indexer.py:120-138` - superclass and interfaces captured

**Change Detection** (`src/codesub/detector.py`):
- `_check_semantic()` method (lines 388-632) detects changes to subscribed constructs
- `_classify_semantic_change()` method (lines 785-824) classifies changes as STRUCTURAL (interface changed) or CONTENT (body changed)
- Container tracking feature detects member additions, removals, and changes within subscribed classes

**Current Container Tracking** (`src/codesub/models.py:50-70`, `src/codesub/detector.py:634-783`):
- `SemanticTarget` supports `include_members` flag to track all members of a container (class/interface/enum)
- Detects when members are added, removed, renamed, or have their interface/body changed
- Stores baseline fingerprints of members at subscription time
- Triggers with `change_type="AGGREGATE"` when member changes detected

**Inheritance Information Captured**:
- Class definitions already capture base class/superclass information in `interface_hash`
- Python: Stored in `annotation` field via `superclasses` node text
- Java: Stored in `annotation` field combining `superclass` and `interfaces` node text
- Changes to inheritance (e.g., `class Admin(User)` → `class Admin(Person)`) are detected as STRUCTURAL changes to the class itself

### What's Missing

**No Parent-Child Relationship Tracking**:
- The `Construct` dataclass (`src/codesub/semantic/construct.py:8-54`) does NOT store which class is the parent of another class
- While base classes are captured as text in the interface hash, there's no parsed list of parent class names
- No data structure exists to represent the inheritance hierarchy or relationships

**No Transitive Change Detection**:
- When a parent class method is modified, only subscriptions on the parent class are triggered
- Subscriptions on child classes that inherit from the modified parent are NOT notified
- Example scenario that is NOT handled:
  - Subscribe to `Admin.validate()` method
  - `Admin` inherits from `User`
  - User.validate() is modified
  - Admin subscription is NOT triggered, even though Admin.validate() behavior changes

**No Inheritance Graph**:
- The indexers extract constructs as a flat list
- No data structure maps parent classes to their children
- No way to query "what classes inherit from X?"
- No way to traverse up the inheritance chain for a given class

## Desired State

Enable inheritance-aware change detection so that when a parent class changes, subscriptions on child classes that inherit affected members are also triggered.

### Expected Behavior

**Parent Class Changes Should Trigger Child Subscriptions**:
- When a subscribed method/field in a child class is inherited (not overridden) from a parent
- And the parent class version of that member changes
- The child class subscription should be triggered with appropriate change classification

**Parent Class Container Subscriptions**:
- If inheritance relationships can be detected reliably, changes to a parent class container should trigger notifications for child class subscriptions that depend on inherited members
- The user's statement "if there are grounds for detection -- it should work even for parent class" means: if we implement inheritance tracking, then subscribing to a parent class should also notify about impacts on child classes

### Change Detection Flow

The system should:
1. Parse inheritance relationships when indexing constructs
2. Build an inheritance graph mapping parent classes to child classes
3. When detecting changes to a parent class member:
   - Identify child classes that inherit from this parent
   - Check if any subscriptions exist on child classes for inherited members
   - Trigger those child subscriptions with details about the parent class change
4. Classify the change type based on whether the child overrides the member or inherits it

### Data Requirements

To support this, the system needs:
1. **Inheritance metadata in constructs**: Extract parent class names from base class lists
2. **Inheritance graph**: Data structure mapping parents to children across the codebase
3. **Member resolution**: Ability to determine if a child class member is inherited or overridden
4. **Subscription metadata**: Track whether subscribed members are inherited from parents

## Constraints

### Language Support Limitations
- **Python**: Multiple inheritance is possible; must handle MRO (Method Resolution Order)
- **Java**: Single inheritance for classes, multiple interface implementation
- Both languages support method overriding

### Cross-File Inheritance
- Parent and child classes may exist in different files
- Requires full-codebase indexing to build complete inheritance graph
- Current detector caches constructs per-file; may need cross-file indexing strategy

### Performance Considerations
- Building inheritance graph for large codebases could be expensive
- May need incremental updates rather than full reindex on every scan
- Current detector already uses construct caching per language/file

### Scope Boundaries
- Only track direct inheritance relationships (not indirect ancestors initially)
- Only trigger for subscriptions where the child class does NOT override the parent member
- If a child overrides a method, changes to the parent version should NOT trigger child subscription (child has its own implementation)

### Backward Compatibility
- Must not break existing semantic subscriptions
- Inheritance tracking should be opt-in or automatic but non-breaking
- Existing fingerprint-based detection must continue to work

## Acceptance Criteria

- [ ] Parent class information is extracted and stored during construct indexing
- [ ] Inheritance graph can be built from indexed constructs
- [ ] When a parent class method changes, child class subscriptions on that method are triggered (if not overridden)
- [ ] Triggers include metadata indicating the change originated from parent class
- [ ] Works for both Python and Java
- [ ] Container subscriptions on parent classes can optionally trigger for child class impacts
- [ ] Test coverage demonstrates detection across inheritance hierarchies
- [ ] Performance remains acceptable for medium-sized codebases (1000+ files)

## Affected Areas

- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/construct.py` - May need to add parent class list field
- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/python_indexer.py` - Extract parent class names from superclasses node
- `/Users/vlad/dev/projects/codesub/src/codesub/semantic/java_indexer.py` - Extract superclass and interfaces as structured data
- `/Users/vlad/dev/projects/codesub/src/codesub/detector.py` - `_check_semantic()` method needs inheritance-aware logic
- `/Users/vlad/dev/projects/codesub/src/codesub/models.py` - May need new fields in SemanticTarget for inheritance tracking
- New module for inheritance graph management (e.g., `src/codesub/semantic/inheritance.py`)

## User Decisions

Based on user clarification, the following design decisions have been made:

1. **Inheritance depth**: **Full inheritance chain** - Track all ancestors (grandparents, great-grandparents, etc.), not just direct parents.

2. **Overridden members**: **No trigger for overridden methods** - If a child class overrides a method, parent changes to that method should NOT trigger the child subscription (child has its own implementation).

3. **Opt-in behavior**: **Automatic for all semantic subscriptions** - No extra flags needed. Inheritance tracking is always enabled.

4. **Cross-file support**: **Cross-file from the start** - Support inheritance across files using import resolution. This requires analyzing imports to resolve parent class locations.
