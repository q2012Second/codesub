# Problem Statement: Frontend Support for Aggregate Subscriptions and Configurations

## Task Type
**Type:** feature

## Current State

The frontend subscription creation interface currently supports two subscription types:
1. **Line-based subscriptions**: Track specific line ranges (e.g., `config.py:10-25`)
2. **Semantic subscriptions**: Track individual code constructs by identity (e.g., `auth.py::User.validate`)

### Current Implementation

**Location**: `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionForm.tsx`
- Form accepts a `location` string input field
- Supports visual code browsing via `CodeBrowserModal` component
- Only sends `location`, `label`, `description`, and `context` fields to the API
- No UI for subscription configuration options

**Code Browser**: `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeViewerPanel.tsx`
- Displays file content with line numbers for line selection
- Shows semantic constructs (variables, fields, methods) as clickable highlights
- Only supports selecting **individual constructs** - filters to `TRACKABLE_KINDS = ['variable', 'field', 'method']`
- Does not display or allow selection of container types (classes, enums, interfaces)

**Frontend API Client**: `/Users/vlad/dev/projects/codesub/frontend/src/api.ts`
- `createProjectSubscription()` sends `SubscriptionCreateRequest` with only basic fields

**Frontend Types**: `/Users/vlad/dev/projects/codesub/frontend/src/types.ts`
- `SubscriptionCreateRequest` interface only has: `location`, `label`, `description`, `context`
- `SemanticTarget` interface does not include container tracking fields

### Backend Already Supports

**API Schema** (`/Users/vlad/dev/projects/codesub/src/codesub/api.py` lines 86-113):
- `SubscriptionCreateRequest` includes:
  - `trigger_on_duplicate: bool` (default: False) - Alert if construct found in multiple files
  - `include_members: bool` (default: False) - Track all members of container
  - `include_private: bool` (default: False) - Include private members (_prefixed)
  - `track_decorators: bool` (default: True) - Track decorator changes on container

**Container Support** (`/Users/vlad/dev/projects/codesub/src/codesub/models.py` lines 19-23):
- Python: `class`, `enum`
- Java: `class`, `interface`, `enum`

**API Behavior**:
- When `include_members=True`, backend validates that the construct is a container type
- Backend indexes all members at baseline and tracks additions, deletions, and changes
- Backend stores member fingerprints in `baseline_members` dict with relative IDs

## Desired State

The frontend should enable users to:

1. **Select container types visually** - Users should be able to browse and select classes, enums, and interfaces in the code browser, not just individual members

2. **Configure aggregate subscriptions** - When subscribing to a container type, users should see configuration options to:
   - Enable "Track all members" mode (`include_members`)
   - Choose whether to include private members (`include_private`, Python only)
   - Choose whether to track decorator changes (`track_decorators`)

3. **Configure duplicate detection** - For all semantic subscriptions, users should be able to enable duplicate detection (`trigger_on_duplicate`)

4. **See configuration in subscription details** - The subscription list and detail views should display which configuration options are enabled

## Constraints

- **Backward compatibility**: Existing subscriptions without these flags should continue to work (backend defaults all flags to `False` except `track_decorators=True`)
- **Language awareness**: `include_private` option should only be shown for Python files
- **Container validation**: Frontend should only offer "Track all members" option when the selected construct is a valid container type for the language
- **UI simplicity**: Configuration options should be presented clearly without overwhelming users with too many choices
- **Type safety**: TypeScript interfaces must align with backend Pydantic schemas

## Acceptance Criteria

- [ ] Frontend `SubscriptionCreateRequest` type includes `trigger_on_duplicate`, `include_members`, `include_private`, and `track_decorators` fields
- [ ] Frontend `SemanticTarget` type includes container tracking fields matching backend schema
- [ ] Code browser (`CodeViewerPanel`) displays and allows selection of container types (class, enum, interface) in addition to individual constructs
- [ ] Subscription form shows configuration checkboxes when creating a semantic subscription:
  - [ ] "Trigger on duplicate" checkbox for all semantic subscriptions
  - [ ] "Track all members" checkbox for container types only
  - [ ] "Include private members" checkbox (visible only when "Track all members" enabled AND language is Python)
  - [ ] "Track decorator changes" checkbox (visible only when "Track all members" enabled)
- [ ] Configuration options are sent to the backend API when creating a subscription
- [ ] Subscription list shows visual indicators for subscriptions with `include_members=True`
- [ ] Subscription detail view displays active configuration options
- [ ] Form validation prevents enabling "Track all members" for non-container constructs
- [ ] All TypeScript types are correctly aligned with backend schemas

## Affected Areas

- `/Users/vlad/dev/projects/codesub/frontend/src/types.ts` - Type definitions
- `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionForm.tsx` - Form with configuration checkboxes
- `/Users/vlad/dev/projects/codesub/frontend/src/components/CodeViewerPanel.tsx` - Container type selection support
- `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionList.tsx` - Display configuration indicators
- `/Users/vlad/dev/projects/codesub/frontend/src/components/SubscriptionDetail.tsx` - Show active configurations
- `/Users/vlad/dev/projects/codesub/frontend/src/api.ts` - API client (minor updates if needed)

## Questions

None - requirements are clear based on backend implementation.
