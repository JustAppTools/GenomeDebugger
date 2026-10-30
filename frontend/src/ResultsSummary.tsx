import {ArrowRight, CheckCircle2, CircleHelp, ListFilter} from 'lucide-react'
import type {Result} from './types'
import {comparisonStory,describeEffect,glossary} from './explanations'
import {isCollectionInput} from './comparisonMode'

export function explainResult(result:Result) {
  const count=result.differences.length
  const important=result.differences.filter(item=>item.meaningful).length
  const identity=isCollectionInput(result.input)?result.identity.explanation:result.identity.status==='verified'
    ?'The edits match in the reference text provided.'
    :result.identity.status==='rejected'
      ?'The edits produce different changes in the reference text provided.'
      :'There is not enough information to confirm whether these describe the same DNA change.'
  const verified=result.findings.some(item=>item.status==='verified')
  const possible=result.findings.some(item=>item.status==='possible'||item.status==='probable')
  const explanation=count===0?'There are no changed fields to explain.'
    :verified&&result.input.synthetic?'An explanation was reproduced within this made-up example.'
    :verified?'An explanation was reproduced for some of the observed changes.'
    :possible?'There are possible explanations, but the cause has not been proved.'
    :'The available information does not establish why the results differ.'
  return {identity,explanation,count,important}
}

export default function ResultsSummary({result,onChanges,onEvidence}:{result:Result;onChanges:()=>void;onEvidence:(id:string)=>void}) {
  const summary=explainResult(result)
  const collection=isCollectionInput(result.input)
  const identityEvidence=result.identity.evidence_ids.find(id=>result.evidence.some(item=>item.id===id))
  return <section className="plain-summary" aria-label="Comparison explained">
    <div className="plain-summary-heading"><div><span className="eyebrow">AT A GLANCE</span><h2>What this comparison tells you</h2></div>{result.input.synthetic&&<span className="example-badge">Made-up example</span>}</div>
    <p className="comparison-story">{comparisonStory(result)}</p>
    {result.input.snapshots.length===2&&<div className="outcome-pair">{result.input.snapshots.map((snapshot,i)=><article key={snapshot.id}><span>Analysis {'AB'[i]}</span><h3>{snapshot.label}</h3>{collection?<p>{1+(snapshot.variant_records?.length??0)} represented variants · {1+(snapshot.annotations?.length??0)+(snapshot.variant_records??[]).reduce((n,r)=>n+r.annotations.length,0)} annotation rows. All supplied rows are compared.</p>:<><p>{describeEffect(snapshot.annotation.consequence)}</p><code>{snapshot.annotation.consequence}</code></>}<small>{snapshot.provenance.tool} {snapshot.provenance.tool_version} · {snapshot.provenance.source_name} {snapshot.provenance.source_release}</small></article>)}</div>}
    {collection&&<p className="source-caveat">Tabular overview rows are stable display anchors sorted by variant and gene/transcript identifiers. They do not declare a preferred transcript or biological selection. All supplied rows remain part of the comparison.</p>}<div className="plain-summary-grid"><article><CheckCircle2 size={20}/><h3>{collection?'Do the represented DNA changes match?':'Is it the same DNA change?'}</h3><p>{summary.identity}</p><small>Matching supplied text alone does not independently verify a reference genome.</small>{identityEvidence&&<button className="text-button" onClick={()=>onEvidence(identityEvidence)}>How was this checked? <ArrowRight size={13}/></button>}</article><article><ListFilter size={20}/><h3>What changed?</h3><p>{summary.count===0?'No compared values changed.':`${summary.count} ${summary.count===1?'value changed':'values changed'}; ${summary.important} marked important by the comparison rules.`}</p><small>“Important” describes the comparison settings, not medical significance.</small><button className="text-button" onClick={onChanges}>See the changes <ArrowRight size={13}/></button></article><article><CircleHelp size={20}/><h3>Do we know why?</h3><p>{summary.explanation}</p><small>A difference can be real even when its cause is uncertain.</small></article></div>
    <div className="check-scope" aria-label="What has been checked"><h3>What has been checked?</h3><dl><div><dt>Supplied DNA descriptions</dt><dd>{result.identity.status==='verified'?'Match within supplied reference text':result.identity.status==='rejected'?'Different within supplied reference text':'Unresolved'}</dd></div><div><dt>External reference</dt><dd>{result.input.reference_check?`Linked NCBI observation: ${result.input.reference_check.status}. This checks the allele and notation, not predicted effects.`:'No external reference check is linked to these input snapshots. Separately saved checks can be reviewed under Optional reference check.'}</dd></div><div><dt>Annotation output</dt><dd>{result.input.annotation_check?`Linked SnpEff output comparison: ${result.input.annotation_check.status}. Inspect its preserved execution provenance separately.`:'No independent annotation-output check is linked.'}</dd></div><div><dt>Source of these values</dt><dd>{result.input.synthetic?'Constructed synthetic example':result.input.snapshots.some(s=>s.provenance.configuration?.source_record_id)?'Linked preserved sources; review origin and capture details below':'User-supplied analysis and declared metadata'}</dd></div></dl></div>
    <details className="terms-guide"><summary>Explain the terms</summary><dl>{glossary.map(([term,definition])=><div key={term}><dt>{term}</dt><dd>{definition}</dd></div>)}</dl></details>
  </section>
}
