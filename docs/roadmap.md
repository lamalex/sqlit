# Helix SQL Editor Roadmap

This is the living roadmap for sqlit's selection-first query editor and its evolution into a syntax-aware SQL development environment.

The goal is not to reproduce every Helix feature. The goal is to preserve Helix's composable selection model while investing most heavily in SQL-specific capabilities that make querying, understanding, and changing data safer and faster.

## Product Principles

1. Selections are the primary editing unit. Motions create or move selections; commands operate on them.
2. Invalid or incomplete key sequences are atomic. They cancel without replaying input in another context.
3. Query errors must be unmistakable. Failed execution must never leave successful-looking stale results visible.
4. Syntax intelligence must degrade gracefully. Incomplete or dialect-specific SQL must remain editable and executable.
5. Parser and language-server implementations stay behind stable application interfaces.
6. SQL dialect behavior belongs to providers or analysis adapters, not scattered UI conditionals.
7. A Rust rewrite is not a prerequisite. Replace the editor core only when measured constraints justify it.

## Shipped Foundation

The current editor foundation includes:

- Primary NORMAL-mode selections and explicit character and line selection modes
- Selection-first copy, delete, change, paste, replace, insert, and execution behavior
- Helix-style word, WORD, line, file, goto, find, till, and matching-bracket motions
- Text-object selection with `mi{object}` and `ma{object}`
- Surround add, delete, and replace with `ms`, `md`, and `mr`
- Smart-case query search with `/`, `n`, and `N`
- Selection direction and logical-head preservation across editing and pane focus changes
- Atomic `m`, `g`, results, leader, and window command grammars
- `Ctrl+w h/j/k/l` pane navigation
- Rectangular and row selections in results
- Raw-value TSV copying from result selections
- Safe UPDATE and DELETE drafting constrained to valid result selections
- Helix-style result goto commands and selection collapse
- Real SQLite execution in the `sqlite-demo` profile
- Error results that replace stale single or stacked results
- User-configurable keymaps with migration for changed defaults

## Phase 0: Selection Correctness

Before adding syntax behavior, finish the remaining selection invariants.

### Substantive Selection Execution (completed)

NORMAL mode represents its primary cursor as a one-character selection, while motions, search, and surround commands can retain broader selections. Execution must distinguish those cases:

- `Enter` on only the primary cursor selection executes the full query buffer.
- `Enter` on a substantive selection executes the selected SQL.
- The rule must be based on explicit selection state, not selection length alone.
- Help text and execution notifications must make the chosen scope clear.

Execution now tracks explicit primary versus substantive selection provenance. NORMAL motion, search, text-object, native, and visual-to-NORMAL selections execute their selected SQL; collapsing back to the primary cursor restores full-buffer execution. The status bar identifies selection and statement execution scopes.

### Selection-Aware Undo (completed)

Undo and redo snapshots should restore:

- Text
- Selection anchor and head
- Selection direction
- Logical cursor head
- Editing mode where appropriate

Undo and redo now use immutable query editor snapshots containing directional selection endpoints, logical cursor, primary/substantive provenance, Vim mode, and visual anchors. Restoration preserves NORMAL, character-selection, line-selection, and INSERT behavior; redo restores the exact post-edit snapshot and new edits invalidate the previous redo branch immediately.

### Unified Selection State (completed)

Reduce the internal distinction between NORMAL, VISUAL, and VISUAL LINE selections. Commands should consume a common selection model even if different modes remain visible to users.

NORMAL, character-selection, line-selection, and INSERT modes now share one immutable live selection snapshot. It owns directional Textual endpoints, the logical head, primary/substantive provenance, mode, and visual anchors; editor commands replace that snapshot atomically, Textual-originated selections are observed back into it, and undo captures the same canonical state.

## Phase 1: Syntax Analysis Boundary

Introduce a dedicated `QueryAnalysisService` before adding syntax-aware commands.

```text
QueryTextArea
    |
    v
QueryAnalysisService
    |
    +-- incremental syntax snapshot
    +-- active SQL dialect
    +-- syntax node and range conversion
    +-- schema metadata
    +-- diagnostics
```

The service should expose application concepts rather than parser objects, for example:

```python
analysis.statement_at(position)
analysis.parent_range(selection)
analysis.previous_selection()
analysis.sibling_range(selection, direction)
analysis.subquery_at(position)
analysis.clause_at(position)
analysis.diagnostics()
```

UI mixins and editing commands must not depend directly on Textual's syntax-document internals, tree-sitter nodes, or SQLGlot expression classes.

### Existing Capability

`QueryTextArea` already runs with `language="sql"` through `textual[syntax]`. Textual maintains an incrementally updated `tree-sitter-sql` syntax tree. The first implementation should reuse that tree through a narrow adapter rather than introduce another immediate parser loop.

The initial `QueryAnalysisService` boundary now exposes parser-neutral syntax ranges for nodes, statements, parents, siblings, and diagnostics. Its Textual adapter is the only layer that accesses the maintained tree, converts UTF-8 parser coordinates to editor coordinates immediately, and never caches or returns parser objects.

