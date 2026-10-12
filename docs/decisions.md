# Architectural decisions

## 2026-10-11: Local FastAPI and React foundation

Use Python/FastAPI/Pydantic for explicit scientific schemas and a deterministic comparison core, React/TypeScript/Vite for an information-dense local UI, and SQLite for small durable investigation records. This follows the requested stack and avoids cloud dependencies.

## 2026-10-11: Controlled synthetic lookup before live annotation APIs

The first causal claim requires a replayable experiment. A tiny immutable synthetic table allows the engine to change one transcript selector and verify the observed consequences while the other declared inputs stay fixed. This tests the investigation workflow without falsely attributing current external data to an old run. Public adapters follow after the comparison semantics are sound.

## 2026-10-11: Conservative allele identity

Use exact assembly/accession/context equality and substitution-only flank trimming. Reject the temptation to infer indel equivalence or cross-assembly identity without a validated sequence repository and normalization library.

## 2026-10-11: Qualitative explanations

Finding statuses express what was tested. No numeric confidence score is emitted. A changed database release alone is only a possible contributor.
