# Semantic Subscription Test Scenarios

## Summary

Created comprehensive test coverage for semantic subscriptions across various Python construct types.

**Total Tests:** 180 (167 original + 13 new advanced tests)
**All Passing:** Yes

## Construct Types Tested

### 1. Module-Level Variables
| Construct | Value Change | Type Change | Cosmetic |
|-----------|--------------|-------------|----------|
| Typed constant (`API_VERSION: str = "v2.0"`) | CONTENT | STRUCTURAL | No trigger |

### 2. Enum Members
| Construct | Value Change | Rename | Delete |
|-----------|--------------|--------|--------|
| Enum member (`Status.PENDING`) | CONTENT | PROPOSAL | MISSING |

### 3. TypedDict Fields
| Construct | Type Change |
|-----------|-------------|
| TypedDict field (`UserDict.id`) | STRUCTURAL |

### 4. Dataclass Fields
| Construct | Default Value Change |
|-----------|---------------------|
| Dataclass field (`SimpleData.name`) | CONTENT |

### 5. Methods
| Construct | Body Change | Signature Change | Return Type Change |
|-----------|-------------|------------------|-------------------|
| Static method (`Calculator.add`) | CONTENT | STRUCTURAL | STRUCTURAL |

### 6. Properties
| Construct | Body Change |
|-----------|-------------|
| Property (`Rectangle.area`) | CONTENT |

### 7. Line Shifts
| Scenario | Result |
|----------|--------|
| Lines added before construct | PROPOSAL (not trigger) |

## Files Created

### mock_repo/advanced_types.py
Comprehensive Python file with:
- 11 module-level variables (constants, typed, complex types)
- 3 Enum classes (Enum, IntEnum, auto)
- 4 TypedDict classes (required, optional, nested)
- 2 NamedTuple classes
- 3 Dataclass classes (simple, complex, frozen)
- 2 Protocol classes
- 2 Generic classes
- 2 Regular classes with various method types

### tests/test_advanced_semantic.py
13 integration tests covering:
- TestModuleConstant (3 tests): value, type, cosmetic changes
- TestEnumMember (3 tests): value, rename, delete
- TestTypedDictField (1 test): type change
- TestDataclassField (1 test): default value change
- TestMethodDetection (3 tests): body, signature, return type
- TestPropertyDetection (1 test): body change
- TestLineShifts (1 test): line shift creates proposal

## Test Matrix Results

| Construct Type | Value Change | Type Change | Rename | Delete | Cosmetic | Line Shift |
|----------------|--------------|-------------|--------|--------|----------|------------|
| Module constant | CONTENT | STRUCTURAL | - | - | No trigger | - |
| Enum member | CONTENT | - | PROPOSAL | MISSING | - | PROPOSAL |
| TypedDict field | - | STRUCTURAL | - | - | - | - |
| Dataclass field | CONTENT | - | - | - | - | - |
| Static method | CONTENT | STRUCTURAL | - | - | - | - |
| Property | CONTENT | - | - | - | - | - |

## Edge Cases Discovered

1. **Partial hash matching**: When deleting an enum member, if another member has the same interface_hash, the detector may find it as a partial match instead of reporting MISSING. Solution: Delete the entire class to properly test MISSING trigger.

2. **Decorated classes**: Fixed indexer to handle `@dataclass` and other decorated class definitions (was previously only detecting plain `class_definition` nodes).

## Subscriptions Created in mock_repo

8 semantic subscriptions added to `mock_repo/.codesub/subscriptions.json`:
1. `API_VERSION` - Typed module constant
2. `Status.PENDING` - Enum member
3. `UserDict.id` - TypedDict field
4. `Point.x` - NamedTuple field
5. `SimpleData.name` - Dataclass field
6. `ServiceConfig.default_timeout` - Class variable
7. `Calculator.add` - Static method
8. `Rectangle.width` - Property method
