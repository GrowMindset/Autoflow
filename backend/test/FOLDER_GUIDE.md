# Test Folder

This folder contains automated backend tests.

Files that belong here:
- API tests for auth, workflows, executions, AI, and credentials
- unit tests for node runners and execution helpers
- shared fixtures such as `conftest.py`

Why this folder exists:
- To verify Phase 1, 2, and 3 behavior safely
- To catch regressions before demo or release
- To document expected system behavior through test cases

Recommended improvement:
- Rename this folder from `test` to `tests` to follow standard Python project convention.

Do not put here:
- production application code
- migration files
- local scratch scripts

