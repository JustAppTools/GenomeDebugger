# Focused competitive assessment

Reviewed 2026-10-11. This is a scoped product comparison based on public documentation, not a claim that any capability is unique.

| Tool or resource | Established capability | Relevance to GenomeDebugger |
|---|---|---|
| [ClinVar Miner](https://clinvarminer.genetics.utah.edu/) | Browse/filter ClinVar data and inspect conflicting interpretations, including by submitter. | Strong conflict discovery. Our intended focus is reproducing *why two specific analysis runs* disagree, including local pipeline configuration. |
| [VarSome Clinical](https://docs.varsome.com/en/variant-table) | Variant tables, annotations, custom transcripts, classification workflows and evidence views. | Rich interpretation; GenomeDebugger should complement, not replicate, annotation or ACMG classification. |
| [Franklin](https://help.genoox.com/en/collections/2077313-franklin-variant-interpretation-hub) | Variant interpretation hub with associated conditions, evidence, and assessment tools. | Similar evidence-rich environment, but our selected workflow is a compact, local, controlled analysis-to-analysis replay. |
| [VariantValidator](https://variantvalidator.org/) | HGVS validation and genomic/transcript mapping, including VCF conversion. | Use established normalization/mapping capabilities in a later adapter; do not implement general HGVS rules from scratch. |
| [Ensembl VEP](https://static.ensembl.org/info/docs/tools/vep/index.html) | Predicts effects across transcripts and proteins; [JSON output](https://static.ensembl.org/info/docs/tools/vep/vep_formats.html) includes per-transcript consequences. | Natural source for future versioned annotation snapshots and controlled reruns. Transcript selection can alter reported consequences. |
| [ClinGen Allele Registry](https://reg.clinicalgenome.org/doc/AlleleRegistry_1.01.xx_api_v1.pdf) | Canonical allele identifiers and mappings across sequence-level descriptions. | Potential identity adapter, with current API terms and access requirements to verify before integration. |
| [GA4GH VRS](https://vrs.ga4gh.org/en/2.1.0-snapshot.2026-02.1/conventions/normalization.html) | Allele representation and normalization conventions. | Target standard for future allele identity; the MVP does not claim VRS conformance. |
| [Nextflow](https://www.nextflow.io/docs/latest/cli.html) | Versioned pipelines, execution traces and task provenance. | Strong pipeline reproducibility. GenomeDebugger aims to interpret a *specific result discrepancy* and preserve evidence-linked comparisons and future regression assertions. |

## Chosen differentiator

The initial differentiated workflow is an **evidence-linked, controlled replay of one analysis discrepancy**. It records the two outputs, checks that the relevant inputs and source versions are held constant, varies transcript selection in an immutable synthetic lookup, and reports the conclusion with replay data and a content hash. This is a narrow demonstration of software-debugging practice applied to genomic analysis, not proof that no other software can do this.

The first implementation deliberately stops at local synthetic fixtures. Existing tools already do much more comprehensive variant normalization and interpretation. The opportunity to test is whether a scientist can quickly turn a disagreement between two *versioned runs* into a clear causal record and, later, a reusable regression test.

## Source-data implications

[ClinVar distinguishes SCV, RCV, and VCV aggregation levels](https://www.ncbi.nlm.nih.gov/clinvar/docs/ftp_primer/), so a future adapter must record which was compared. [Monthly ClinVar releases are archived](https://www.ncbi.nlm.nih.gov/clinvar/docs/downloads/); a current API response is not historical evidence. Release-associated changes must remain possible explanations until underlying records can be reconstructed. ClinVar VCF files are summary-level and incomplete for imprecise variants, so a future clinical comparison should prefer suitable XML records where required.
