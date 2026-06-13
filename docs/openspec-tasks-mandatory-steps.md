---
description: Enforce mandatory steps from openspec/config.yaml when creating tasks.md artifacts and ensure agent executes all manual tests
alwaysApply: true
---

# OpenSpec Tasks: Mandatory Steps Enforcement

When creating or updating `tasks.md` artifacts in OpenSpec changes, you MUST:

## 1. Read openspec/config.yaml First

**BEFORE** creating or updating any `tasks.md` file, you MUST read `openspec/config.yaml` to understand:
- Backend mandatory steps
- Branch naming conventions
- Task structure requirements
- Testing and documentation requirements

## 2. Mandatory Steps

All implementation tasks MUST include these steps in the correct order:

### Step 0: Create Feature Branch (MUST BE FIRST)
- **Location**: Must be the very first step (Step 0)
- **Branch naming**: `feature/[ticket-id]` or `feature/[change-name]`
- **Action**: Create and switch to feature branch before any code changes

### Mandatory Steps (Must Be Included):
- **Step N**: Review and Update Existing Unit Tests (MANDATORY)
- **Step N+1**: Run Unit Tests and Verify Database State (MANDATORY)
- **Step N+2**: Manual Endpoint Testing with curl (MANDATORY) - **AGENT MUST EXECUTE**
- **Step N+3**: E2E Testing (MANDATORY if applicable) - **AGENT MUST EXECUTE**
- **Step N+4**: Update Technical Documentation (MANDATORY)

## 3. Manual Testing Requirements - CRITICAL: Agent Must Execute

**IMPORTANT**: The coding agent (AI) MUST perform all manual testing steps itself. **NEVER delegate testing to the user**. These tests must be executed by the agent to mark tasks as completed in `tasks.md`.

### Step N+1: Run Unit Tests and Verify Database State (MANDATORY)

**Agent Responsibility**: The coding agent MUST execute unit tests, validate database integrity before/after execution, and produce a test report.

**Implementation Steps** (Agent must perform):
1. **Prepare Test Environment**:
   - Ensure required services are available (database via Docker, dependencies installed)
   - Capture pre-test database state relevant to the change (counts, key records)
   - Document the exact test command(s) that will be executed

2. **Run Targeted Unit Tests First**:
   ```bash
   pytest tests/test_<module>.py -v
   ```
   - Execute focused tests for the modified module(s)
   - Confirm failures are resolved and no new regressions appear
   - Capture command output summary (passed/failed/skipped)

3. **Run Broader Unit Test Suite**:
   ```bash
   pytest -v --cov=app
   ```
   - Execute the full project test suite
   - Record total test counts, failures, runtime, and any flaky behavior

4. **Verify Post-Test Database State**:
   - Re-check the same database indicators captured before tests
   - Confirm no unintended mutations remain after tests complete
   - If any mutation occurred, restore state and document the restoration

5. **Create Unit Test Verification Report in Spec Folder**:
   - Save report under the current change folder in `specs/<change-name>/reports/`
   - Filename pattern: `YYYY-MM-DD-step-N+1-unit-test-and-db-verification.md`
   - Include executed commands, summarized results, database pre/post comparison

6. **Mark Task as Completed**: Only after unit tests pass (or approved exceptions are documented), database state is verified/restored, and the report file is created.

**Report Template** (store in `specs/<change-name>/reports/`):
```markdown
# Step N+1 Report - Unit Tests and Database Verification

- Date: YYYY-MM-DD
- Change: <change-name>

## Commands Executed
- `pytest tests/test_<module>.py -v`
- `pytest --cov=app --cov-report=term-missing`

## Unit Test Results
- Targeted tests: X passed, Y failed, Z skipped
- Full suite: X passed, Y failed, Z skipped
- Coverage: X%
- Runtime: <duration>
- Notes: <flaky tests, retries, exceptions>

## Database State Verification
- Pre-test baseline: <metric/table/check>: <value>
- Post-test validation: <metric/table/check>: <value>
- State restored: Yes/No

## Outcome
- Step N+1 status: PASS/FAIL
```

