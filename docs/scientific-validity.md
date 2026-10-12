# Scientific validity and limitations

## Validated in this release

- **Input consistency:** The schema rejects missing required fields, invalid bases, an unchanged allele, and a `ref` that does not match its supplied reference context. The context itself is user supplied and is not checked against a reference genome.
- **Narrow allele comparison:** On the same declared assembly, sequence accession, and identical supplied reference context, shared-prefix/suffix trimming identifies equivalent *nonempty substitution edits*. It is symmetric and idempotent in tests. This is local representation equivalence, not external sequence validation.
- **Controlled synthetic replay:** For one synthetic allele, a transcript lookup is deterministically rerun against each selected transcript. The engine requires matching observed outputs and identical tool/version, source/release, and configuration before calling transcript selection verified **within that supplied fixture**.
- **Clinical comparability guard:** Classifications are compared only when condition ID and framework match. No classification is inferred.
- **Traceability:** Field differences, candidate causes, and replay results carry evidence IDs. Canonicalized input JSON and lookup rows are SHA-256 hashed.
- **Regression assertions:** A pinned replay requires the saved annotations, identity status, field differences, findings, and hashed evidence data to match the current engine. A candidate replay requires the same submitted variant descriptions and compares expected output fields while surfacing input and evidence drift. A passing candidate run with changed evidence does not imply the evidence sources are equivalent.

These behaviors are covered by unit and API tests. They have **not** yet been validated against authoritative biological reference cases or independent annotation engines.

## Experimental or unsupported

- Insertions/deletions, including repeat shifting, are unresolved. Flank trimming does not implement VCF left alignment, HGVS 3′ shifting, SPDI contextualization, or VRS normalization.
- Assembly changes and different sequence accessions are unresolved; there is no liftover or sequence equivalence service.
- Reference-context authenticity, transcript consequences, and synthetic lookup entries are not independently verified. The fixture uses fabricated gene and transcript names.
- Different source releases produce a possible release-associated explanation, never a claim about the underlying evidence change.
- No live ClinVar/VEP integration, historical reconstruction, clinical review-status inference, patient-specific interpretation, or pathogenicity prediction exists.
- Regression tests do not run VEP, ClinVar, or another external pipeline. Candidate snapshots must be supplied by the user; their provenance and content are not independently authenticated.
- A file hash in `Provenance` is accepted as metadata, but file content is not uploaded or checked by the MVP. The `input_sha256` is a hash of validated canonical JSON, not original input bytes.

## Failure modes to guard against next

False equivalence can arise if a supplied reference context is wrong. False causal certainty can arise if a controlled table is itself inaccurate or if hidden configuration variables differ. Future public-source adapters need record-level provenance, release identifiers, and independent fixtures. Any regression-test feature must pin the reference, source, and tool versions it expects.

GenomeDebugger is a research and bioinformatics quality-assurance tool, not a certified clinical diagnostic device.
