## 1. Test Factories

- [ ] 1.1 Create `tests/factories.py` with factory_boy factories for FSMUser, Technician, Spare, Market, Equipment, Labsdl
- [ ] 1.2 Add factories for Ticket, AddWkd, Maintenance, Cancellation, Pause
- [ ] 1.3 Add factories for Photo, Worksheet, UploadSession, TokenBlacklist
- [ ] 1.4 Add factories for association models: MaintenanceTechnician, MaintenanceSpare
- [ ] 1.5 Add any missing fixtures to `tests/conftest.py` needed by test files (e.g., reference data fixtures for markets, equipment, technicians)

## 2. Ticket API Tests

- [ ] 2.1 Create `tests/test_tickets.py` with tests for POST /tickets (create: 201, 401, 422)
- [ ] 2.2 Add tests for GET /tickets (list: 200, 401) and GET /tickets/{id} (get: 200, 401, 404)
- [ ] 2.3 Add tests for PATCH /tickets/{id}/assign (assign: 200, 401, 404, 400 for invalid state)
- [ ] 2.4 Add tests for PATCH /tickets/{id}/start (start: 200, 401, 400 for invalid state)
- [ ] 2.5 Add tests for PATCH /tickets/{id}/cancel (cancel: 200, 401, 400)
- [ ] 2.6 Add tests for PATCH /tickets/{id}/addwkd (addwkd: 200, 401) and DELETE /tickets/{id} (delete: 204, 401)

## 3. Maintenance API Tests

- [ ] 3.1 Create `tests/test_maintenances.py` with tests for POST /maintenances (create: 201, 401, 422)
- [ ] 3.2 Add tests for GET /maintenances (list: 200, 401) and GET /maintenances/{id} (get: 200, 401, 404)
- [ ] 3.3 Add tests for PATCH /maintenances/{id} (update: 200, 401, 404, 422)
- [ ] 3.4 Add tests for PATCH /maintenances/{id}/pause (pause: 200, 401, 404) and DELETE /maintenances/{id} (delete: 204, 401)

## 4. Upload API Tests

- [ ] 4.1 Create `tests/test_uploads.py` with tests for POST /uploads/init (init: 201, 401, 422)
- [ ] 4.2 Add tests for POST /uploads/chunk (chunk: 200, 401, 404, 422)
- [ ] 4.3 Add tests for GET /uploads/status/{upload_id} (status: 200, 401, 404)
- [ ] 4.4 Add tests for POST /uploads/complete (complete: 200, 401, 404)

## 5. Worksheet API Tests

- [ ] 5.1 Create `tests/test_worksheets.py` with tests for GET /maintenances/{id}/worksheet (get or create: 200, 401, 404)
- [ ] 5.2 Add tests for PATCH /maintenances/{id}/worksheet (update: 200, 401, 404, 422)
- [ ] 5.3 Add tests for POST /maintenances/{id}/worksheet/generate-pdf (generate: 200, 401, 404)

## 6. Verification

- [ ] 6.1 Run the full test suite.
- [ ] 6.2 Identify the tests failuress and classify them in: a. genuine bug b. requirements recently changed c. test poorly written
- [ ] 6.3 Prepare creation of a ticket (required solution to development team) for each test failure into category a. genuine bug. 
- [ ] 6.4 Create each ticket in the folder openspec/pre_propossals in jira format: (Summary — the title/one-liner of the ticket. Issue Type — Story, Bug, Task, Epic, Subtask. Project — which project it belongs to. Optionals: Description, Assignee, Priority, Story Points-Estimate, Sprint, Epic Link, Labels-Components, Reporter). 
- [ ] 6.5 If there are not test with failures, run tests with coverage (`pytest --cov=app --cov-report=term-missing`) and verify routes coverage is >= 80%
