export type Status = 'verified' | 'rejected' | 'probable' | 'possible' | 'unresolved'
export interface Variant { assembly: string; sequence_id: string; position: number; ref: string; alt: string; reference_context?: {start: number; sequence: string} }
export interface Snapshot { id: string; label: string; variant: Variant; annotation: {gene_id: string; transcript_id: string; consequence: string; protein_consequence?: string | null; clinical?: {framework: string; condition_id: string; classification: string; review_status?: string} | null}; provenance: {tool: string; tool_version: string; source_name: string; source_release: string; configuration: Record<string,string>} }
export interface InvestigationInput { title: string; synthetic: boolean; snapshots: Snapshot[]; controlled_lookup?: unknown }
export interface Evidence { id: string; kind: string; description: string; data: Record<string,unknown> }
export interface Difference {field: string; category: string; before: string | null; after: string | null; meaningful: boolean; evidence_ids: string[] }
export interface Finding {status: Status; cause: string; explanation: string; affected_fields: string[]; evidence_ids: string[] }
export interface Result {id: string; input: InvestigationInput; identity: {status: Status; explanation: string; normalized_a?: string; normalized_b?: string; evidence_ids: string[]}; differences: Difference[]; findings: Finding[]; evidence: Evidence[]; input_sha256: string }
export interface RegressionCase {id: string; name: string; schema_version: number; created_at: string; source_investigation: Result }
export interface RegressionCheck {path: string; expected: unknown; actual: unknown; passed: boolean; required: boolean }
export interface RegressionRun {id: string; case_id: string; created_at: string; mode: 'pinned'|'candidate'; status: 'passed'|'failed'; baseline_input_sha256: string; candidate_input_sha256: string; checks: RegressionCheck[]; input_changes: string[]; actual: Result }
export interface RegressionRunSummary {id: string; created_at: string; mode: 'pinned'|'candidate'; status: 'passed'|'failed'}
