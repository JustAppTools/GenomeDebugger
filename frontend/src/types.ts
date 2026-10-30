export type Status = 'verified' | 'rejected' | 'probable' | 'possible' | 'unresolved'
export interface Variant { assembly: string; sequence_id: string; position: number; ref: string; alt: string; reference_context?: {start: number; sequence: string} | null }
export interface Annotation {gene_id: string; transcript_id: string; consequence: string; protein_consequence?: string | null; clinical?: {framework: string; condition_id: string; classification: string; review_status?: string | null; assertion_date?:string|null} | null}
export interface Snapshot { id: string; label: string; variant: Variant; annotation: Annotation; annotations?: Annotation[]; variant_records?: {variant:Variant;annotations:Annotation[]}[]; provenance: {tool: string; tool_version: string; source_name: string; source_release: string; configuration: Record<string,string>; source_uri?: string | null; input_sha256?: string | null} }
export interface ReferenceCheckSummary {id:string;source_record_id:string;source_response_sha256:string;refseq_accession:string;expected_reference:string;observed_reference:string;reference_matches:boolean;spdi_matches:boolean;hgvs_matches:boolean;status:'agree'|'disagree'}
export interface AnnotationCheckSummary {id:string;status:'agree'|'disagree'|'unresolved'}
export interface InvestigationInput { title: string; synthetic: boolean; snapshots: Snapshot[]; controlled_lookup?: unknown; reference_check?: ReferenceCheckSummary | null; annotation_check?: AnnotationCheckSummary | null; meaningful_overrides?: Record<string,boolean> }
export interface Evidence { id: string; kind: string; description: string; data: Record<string,unknown> }
export interface Difference {field: string; category: string; before: string | null; after: string | null; meaningful: boolean; evidence_ids: string[] }
export interface Finding {status: Status; cause: string; explanation: string; affected_fields: string[]; evidence_ids: string[] }
export interface Result {id: string; engine_version?:string; input: InvestigationInput; identity: {status: Status; explanation: string; normalized_a?: string; normalized_b?: string; evidence_ids: string[]}; differences: Difference[]; findings: Finding[]; evidence: Evidence[]; input_sha256: string }
export interface RegressionCase {id: string; name: string; schema_version: number; created_at: string; source_investigation: Result }
export interface RegressionCheck {path: string; expected: unknown; actual: unknown; passed: boolean; required: boolean }
export interface RegressionRun {id: string; case_id: string; created_at: string; mode: 'pinned'|'candidate'; status: 'passed'|'failed'; baseline_input_sha256: string; candidate_input_sha256: string; checks: RegressionCheck[]; input_changes: string[]; actual: Result }
export interface RegressionRunSummary {id: string; created_at: string; mode: 'pinned'|'candidate'; status: 'passed'|'failed'}
