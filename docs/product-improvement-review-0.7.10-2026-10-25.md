# GenomeDebugger product improvement review

Reviewed October 25, 2026. Application 0.7.10; comparator 0.6.5.

## Main finding

GenomeDebugger has a sound foundation for a specialist investigation tool, but its user journey still assumes that people understand the underlying data model. Its next major improvement should be helping someone move from **“I have these analysis results”** to **“I understand what differs and what the evidence supports.”**

The product can make comparisons understandable to a broad audience. Preparing scientifically valid inputs will still require information from an analysis tool or a knowledgeable data producer. The interface should obtain that information through supported imports, explain where it comes from, and expose missing information honestly. It should never encourage people to invent genome metadata to complete a form.

This is an improvement review, not a new bug audit or an implementation plan committing to every possible feature. Priorities reflect the user's stated preference for understandable, simplified workflows without games. Recommendations need validation with representative users.

## Review basis and limits

- Reviewed the local homepage, input flow, public lookup, an existing synthetic comparison, changes, evidence, saved-test entry, and comparison library, together with the relevant frontend code and current roadmap.
- Checked the public-lookup layout at 375 × 844 CSS pixels and restored the default viewport afterward.
- Opened existing local records only. Did not run new external lookups, create comparisons, save tests, or edit scientific records during this review.
- This review does not establish WCAG conformance, performance limits, browser compatibility, or clinical validity. Those require dedicated evaluation.
- Existing capabilities include guided and JSON inputs, a three-question summary, term definitions, source capture, reference checks, saved comparisons and search, regression tests, and JSON/text/bundle exports. The recommendations below improve those capabilities rather than treating them as absent.

### Specific observations

| Observation | Product implication |
| --- | --- |
| The start screen offers an example and manual/custom JSON entry; public lookup is a sidebar destination. | The easiest route depends on what the visitor already has, but the start screen does not help them choose that route. |
| The guided input has approximately 33 input controls for the initial comparison, including specialist metadata. | A guided form still demands substantial scientific preparation. |
| Assembly, accession, reference context, and tool/source versions appear without field-specific instructions about where to obtain them. | Users can understand the label yet still have no way to supply a valid value. |
| Historical VEP reconstruction appears before the current Ensembl lookup. At phone width, the current lookup starts below the first screen. | A specialist path takes attention away from the simpler task. |
| The summary reports counts and broad certainty statements. Detailed findings are inside “Show technical details.” | Important explanatory content is hidden with implementation detail. |
| Changes display raw values such as `missense_variant`; evidence entries have names such as `diff-1` and open JSON. | A non-specialist must translate the result themselves. |
| Global navigation repeats result sections that also appear in local tabs; compare/example actions recur in several places. | The page asks users to choose between controls with overlapping purposes. |
| Recent records include multiple identical synthetic titles distinguished mainly by hashes. | Returning to the right comparison becomes harder as the library grows. |
| The mobile navigation is labeled, but occupies considerable initial screen space. | The task itself should receive more of the limited viewport. |

## Priority definitions

- **P1 — next release:** changes that most directly improve purpose, entry, and understanding.
- **P2 — following work:** workflow, accessibility, and everyday-use improvements after the core journey is coherent.
- **P3 — conditional expansion:** implement when there is a validated audience need and adequate scientific coverage.

Relative effort is indicative: small means mainly wording/presentation; medium means coordinated frontend/state work; large means new data handling, scientific validation, or distribution work. It is not an estimate in days.

## P1: make the core journey understandable

### 1. State the job in one concrete sentence

**Proposal:** Lead with “See why two tools gave different predictions for the same DNA change,” followed by a short before/after example. Broaden that wording where comparisons also involve versions or settings. Explain that the starting material is already analyzed output, not an arbitrary gene name or a raw personal DNA file.

**Acceptance:** A first-time visitor can explain what the product compares and name the information needed without opening documentation. **Effort:** small.

### 2. Organize the homepage around what the user has

