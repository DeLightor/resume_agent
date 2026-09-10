## ADDED Requirements

### Requirement: Versioned edits and history
The system SHALL atomically validate the expected node version and store changed content with a monotonic version and a bounded history of 20 snapshots.

#### Scenario: Concurrent editors
- **WHEN** two saves use the same base version
- **THEN** only the first changed save succeeds and the other receives a conflict without overwriting data

#### Scenario: Undo and redo
- **WHEN** a user undoes and redoes a node edit
- **THEN** the stored snapshots are restored with increasing write versions
- **AND** a new edit after undo discards the redo branch

### Requirement: Durable autosave
The UI SHALL autosave after 800ms and retain pending edits across navigation and reload.

#### Scenario: Save interruption
- **WHEN** a user edits multiple fields and reloads before save completes
- **THEN** pending local drafts can be recovered and save failures are visible

### Requirement: AI draft approval
The system SHALL present generated edits as selectable differences before writing them.

#### Scenario: Stale generation
- **WHEN** a user changes the node after generation starts and then accepts the old draft
- **THEN** the draft cannot overwrite the newer node without a conflict

### Requirement: Recoverable node deletion
The system SHALL soft-delete nodes with their active descendants and allow batch restoration within 30 days while protecting master and deleted node access.

#### Scenario: Restore subtree
- **WHEN** a user restores a deleted branch within 30 days with its parent active
- **THEN** descendants deleted in the same batch return with their contents intact
- **AND** descendants deleted earlier remain deleted
