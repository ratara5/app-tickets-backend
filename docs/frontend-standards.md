---
description: Frontend development standards, best practices, and conventions for the React Native application including component patterns, state management, UI/UX guidelines, and testing practices. NOTE: This is a SEPARATE project from this backend repo.
globs: []  # This is a separate project — no globs in the backend repo
alwaysApply: true
---

# Frontend Standards (React Native — Separate Project)

> **IMPORTANT**: The frontend is a **separate React Native project** in its own repository.
> This file serves as a reference for the API contract and integration points between
> the backend (this repo) and the mobile frontend. The full frontend standards and
> conventions belong in the frontend project's own documentation.

## Overview

The frontend is a **React Native** application that communicates with this backend via REST API following the contract defined in `docs/api-spec.yml` (or `docs/api-spec.json`).

## Technology Stack (Frontend Project)

### Core Technologies
- **React Native**: Cross-platform mobile framework (iOS + Android)
- **TypeScript**: Type safety
- **React Navigation**: Screen routing and navigation
- **Axios** or **React Query**: HTTP client for API communication

### State Management
- **React Context** or **Zustand** for global state
- **AsyncStorage** or **MMKV** for persistent local storage
- **React Query** for server state caching and synchronization

### UI Framework
- **React Native** built-in components
- Custom component library or community UI kits (e.g., NativeBase, Tamagui, or Gluestack)
- **Styled Components** or **Tailwind CSS for RN** for styling

### Testing
- **Jest**: Unit testing
- **React Native Testing Library**: Component testing
- **Detox** or **Maestro**: End-to-end testing

## API Integration

### Contract
- The frontend consumes the API contract defined in `docs/api-spec.yml`
- Both projects must stay in sync with this spec
- When the API changes (new endpoints, modified schemas), regenerate `api-spec.json` from the running backend and commit it

### Authentication
- Obtain JWT token via `POST /auth/login`
- Store token securely (e.g., `expo-secure-store` or `react-native-keychain`)
- Send token in `Authorization: Bearer <token>` header for all protected requests
- Handle 401 responses by redirecting to login

### Key Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /auth/login | Login -> JWT |
| GET | /tickets | List tickets |
| GET | /tickets/{id} | Ticket details |
| POST | /tickets | Create ticket |
| PATCH | /tickets/{id} | Update ticket |
| POST | /tickets/{id}/cancel | Cancel ticket |
| GET | /maintenances/{id} | Maintenance details |
| POST | /maintenances | Create maintenance |
| POST | /uploads | Chunked file upload |
| POST | /worksheets/{id}/generate | Generate PDF worksheet |

## Coding Standards

### Naming Conventions
- **Components**: `PascalCase` (`TicketCard.tsx`, `MaintenanceDetail.tsx`)
- **Hooks**: `camelCase` with `use` prefix (`useTickets`, `useAuth`)
- **Services**: `camelCase` (`ticketService`, `authService`)
- **Types/Interfaces**: `PascalCase` (`Ticket`, `Maintenance`, `ApiResponse<T>`)
- **Files**: PascalCase for components, camelCase for utilities

### TypeScript
- **Strict mode** enabled
- Define types for all API responses (match Pydantic schemas from the backend)
- Use `zod` or similar for runtime validation of API responses

### Error Handling
- Wrap API calls in try/catch with user-friendly error messages
- Handle network connectivity issues gracefully (offline mode, retry)
- Show appropriate loading states (skeleton screens, spinners) during API calls

## Communication with Backend

### Synchronization
1. Backend changes the API → regenerate `api-spec.json` → commit to backend repo
2. Frontend team reviews the spec change → updates API client code
3. Both projects maintain independent versioning and CI/CD

### File Uploads
- Backend supports chunked uploads via MinIO
- Frontend uploads files in chunks, tracks progress
- Images are accessed via MinIO presigned URLs (not proxied through the API)

### PDF Generation
- Backend generates PDF worksheets via WeasyPrint + Jinja2 templates
- Frontend requests generation via API, receives a PDF URL
- PDF is displayed/stored using the presigned URL

## Network Security

- All API calls should use HTTPS in production
- JWT tokens stored in secure device storage (Keychain on iOS, Keystore on Android)
- Implement certificate pinning for production builds
- Add request/response timeout handling

## Development Workflow

- The frontend project follows its own branching and release strategy
- Coordinate with backend when consuming new API features
- Use `docs/api-spec.yml` as the single source of truth for the API contract
- When the API spec changes, update the frontend's API client code and types