## Phase 2: Structural Helix Editing

Use the syntax service to deliver the first high-value vertical slice:

- Expand selection to its parent syntax node
- Shrink to the previous syntax selection
- Select previous and next syntax siblings
- Preserve structural selection history
- Select the statement at the logical head
- Select a CTE definition or body
- Select a subquery
- Select a SELECT list
- Select WHERE, GROUP BY, HAVING, ORDER BY, LIMIT, and RETURNING clauses
- Select JOIN conditions and table expressions

Proposed defaults should follow Helix where practical:

- `Alt+o`: expand selection
- `Alt+i`: shrink selection
- `Alt+n`: next sibling
- `Alt+p`: previous sibling

The initial structural slice now supports parent expansion, history-based shrinking, previous and next sibling selection, and statement selection through `QueryAnalysisService`. Structural selections use the same canonical selection snapshot as other editor commands, and ordinary motions invalidate structural history rather than restoring stale ranges.

Semantic match commands now select statements (`mS`), CTE definitions and bodies (`me`/`mE`), subqueries (`mq`), SELECT lists (`ml`), the clause at the logical head (`mc`), JOIN conditions (`mj`), and table expressions (`mt`). Cross-style fixtures cover common SQLite, PostgreSQL, MySQL, SQL Server, BigQuery, and Snowflake shapes plus incomplete SQL; unsupported dialect grammar degrades to diagnostics or no semantic match without blocking editing.

The spike succeeds when these commands remain responsive and useful across representative SQLite, PostgreSQL, MySQL, SQL Server, BigQuery, and Snowflake queries, including incomplete SQL.

## Phase 3: Embedded SQL Semantics

Evaluate SQLGlot as an explicit dependency behind `QueryAnalysisService`.

Potential uses include:

- Dialect-aware parsing and normalized ASTs
- Query and selection formatting
- Table, alias, column, and CTE resolution
- Best-effort lineage
- Safe query transformations
- More precise statement and clause boundaries

Tree-sitter and SQLGlot serve different purposes:

- Tree-sitter provides incremental, error-tolerant structure while the user types.
- SQLGlot provides richer dialect-aware semantics when a complete parse succeeds.

Failure to parse must never block editing or execution. The connected database remains authoritative for runtime validity.

## Phase 4: SQL-Native Workflows

Build features that exploit syntax and live schema knowledge:

- Format the current selection, statement, or buffer
- Preview the exact SQL execution scope
- Show syntax diagnostics without obscuring database errors
- Map database error locations back into query selections
- Explain the selected statement
- Preview CTEs and subqueries
- Rename aliases within a safe syntax scope
- Navigate between CTE definitions and references
- Show table and column types from the active connection
- Run independent selected statements and stack their results

Mutating transformations must be conservative, dialect-aware, undoable, and inspectable before execution.

## Phase 5: Optional Language Servers

Add a provider-neutral LSP client only after the embedded analysis boundary is stable.

Potential backends include:

- dbt Fusion for dbt projects when the user already has Fusion installed
- Other SQL language servers when they add capabilities beyond embedded analysis

dbt Fusion is an external optional integration, not a core dependency. It offers deep dbt project semantics, Jinja compilation, type analysis, CTE previews, diagnostics, and lineage, but its SQL comprehension components are not a simple MIT/Apache parser library and its server is oriented around dbt projects.

sqlit should communicate through standard LSP messages and remain useful without an account, a dbt project, or an installed language server.

## Deferred, Not Required

These Helix capabilities are valuable but are not prerequisites for syntax-aware SQL editing:

- Multiple selections and multiple cursors
- Named registers
- Keyboard macros
- Repeat-last-change
- Full selection filtering and splitting grammar
- Complete Helix count semantics

Multiple selections should be revisited when a concrete SQL workflow benefits from them, such as renaming several aliases, editing repeated predicates, or executing independent selected statements.

## Editor Core Checkpoints

Continue with Textual and Python unless one or more measured constraints become material:

- Arbitrary diagnostics or structural decorations require pervasive private Textual APIs.
- Large real-world queries produce visible parse or render latency.
- Selection correctness is blocked by Textual's single-selection model.
- Syntax features spread parser-specific state across application mixins.
- Textual upgrades repeatedly break essential editor behavior.

If those conditions appear, first replace `QueryTextArea` with a purpose-built editor widget behind the existing application protocols. A full application rewrite is a separate decision and requires stronger evidence.

## Definition of Success

sqlit should feel like a SQL-native Helix environment:

- Structural navigation is faster than manually positioning a cursor.
- Every operation clearly communicates its selection and execution scope.
- Invalid SQL is obvious before or after execution.
- Syntax intelligence improves editing without rejecting valid vendor SQL.
- Live database metadata and local syntax analysis reinforce each other.
- Optional external tooling adds depth without becoming a requirement.