**Dependencies**:
- Python dependencies installed (`pip install -r requirements.txt`)
- Docker running with PostgreSQL container
- Database access for state verification/restoration

**Notes**:
- **The agent MUST execute tests itself** - never ask the user to run tests
- Use `pytest` as the test runner (not Jest, not unittest directly)
- Coverage target: minimum 80%

### Step N+2: Manual Endpoint Testing with curl (MANDATORY)

**Agent Responsibility**: The coding agent MUST execute all curl commands and verify responses.

**Implementation Steps** (Agent must perform):
1. **Prepare Test Environment**:
   - Ensure backend server is running (start via `uvicorn app.main:app --reload` if needed)
   - Verify database connection is active
   - Note current database state (if testing CREATE/UPDATE/DELETE endpoints)

2. **Test GET Endpoints** (if any):
   ```bash
   curl -X GET http://localhost:8000/tickets -H "Authorization: Bearer <token>"
   ```
   - Verify response status code (200, 404, etc.)
   - Verify response body structure and content

3. **Test POST Endpoints** (CREATE operations):
   ```bash
   curl -X POST http://localhost:8000/tickets \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"ticket_description": "test", "priority": "HIGH"}'
   ```
   - Verify response status code (201, 400, 422, etc.)
   - **Restore Database State**: Delete created record after testing
   - Document the curl command, response, and cleanup action

4. **Test PATCH Endpoints** (UPDATE operations):
   - Execute PATCH with updated data
   - Verify response status code (200, 404, 400, etc.)
   - **Restore Database State**: Revert changes after testing

5. **Test DELETE Endpoints**:
   - Execute DELETE
   - Verify response status code (200, 204, 404, etc.)
   - **Restore Database State**: Recreate deleted record after testing

6. **Test Error Cases**:
   - Test with invalid data (validation errors)
   - Test with non-existent resources (404 errors)
   - Test with missing/invalid auth (401 errors)

7. **Mark Task as Completed**: Only after all curl tests pass and database state is restored.

**Notes**:
- This step is MANDATORY for all new endpoints
- **The agent MUST execute all curl commands itself**
- All CREATE/UPDATE/DELETE operations must restore database to original state
- Document all curl commands and responses
- Do not skip manual testing even if unit tests pass

### Step N+3: E2E Testing (MANDATORY if applicable)

**Agent Responsibility**: The coding agent MUST execute E2E tests.

**When This Applies**:
- Frontend changes that affect user workflows
- Integration between frontend and backend endpoints
- User-facing features requiring mobile interaction

**NOTE**: The frontend is a **separate React Native project** in its own repository. E2E testing for mobile features is done in that project using **Detox** or **Maestro**.

**What the agent must do in this repo**:
1. If the change affects the API only (no frontend counterpart), this step can be marked as "N/A" with justification
2. If the change has corresponding frontend work, verify the API contract is correct by:
   - Checking that `api-spec.json` is regenerated and committed
   - Verifying response schemas match expected frontend types

**Dependencies**:
- Backend server running
- Frontend project availability (separate repo)

### Step N+4: Update Technical Documentation (MANDATORY)

Update all affected documentation:
- `docs/api-spec.json` — Re-export via `curl http://localhost:8000/openapi.json -o docs/api-spec.json`
- `docs/data-model.md` — If DB schema changed
- `docs/backend-standards.md` — If patterns/conventions changed
- `docs/development_guide.md` — If setup steps changed

## 4. Verification Checklist

Before finalizing any `tasks.md` file, verify:
- [ ] Step 0 (Create Feature Branch) is the FIRST step
- [ ] All mandatory steps from config.yaml are included
- [ ] Steps are numbered sequentially
- [ ] Mandatory steps are clearly marked with "(MANDATORY)" label
- [ ] Branch naming follows the convention: `feature/[name]`
- [ ] Step N+1 includes report path in `specs/<change-name>/reports/`
- [ ] Manual testing steps explicitly state "AGENT MUST EXECUTE"
- [ ] Tasks include database state restoration steps
- [ ] E2E testing step accounts for separate mobile frontend project

