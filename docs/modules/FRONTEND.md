# RECALL — Frontend Module Contract

## Goal

Build the human-facing RECALL dashboard as a React application styled with Tailwind CSS and standard HTML semantics.

## Technology

- React
- Tailwind CSS
- JavaScript/JSX
- Vite preferred for local development/build

## MVP Screens

1. Chat / Ask RECALL
2. Memory Explorer
3. Conflict Center
4. Custom Instructions
5. Sessions/Stats
6. Project/context selector

## Required Custom Instruction UI

The UI must support:

- viewing/listing instructions;
- creating an instruction;
- updating an instruction;
- deleting/deactivating an instruction;
- selecting global or project scope.

## API Rule

The frontend communicates only through the RECALL HTTP/JSON API.

Never import database code into React.

## UX Requirements

Implement clear:

- loading states;
- empty states;
- validation states;
- API error states;
- success feedback;
- disabled/inactive instruction states;
- provenance/source displays when available.

## Integration Strategy

Use mocked API responses or a local mock layer if the backend is incomplete. Do not block UI development on backend completion.
