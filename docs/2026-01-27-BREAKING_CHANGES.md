# Breaking Changes - API Cleanup (2026-01-27)

## Overview

This release includes significant API cleanup to improve consistency and reduce code duplication. The primary changes involve removing module-level wrapper functions in favor of using client classes directly.

## Breaking Changes

### 1. Module-level convenience functions removed

All module-level wrapper functions in `*.client` modules have been removed. These were thin wrappers that simply instantiated a client class and called a method.

#### Albert (`edubag.albert.client`)

**Removed functions:**
- `edubag.albert.client.authenticate()`
- `edubag.albert.client.fetch_and_save_rosters()`
- `edubag.albert.client.fetch_class_details()`

**Migration:**

```python
# Old code (BROKEN):
from edubag.albert.client import authenticate, fetch_and_save_rosters

authenticate(username="user", password="pass", headless=True)
paths = fetch_and_save_rosters("MATH-UA 120", "Spring 2026")

# New code:
from edubag.albert.client import AlbertClient

client = AlbertClient()
client.authenticate(username="user", password="pass", headless=True)
paths = client.fetch_and_save_rosters("MATH-UA 120", "Spring 2026")
```

#### Brightspace (`edubag.brightspace.client`)

**Removed functions:**
- `edubag.brightspace.client.authenticate()`
- `edubag.brightspace.client.save_gradebook()`
- `edubag.brightspace.client.save_attendance()`

**Migration:**

```python
# Old code (BROKEN):
from edubag.brightspace.client import authenticate, save_gradebook

authenticate(username="user", password="pass", headless=True)
paths = save_gradebook(course="555872", save_dir="./data")

# New code:
from edubag.brightspace.client import BrightspaceClient

client = BrightspaceClient()
client.authenticate(username="user", password="pass", headless=True)
paths = client.save_gradebook(course="555872", save_dir="./data")
```

#### Gradescope (`edubag.gradescope.client`)

**Removed functions:**
- `edubag.gradescope.client.authenticate()`
- `edubag.gradescope.client.sync_roster()`
- `edubag.gradescope.client.fetch_class_details()`
- `edubag.gradescope.client.save_roster()`

**Migration:**

```python
# Old code (BROKEN):
from edubag.gradescope.client import authenticate, save_roster

authenticate(username="user", password="pass", headless=True)
path = save_roster(course="12345", save_dir="./data")

# New code:
from edubag.gradescope.client import GradescopeClient

client = GradescopeClient()
client.authenticate(username="user", password="pass", headless=True)
path = client.save_roster(course="12345", save_dir="./data")
```

## Non-Breaking Changes

### 1. New base class for all LMS clients

All client classes now inherit from `edubag.clients.LMSClient`, which provides:
- A consistent interface across all clients
- Abstract method signatures for `authenticate()` and `_default_auth_state_path()`
- Comprehensive documentation about the `headless` parameter behavior

### 2. Enhanced documentation

All client classes now have expanded docstrings that explain:
- The purpose of the client
- The rationale for `headless` parameter defaults:
  - `authenticate()` defaults to `False` (headed) - interactive login with MFA
  - Other operations default to `True` (headless) - automated operations

### 3. CLI commands unchanged

**Important:** The CLI interface remains unchanged. All `edubag` commands work exactly as before:

```bash
# These commands still work:
edubag albert client authenticate
edubag brightspace client save-gradebook 555872
edubag gradescope client save-roster 12345
```

## Rationale

This cleanup achieves several goals:

1. **Reduced API surface**: Fewer functions to document and maintain
2. **Clearer separation of concerns**: 
   - Use client classes for programmatic access
   - Use CLI commands for command-line operations
3. **Consistency**: All platforms follow the same pattern
4. **Simplified maintenance**: One less layer of indirection to update

## Timeline

- **Breaking change introduced:** 2026-01-27
- **Branch:** `2026-01-27-cleanup`
- **Recommended action:** Update any scripts that import module-level functions to use client classes directly

## Questions?

If you need help migrating your code, please file an issue on GitHub.
