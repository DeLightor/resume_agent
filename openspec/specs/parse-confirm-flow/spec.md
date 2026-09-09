# parse-confirm-flow Specification

## Purpose
TBD - created by archiving change parse-confirm-flow. Update Purpose after archive.
## Requirements
### Requirement: Two-stage resume import
The system SHALL extract an uploaded resume asynchronously and SHALL NOT write resume versions or knowledge chunks until the user confirms the reviewed structured data.

#### Scenario: Extract and review
- **WHEN** a user starts parsing an uploaded resume
- **THEN** the API returns a task ID and exposes extraction progress and editable results
- **AND** no resume version or knowledge chunk is created before confirmation

#### Scenario: Confirm corrected data
- **WHEN** a user edits and confirms extracted fields
- **THEN** the final validated values are stored in the version tree and indexed in knowledge
- **AND** uncorrected raw source text is not indexed
- **AND** repeated confirmation does not create duplicate writes

### Requirement: Visible evidence and explicit overrides
The system SHALL show confidence for each extracted field, highlight low confidence fields, and require explicit user action to adopt existing knowledge personal information.

#### Scenario: Review confidence and knowledge values
- **WHEN** an extraction is ready for confirmation
- **THEN** the user can edit basic information, education, experience, projects, skills and direction
- **AND** each extracted leaf has source-match confidence, including dates and highlights
- **AND** existing knowledge values are displayed without silently replacing extracted values

### Requirement: Recoverable progress and failures
The system SHALL expose SSE progress and polling details without cancelling extraction when an observer disconnects, and SHALL support recovery from interruption.

#### Scenario: Slow or degraded parsing
- **WHEN** MinerU fails or times out
- **THEN** local parsing is attempted and degradation is visible in the result
- **AND** a task taking longer than five seconds remains active

#### Scenario: Restart and retry
- **WHEN** the server has restarted during extraction
- **THEN** the orphan task is marked failed persistently and the same upload can start a new task

#### Scenario: Resume confirmation
- **WHEN** a user closes confirmation or reloads the page
- **THEN** the pending task can be reopened without creating tree nodes or knowledge chunks
- **AND** closing retains the current in-page draft while reloading restores the server extraction

#### Scenario: Index failure
- **WHEN** a version is saved but knowledge indexing fails
- **THEN** the user receives an explicit knowledge warning

### Requirement: Confirm a custom direction
The system SHALL accept a user-supplied custom direction during confirmation, persist the final direction on the upload, and use the direction to select or create a version-tree branch.

#### Scenario: Custom direction
- **WHEN** the user confirms with custom_direction set to 云安全
- **THEN** the saved upload and resulting branch have direction 云安全

### Requirement: Manage confirmed resume sources
The system SHALL display confirmed uploads with their saved direction and provide a source deletion action that preserves version-tree nodes.

#### Scenario: Delete a confirmed source
- **WHEN** the user confirms deletion and the storage operations succeed
- **THEN** the upload, parse tasks, related knowledge chunks, vectors and source file are removed
- **AND** the version-tree nodes remain