Offer three clear paths: **Understand an example**, **Import two analysis results**, and **Look up a public DNA change**. If users have no usable output yet, explain the preparation step and supported tools rather than sending them into a blank scientific form.

**Acceptance:** Each path states its required starting material and expected result. **Effort:** medium; coordinate with items 3–5.

### 3. Replace the long entry page with a short sequence

Use **Choose inputs → Review the DNA change and sources → Compare → Understand**. Keep expert manual editing available, but initially reveal only information necessary for the selected path. Show optional context, multiple variants, extra annotations, and advanced JSON when relevant.

**Acceptance:** Users can complete the supported simple case without working through the entire internal schema. **Effort:** medium.

### 4. Explain exactly where each value comes from

Add persistent, accessible help beside assembly, sequence accession, position, reference/alternate, reference context, gene/transcript identifiers, predicted effect, and analysis version fields. For example, assembly should come from the input file header or producing analysis; reference context requires the appropriate reference source. Explain when a value is required, optional, unknown, or unavailable. Do not substitute plausible defaults for unknown scientific facts. This follows [W3C guidance on form instructions](https://www.w3.org/WAI/tutorials/forms/instructions/).

**Acceptance:** Each specialist input has a definition, a source/example, and an explanation of what to do if it is missing. **Effort:** medium.

### 5. Make supported imports the primary real-data path

Unify discovery of existing custom-input JSON, historical VEP JSON, and SnpEff-related workflows. Display exact accepted formats, scope, and examples. Extend parsers in stages rather than presenting “JSON” or “VCF” as universally interchangeable formats. Later candidates include specific annotated VEP/SnpEff exports and explicitly mapped tabular exports.

Show a preview with detected metadata, imported rows, unsupported rows, and conflicts before creating a comparison. Preserve original inputs; never silently select a genome assembly, coordinate convention, transcript, or allele to make an import succeed.

**Acceptance:** A supported file has a documented path into a reviewed comparison; unsupported files receive a useful explanation. **Effort:** large for new formats; medium for consolidating current import paths.

### 6. Add a comparison-readiness review

Before running, summarize what the app will compare: variant, assembly, analysis/tool versions, selected outputs, and available checks. Distinguish errors that prevent comparison from missing evidence that only limits a conclusion. Offer a fix beside each issue. If both analyses describe the same variant, allow copying confirmed shared data without preventing legitimate differences.

**Acceptance:** The user knows what has been supplied, what remains unknown, and what the result will be able to establish. **Effort:** medium.

### 7. Give a case-specific answer before counts

Build on the existing three-question summary. Explain the actual changed output and relevant settings or transcript differences, rather than only “6 values changed.” Bring supported explanatory findings out of the technical-details disclosure. Use deterministic, evidence-linked explanations so that wording remains within the engine's scientific claims.

For example, a synthetic case can explain that the analyses selected different transcripts and returned different predicted effects, then separately describe what the controlled replay demonstrates. Avoid generalizing that demonstration to real clinical causation.

**Acceptance:** Readers can identify the principal difference, the supporting evidence, and what is still uncertain from the first result screen. **Effort:** medium.

### 8. Make evidence readable by default

Render evidence according to its purpose: before/after fields, source and capture details, performed checks, and replay inputs/results. Name entries “DNA change comparison” or “Predicted effect changed,” retaining internal IDs in an optional technical view. Keep raw JSON and hashes available under an explicit disclosure.

**Acceptance:** “How was this checked?” opens an understandable explanation with access to the exact stored record. **Effort:** medium.

### 9. Translate result values without discarding their exact meaning

Pair consequence identifiers with short, reviewed explanations, retain exact tool terms, and distinguish annotations from evidence about health. Show available gene names beside stable identifiers without inferring a gene/transcript mapping that has not been supplied or verified. Use Analysis A/B names that reflect the actual tool, version, or selected transcript.

**Acceptance:** The original scientific value remains visible or directly accessible, and its explanation does not overstate its implications. **Effort:** medium.

### 10. Explain the different kinds of certainty separately

Keep separate answers for matching edits in supplied context, external reference checking, agreement between predicted outputs, and evidence for a cause. Show whether each claim comes from a made-up example, imported declaration, captured public source, independent check, or controlled execution. These are distinct dimensions, not one confidence percentage.

**Acceptance:** Readers can tell what was checked and what was only declared. **Effort:** medium.

### 11. Give every result an appropriate next action

Link uncertainty to a specific useful action: obtain missing source/version metadata, review the selected transcript, inspect a changed output, perform an available reference check, or export a report. Some uncertainty may have no supported resolution; say so rather than offering an irrelevant action.

**Acceptance:** A completed or limited result explains the next useful step, if there is one. **Effort:** medium.

### 12. Simplify navigation and repeated controls

Use global navigation for major tasks and local navigation for the open comparison. Keep one prominent action for the current step. Move input JSON and scientific regression controls into clearly discoverable advanced areas. Preserve useful expert shortcuts without presenting them as the default first-time journey.

**Acceptance:** Users do not need to choose between several differently worded buttons that perform the same next step. **Effort:** medium.

### 13. Put the simple public lookup first

Start the lookup page with the current, supported query. Place preserved historical output and local annotation execution in clearly named advanced sections. Explain the supported assembly and variant type before entry. Let the user see the variant, source, capture date, and available outputs before the detailed provenance hashes.

**Acceptance:** The current lookup is immediately discoverable on desktop and phone; historical and execution capabilities remain accessible. **Effort:** small to medium.

### 14. Provide a grown-up, guided example

Keep the existing synthetic example, but explain what to notice at each stage and how its inputs were constructed. Add contrasting examples for matching outputs, different transcripts/settings, and insufficient evidence. Where independently sourced examples are added, document capture and limitations distinctly from synthetic fixtures.

**Acceptance:** A person can finish an example and explain what their own real-data equivalent would require. No games, scores, or reward mechanics. **Effort:** medium; larger for curated external cases.

## P2: make everyday use easier

### 15. Make the Changes view easier to interpret

Group changes into variant description, predicted outputs, analysis settings, and source metadata. Add short descriptions and let readers expand technical detail. Make the active filter and shown-versus-total count explicit; explain why comparison rules emphasize particular fields. Review whether “Important” should become “Prioritized by comparison rules” or another tested label.

**Acceptance:** Users understand why the example's six changes can produce three visible rows, and do not read comparison priority as medical significance. **Effort:** medium.

### 16. Show a small, factual visual when it resolves confusion

Use a DNA-letter alignment for differently written edits and a simple schematic for selecting different transcripts. Label a teaching schematic as conceptual; only draw genomic positions, strand, exon boundaries, or normalization steps when the actual supporting data is available. Supply a text equivalent.

**Acceptance:** The visual answers a specific question and remains faithful to stored data. **Effort:** medium.

### 17. Make required-field feedback local and timely

Mark required/optional information beside fields, explain expected formats, and connect messages to the affected inputs. Prefer actionable feedback during review or after interaction over an intimidating list of everything missing from a fresh form. Provide a linked error summary for navigation when submission fails.

**Acceptance:** Users can find and correct each issue without searching the entire page. **Effort:** medium.

### 18. Make technical limitations useful at the point of decision

Show whether a limitation concerns import, comparison, reference checking, or causal explanation. These capabilities have different supported scopes. Explain unsupported cases before users invest time filling a form, and offer the closest valid path where one exists.

**Acceptance:** “Unsupported” says which operation is unavailable and why, rather than implying the whole DNA change is unusable. **Effort:** medium.

### 19. Add a resumable local draft workspace

Offer explicit local draft saving/restoration, last-saved status, resume/discard, and undo for edits. Keep editable drafts separate from immutable completed investigations. Make storage duration and clearing controls visible; avoid silently retaining extra sensitive data beyond user expectations.

**Acceptance:** Users can deliberately recover unfinished work and distinguish it from a completed result. **Effort:** medium.

### 20. Make the library recognizable without hashes

Allow user-facing labels, notes, tags, and favorites; show variant and tool/source summaries. Add source, date, and result-status filters, sorting, and a compact preview. Keep cosmetic labels separate from hashed scientific input so renaming does not rewrite evidence. Recent entries should show a distinguishing name/date and meaningful context.

**Acceptance:** Users can locate a known comparison among repeated titles without opening every record. **Effort:** medium to large.

### 21. Provide recoverable organization and deletion

Consider archive/trash and explicit restore for ordinary records, with clear behavior for pinned tests and storage retention. Offer selected-record export and backup before bulk operations. Do not describe a UI archive as permanent deletion, or promise recovery for data actually purged.

**Acceptance:** Accidental cleanup has a documented recovery path while users retain a deliberate permanent-delete option. **Effort:** large; storage design required.

### 22. Add bookmarkable local pages

Use routes for saved comparisons and their result sections, with working browser Back/Forward and clear missing-record states. Label copied localhost links as local to the installation; they do not share the underlying data with someone else's computer. Keep bundle export as a supported transfer path.

**Acceptance:** Reloading a saved comparison URL returns to that comparison without creating a new record. **Effort:** medium.

### 23. Improve the human report

Build a print-friendly HTML report, with print-to-PDF support if appropriate, on the existing text report and full bundle. Lead with the comparison question, named analyses, specific differences, evidence scope, uncertainty, and next steps. Put technical provenance in an appendix. Show an export preview and explain which export suits reading versus reproducible transfer.

**Acceptance:** A non-specialist can read the report without understanding JSON, while an expert can trace its claims. **Effort:** medium.

### 24. Make saved tests understandable as a task

Introduce the concept as “Save an expected result” and “Check a new analysis.” Show expected versus actual values and explain a failure in context. Keep baseline immutability, candidate declarations, evidence fingerprints, and advanced replay controls available to experts.

**Acceptance:** The user understands what a saved test protects and that passing it is not proof of a biological or medical conclusion. **Effort:** medium.

### 25. Improve transcript selection

Help users understand why they are choosing two outputs and what selection changes. Show informative supplied labels, differences, biotype, transcript versions, and source. Retain filtering already present. If adding recommendations or canonical/MANE indicators, obtain and display their actual source and date rather than inventing a preferred transcript.

**Acceptance:** Users can explain which two outputs they selected and why; the interface does not imply a universally correct transcript. **Effort:** medium.

### 26. Make source freshness and reproducibility easier to compare

Present a source card with original analysis date if known, capture/import date, tool and database versions, declared versus observed metadata, and cache status. Explain that refreshing public data creates a new captured observation rather than replacing evidence behind an old result. Put long hashes behind a technical disclosure.

**Acceptance:** A reader can distinguish an original historical output from a present-day source response. **Effort:** medium.

### 27. Design useful progress and recovery states

For slow imports, queries, and controlled executions, show the actual phase, what can be safely cancelled, and useful retry/recovery actions. Preserve the reviewed input and identify which operation a message concerns. Only show a percentage when the operation exposes meaningful progress.

**Acceptance:** A user knows whether to wait, retry, correct input, or use cached data. **Effort:** medium; background jobs may be larger.

### 28. Give the phone layout a smaller navigation footprint

Retain labeled controls, but consider a compact task switcher and contextual result navigation. Put the current task and next action ahead of advanced introductions. Render dense tables as expandable summaries or deliberately scrollable tables where necessary. Check that any sticky controls remain usable with the keyboard and do not cover content.

**Acceptance:** The main lookup and comparison steps are apparent in the first useful phone screen, and all technical details remain reachable. **Effort:** medium.

### 29. Improve visual hierarchy and reading comfort

Keep the calm teal/navy identity. Increase the smallest explanatory text, reduce unnecessary uppercase labels and competing cards, and reserve monospace for exact identifiers/data. Use space and headings to prioritize the conclusion rather than expanding every panel equally. Test larger text and a comfortable reading width.

**Acceptance:** The primary answer and action are visually distinct; essential explanations do not depend on tiny secondary text. **Effort:** small to medium.

### 30. Run a dedicated accessibility review

Evaluate keyboard navigation, focus visibility and movement, screen-reader names and errors, contrast, zoom/reflow, reduced motion, tables, and announcements. Test touch target size and spacing. WCAG 2.2 AA target-size guidance uses 24 × 24 CSS pixels with defined exceptions; larger comfortable controls can still be a worthwhile product goal. Existing 38-pixel button heights alone do not establish a failure. See [W3C's target-size explanation](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

**Acceptance:** Document actual findings, resolve them, and verify core workflows with both automated checks and assistive-technology use. **Effort:** medium.

### 31. Add concise, contextual help

Extend the existing glossary with assembly, accession, coordinates, reference context, provenance, and controlled replay. Link directly from the relevant field/result. Include a short “Where do my inputs come from?” guide, supported-files examples, and troubleshooting. Keep brief definitions in the interface and detailed material one click away.

**Acceptance:** Help answers the question at hand without making users read a scientific manual first. **Effort:** small to medium.

### 32. Add a local data and settings page

Show data location, storage use/limits, backup/restore instructions or controls, application/comparator versions, and provider-request behavior. Explain that local storage is distinct from source-provider queries and exported bundles. Make the data included in a request clear beside the action that sends it.

**Acceptance:** Users know where their work lives, how to preserve it, and what leaves the installation when they invoke an external operation. **Effort:** medium.

## P3: expand only after validating the core journey

### 33. Accept convenient public variant identifiers

Consider rsID or HGVS entry alongside coordinates. Resolve and preview the precise variant, assembly, reference/alternate, and supported operation before querying/using it. Handle ambiguous identifiers and multiple alleles explicitly. A gene name alone is not a unique variant selection.

**Acceptance:** Convenience input never silently changes scientific meaning. **Effort:** large; identifier resolution and coverage tests required.

### 34. Add batch comparison with an explicit review model

For users who regularly have many variants, add import previews, stable row matching, per-row scope/status, filters, selected export, and bounded/background processing where justified. Do not simply increase limits and expose thousands of raw rows.

**Acceptance:** Users can identify unmatched or unsupported rows and inspect the evidence behind each matched result. **Effort:** large.

### 35. Broaden scientific coverage deliberately

Extend assemblies, sequence types, variant classes, normalization, or cross-assembly mapping only with independent examples and explicit validation. Display a capability matrix rather than suggesting every operation supports the same inputs.

**Acceptance:** Every broadened claim has documented scope and positive, negative, and ambiguous test cases. **Effort:** large.

### 36. Build real historical comparison workflows

Where genuine original artifacts are available, help users compare captured tool/database/reference releases and controlled changes. Add sourced timelines or dependency views when they answer an actual investigation question. Never reconstruct a claimed past response from current data alone.

**Acceptance:** Each historical claim traces to preserved artifacts or is clearly labeled as unverified declaration. **Effort:** large.

### 37. Package an easier local application

Consider an installer/launcher that manages the necessary runtime and dependable startup, shows readiness, and offers a usable recovery screen. Add versioned, reviewed update and backup behavior. This reduces setup friction for non-developers without requiring a hosted product.

**Acceptance:** A target user can install, launch, close, and reopen their saved work without managing development terminals. **Effort:** large.

### 38. Decide separately whether hosted collaboration is needed

Only add accounts, shared workspaces, hosted URLs, and collaboration if the intended audience needs them. A hosted service requires a deliberate architecture for access, retention, isolation, and shared evidence; exposing the local development server is not that architecture.

**Acceptance:** Hosting has an explicit audience/use case and reviewed data-management design. **Effort:** large; separate product decision.

### 39. Add integrations where they remove repeated work

Consider documented command-line/API import or pipeline-export adapters for actual producing tools. Prefer a small number of well-supported, versioned adapters to a broad compatibility claim. Keep original files, mapping choices, and provenance available.

**Acceptance:** A repeated real workflow becomes simpler without weakening scientific traceability. **Effort:** large.

### 40. Consider language support after simplifying the source wording

If users need it, translate the interface, help, and reviewed explanations while retaining exact original scientific identifiers and consequences. Test dates, number entry, long labels, and accessibility in each supported language.

**Acceptance:** Translation preserves meaning and scientific identifiers, rather than merely translating button labels. **Effort:** medium to large.

## Product validation that should accompany the work

### 41. Test comprehension with representative people

Include people who read results without preparing them and people who generate valid analysis outputs. Ask participants to explain the product, choose valid inputs, finish a comparison, describe the main difference, and state what remains unknown. Observe where they stop or guess. Do not use visual preference alone as proof of improvement.

**Acceptance:** Define success criteria before testing and record concrete task outcomes. **Priority:** P1, repeated after major flow changes.

### 42. Expand realistic evaluation data

Maintain curated matching, differing, missing-evidence, ambiguous, transcript-version, and unsupported examples from independent sources where possible. Separate scientific validation from UI tests. Test report wording against those cases so explanation changes cannot overstate conclusions.

**Acceptance:** Result explanations remain accurate across both expected successes and limitations. **Priority:** P1/P2.

### 43. Validate browsers, assistive technologies, and scale

Add targeted Firefox/WebKit coverage, representative screen-reader/keyboard testing, and measurements for larger supported inputs and libraries. Expand testing based on observed risk and supported audiences rather than repeating the same Chromium workflow many times.

**Acceptance:** Publish a realistic supported environment and measured input/storage limits. **Priority:** P2.

### 44. Measure improvement without collecting genetic data

Use moderated observation first. If product metrics are needed, define an explicit opt-in design for non-content events such as task completion or time to a first useful comparison. Do not send variants, files, result content, identifiers, or reports as analytics. Useful measures include abandoned entry steps, import success, correction effort, and comprehension of uncertainty.

**Acceptance:** Metrics answer specific product questions and users understand any data collection. **Priority:** P2, conditional on need.

## Recommended implementation sequence

Do not build all 44 items at once. Some are alternatives or depend on evidence about future users.

1. **Clarify the start and required inputs:** items 1–4, 12–14, and contextual help from 31. Start representative user testing (41).
2. **Make the answer understandable:** items 7–11, 15–16. Preserve exact evidence and validate wording with cases from 42.
3. **Make real-data entry practical:** consolidate current imports, then implement the next validated adapter and readiness review (5–6, 17–18, 25–26).
4. **Support repeated use:** drafts, library, routes, reports, and comprehensible saved tests (19–24). Accessibility and phone work (28–30) should accompany each stage, not wait for the end.
5. **Improve distribution and expand based on demand:** settings/progress first; installer, additional identifiers, batch support, scientific coverage, integrations, and hosting only after their dependencies are met.

The first release should let a new user answer four questions without help: **What is this for? What do I need? What changed in my comparison? What can the evidence actually establish?**

## What to preserve

- The calm, professional visual identity and the removal of game mechanics.
- The existing three-question summary, expanded rather than replaced with another dashboard.
- Conservative scientific claims and explicit uncertainty.
- Original source artifacts, immutable completed results/baselines, reproducible bundles, and expert access to exact data.
- Local operation and deliberate external source actions.
- Existing import, search, export, reference-check, and regression capabilities; improve their discovery and presentation.

## External references

- [W3C: Form instructions](https://www.w3.org/WAI/tutorials/forms/instructions/) — required/optional inputs, formats, persistent instructions, and accessible association with controls.
- [W3C: Understanding target size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) — target size/spacing and the distinction between a minimum requirement and comfortable interaction.

The application code and observed local UI are the primary evidence for the product observations above. This review changes documentation only.