## 5. When This Applies

This rule applies when:
- Creating `tasks.md` via `/opsx:ff` (fast-forward) or `openspec-ff-change` skill
- Creating `tasks.md` via `/opsx:continue` (continue change) or `openspec-continue-change` skill
- Updating existing `tasks.md` files
- Any task creation that involves backend changes
- Implementing tasks from `tasks.md` via `/opsx:apply` or `openspec-apply-change` skill

## 6. Example Structure

```markdown
## 0. Setup: Create Feature Branch (MANDATORY - FIRST STEP)

- [ ] 0.1 Create feature branch `feature/add-ticket-priority` from main
- [ ] 0.2 Verify branch creation and current branch status

## 1. Backend: Add Priority Model/Enum
...

## N. Backend: Review and Update Existing Unit Tests (MANDATORY)
...

## N+1. Backend: Run Unit Tests and Verify Database State (MANDATORY)
- [ ] N+1.1 Capture pre-test database baseline
- [ ] N+1.2 Run targeted unit tests
- [ ] N+1.3 Run full test suite: `pytest --cov=app`
- [ ] N+1.4 Verify post-test database state and restore if needed
- [ ] N+1.5 Create report `specs/<change-name>/reports/YYYY-MM-DD-step-N+1-report.md`

## N+2. Backend: Manual Endpoint Testing with curl (MANDATORY - AGENT MUST EXECUTE)
- [ ] N+2.1 Ensure backend server is running (`uvicorn app.main:app --reload`)
- [ ] N+2.2 Test GET endpoints with curl and verify responses
- [ ] N+2.3 Test POST endpoints, verify creation, then restore database state
- [ ] N+2.4 Test PATCH endpoints, verify updates, then restore database state
- [ ] N+2.5 Test DELETE endpoints, verify deletion, then restore database state
- [ ] N+2.6 Test error cases (validation errors, 404, auth errors)
- [ ] N+2.7 Verify database state matches pre-test state

## N+3. E2E Testing (MANDATORY if applicable - AGENT MUST EXECUTE)
- [ ] N+3.1 Verify API spec is updated (regenerate api-spec.json)
- [ ] N+3.2 Mark as N/A if no frontend counterpart exists
- [ ] (Frontend project handles mobile E2E with Detox/Maestro)

## N+4. Update Technical Documentation (MANDATORY)
- [ ] N+4.1 Regenerate api-spec.json from running server
- [ ] N+4.2 Update data-model.md if schema changed
- [ ] N+4.3 Update backend-standards.md if patterns changed
```

## 7. Agent Execution Requirements

**CRITICAL**: When implementing tasks from `tasks.md`, the coding agent MUST:

1. **Execute All Manual Tests**: Never ask the user to run commands. The agent must:
   - Start servers if needed (`uvicorn app.main:app --reload`)
   - Execute all curl commands for endpoint testing
   - Execute all pytest commands for unit tests
   - Verify all responses and outcomes
   - Restore database state after tests

2. **Mark Tasks as Completed**: Tasks can ONLY be marked as completed (`[x]`) in `tasks.md` AFTER:
   - The agent has successfully executed all required tests
   - All test results have been verified
   - Database state has been restored (for CREATE/UPDATE/DELETE operations)
   - All test outcomes have been documented

3. **Never Delegate Testing**: The agent must never:
   - Ask the user to run pytest or curl commands
   - Ask the user to test endpoints manually
   - Mark tasks as completed without executing tests
   - Skip manual testing steps

4. **Document Test Execution**: The agent must document:
   - All curl commands executed
   - All responses received
   - Database state restoration actions
   - Any issues encountered and resolutions

## Failure to Follow

If you create tasks without following these mandatory steps, the user will need to manually fix the tasks.md file. Always read `openspec/config.yaml` first and ensure all mandatory steps are included.

**If you implement tasks without executing manual tests yourself, you are violating this rule. The agent must execute all tests to mark tasks as completed.**
