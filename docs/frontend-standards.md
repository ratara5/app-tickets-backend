---
description: Frontend development standards for the Expo React Native mobile app that integrates with the current FastAPI backend project. This document reflects the actual architecture and API contract used by the app-tickets backend.
globs: []
alwaysApply: true
---

# Frontend Standards (React Native / Expo)

> **IMPORTANT**: The frontend is a separate Expo React Native project that lives beside this backend repository. This file captures the integration rules and conventions for the current backend implementation.

## Overview

The frontend is a mobile application that communicates with this backend through REST JSON endpoints. The current backend contract is defined by the OpenAPI files in the backend repo and implemented in the FastAPI routes under app/api/routes.

## Current Stack

### Core Technologies
- **Expo**: Fast mobile app development and Android/iOS workflow
- **React Native**: Cross-platform mobile UI
- **TypeScript**: Strict typing for screens, state, and API payloads
- **React Navigation**: Native stack and bottom tabs
- **Zustand**: Lightweight global state for auth and app state
- **TanStack Query**: Server-state caching and synchronization when needed
- **Axios**: HTTP client for REST calls
- **Expo Secure Store**: Secure token persistence

### Project Layout
- **src/app**: navigation shell and app bootstrap
- **src/features/**: feature-specific screens and UI modules
- **src/shared/**: shared API client, storage helpers, and utilities
- **src/stores/**: Zustand stores
- **src/types/**: generated API types and local type aliases
- **src/mocks/**: mock data for UI development and offline prototyping

## API Integration Rules

### Source of Truth
- Use the backend OpenAPI contract from the backend repo as the authoritative contract.
- Prefer the generated types in the frontend project rather than ad-hoc interfaces.
- When backend endpoints or schema fields change, update the frontend types and screens accordingly.
- The above, implies a comparison between backend-/docs/api-spec.json and frontend-/docs/api-spec.json. If there are changes, types/api and types/types must be updated in frontend. 

### Authentication Flow
- Use `POST /auth/login` and `POST /auth/register` for authentication.
- Store JWTs securely using Expo Secure Store.
- Send the token in the `Authorization: Bearer <token>` header for protected requests.
- Handle 401 responses by clearing auth state and redirecting to login.

### Current Backend Endpoints

| Area | Endpoint | Purpose |
|---|---|---|
| Auth | `POST /auth/login` | Sign in |
| Auth | `POST /auth/register` | Create account |
| Auth | `POST /auth/logout` | Invalidate token |
| Auth | `GET /auth/me` | Fetch signed-in user profile |
| Tickets | `GET /tickets` | List tickets |
| Tickets | `GET /tickets/{ticket_id}` | Ticket detail |
| Tickets | `POST /tickets` | Create ticket |
| Tickets | `PATCH /tickets/{ticket_id}/assign` | Assign ticket |
| Tickets | `PATCH /tickets/{ticket_id}/start` | Start maintenance workflow |
| Tickets | `PATCH /tickets/{ticket_id}/cancel` | Cancel ticket |
| Tickets | `PATCH /tickets/{ticket_id}/addwkd` | Register weekend work |
| Maintenances | `GET /maintenances` | List maintenances |
| Maintenances | `GET /maintenances/{maintenance_id}` | Maintenance detail |
| Maintenances | `PATCH /maintenances/{maintenance_id}` | Update maintenance |
| Maintenances | `PATCH /maintenances/{maintenance_id}/pause` | Pause maintenance |
| Uploads | `POST /uploads/init` | Initialize upload |
| Uploads | `POST /uploads/chunk` | Upload chunk |
| Uploads | `GET /uploads/status/{upload_id}` | Upload status |
| Uploads | `POST /uploads/complete` | Complete upload |
| Master Data | `GET /markets`, `GET /equipments`, `GET /technicians`, `GET /spares`, `GET /labsdls` | Lookup data |

## Frontend Architecture Guidelines

### Feature-Based Structure
- Keep each business domain in its own feature folder under `src/features`.
- Group screens, components, and hooks around the user flow they support.
- Place shared infrastructure in `src/shared` and app-wide state in `src/stores`.

### State Management
- Use Zustand for auth and simple global app state.
- Use TanStack Query for server-state fetching, caching, and invalidation.
- Avoid overusing global state for screen-local UI state.

### UI and UX
- Prefer native mobile patterns: clear loading, empty, and error states.
- Show concise and actionable feedback for failed requests.
- Keep ticket and maintenance workflows explicit and easy to follow.
- Use consistent visual hierarchy for statuses, priorities, and actions.

### Type Safety
- Use strict TypeScript everywhere.
- Reuse generated API types from the frontend type files.
- Do not define duplicate ad-hoc types when a generated type already exists.

### Error Handling
- Wrap API calls with `try/catch` and surface useful user messages.
- Show loading indicators while data is being fetched.
- Handle offline and 401 scenarios gracefully.

## Development Workflow

1. Review the backend route and schema changes before implementing UI changes.
2. Keep the frontend project decoupled from the backend repo while staying aligned to the API contract.
3. Update the frontend mock data when new backend entities or fields are introduced.
4. Prefer small, feature-focused changes and verify them against the current app flow.

## Quality Bar

- The mobile app should work well for authentication, ticket handling, maintenance workflows, and uploads.
- The frontend should remain consistent with the backend domain model and terminology.
- The implementation should be maintainable, typed, and easy to extend for future backend changes.
