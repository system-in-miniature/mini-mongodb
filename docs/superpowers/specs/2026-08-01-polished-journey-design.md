# MiniMongoDB Polished Journey Design

## Goal

Add the shared System-in-Miniature learning model without changing the finished
database implementation: a mechanism tutorial, a browser-based self-guided
rebuild, and a short agent-guided CLI usage path.

## Stage model

MiniMongoDB's implementation history is concentrated in two large feature
commits. The Journey therefore uses content-owned Stage boundaries instead of
pretending that each commit was already a lesson. Every Stage is still derived
from an exact Git revision and the cumulative final Stage must byte-match the
canonical owned source, labs, tests, and project metadata.

The twelve dependency-ordered Stages are:

1. BSON value and dotted-path contract
2. Array-aware query matching
3. Update and replacement semantics
4. Oplog value objects
5. Durable storage frames
6. Collection, database, and recovery loop
7. Journal-first ordering and canonical identity regressions
8. Secondary and multikey indexes
9. Planner and explain counters
10. Aggregation pipelines
11. Empty-collection query validation regression
12. Executable labs and domain closure

## Lesson contract

Each bilingual Stage explains the current problem, basic concepts, necessity,
and runtime mental model before source walkthroughs. Test diffs appear only in
the Test contract, where the failure preview is nested. Production diffs are
grouped by mechanism rather than mechanically titled by filename. Package
exports, dependency metadata, and other supporting files share one collapsed
support block.

Tests are observable evidence, not a mandatory test-first teaching ritual.
Each lesson names what the selected test protects, how its counterexample is
constructed, the key assertion, and what a failure means. Mechanism sections
explain what the code is, its runtime role, and the critical statement.

## Learning modes

- Mechanism Tutorial: the existing chapter-oriented book.
- Self-Guided Rebuild: twelve independent browser lessons with collapsed diffs.
- Agent-Guided Rebuild: a concise usage page and `AGENTS.md`; the command creates
  or resumes a marked Stage-specific workspace from the canonical repository.

No teaching branch switch is required. The agent-only Stage material is kept
inside the generated learning workspace, while the canonical repository stays
the source of truth.

## Verification

Acceptance requires the existing suite, Journey tool tests, all twelve focused
Stage checks, cumulative owned-tree parity, Python compilation, strict MkDocs
build, and browser checks for both languages, collapsed diffs, section order,
same-Stage language switching, the three-mode home, and Agent guide routes.
