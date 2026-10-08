# RECALL — Product and Interaction Design

## Design Principles

1. **Memory is inspectable.** The user should be able to understand what RECALL knows and why.
2. **User control is explicit.** Custom instructions are user-authored state, not hidden prompt text.
3. **Conflicts are visible.** RECALL should expose unresolved or resolved conflicts rather than hiding them.
4. **Clients stay thin.** UI and OpenCode integrations call the same core APIs.
5. **History is preserved.** Compaction and updates do not erase canonical evidence by default.

## OpenCode Experience

The `/recall` command surface should feel operational and predictable.

Examples:

```text
/recall search database architecture
/recall update-context SQLite remains the source of truth
/recall compact
/recall custom-instructions
```

`/recall custom-instructions` should guide the user through listing, creating, updating, and deleting instructions when arguments are omitted or ambiguous.

## Dashboard Experience

The dashboard should feel familiar like a ChatGPT wrapper but remain visually and conceptually focused on persistent memory.

### Layout

- left navigation for chats, memory, conflicts, instructions, projects;
- central conversation/content area;
- contextual panel for sources, memory IDs, lineage, or active instructions when useful.

### Dashboard Pages

#### Home / Chat

A conversation-style interface for querying RECALL.

Example query:

> What did we decide about storage?

The response should be able to show supporting memory records and a compact provenance trail.

#### Memory Explorer

- search;
- filters by project/type/status/time;
- record detail;
- lineage/history;
- update/delete actions where allowed.

#### Conflict Center

Display:

- conflicting claims;
- source records;
- resolution status;
- deterministic reason;
- whether the local model was used;
- abstained/unresolved state;
- manual resolution action if supported.

#### Custom Instructions

The user must be able to:

- list/view active and inactive instructions;
- create an instruction;
- choose global or project scope;
- update an instruction;
- delete/deactivate an instruction.

#### Overview / Stats

Show useful operational metrics such as:

- active memories;
- projects;
- sessions;
- custom instructions;
- unresolved conflicts;
- semantic index status.

## Frontend Rules

The frontend never performs business logic that belongs to RECALL Core. It only manages UI state, API calls, validation needed for UX, and presentation.
