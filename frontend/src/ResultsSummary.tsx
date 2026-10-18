import {ArrowRight, CheckCircle2, CircleHelp, ListFilter} from 'lucide-react'
import type {Result} from './types'

export function explainResult(result:Result) {
  const count=result.differences.length
  const important=result.differences.filter(item=>item.meaningful).length
  const identity=result.identity.status==='verified'
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
  const identityEvidence=result.identity.evidence_ids.find(id=>result.evidence.some(item=>item.id===id))
  return <section className="plain-summary" aria-label="Comparison explained">
    <div className="plain-summary-heading"><div><span className="eyebrow">AT A GLANCE</span><h2>What this comparison tells you</h2></div>{result.input.synthetic&&<span className="example-badge">Made-up example</span>}</div>
    <div className="plain-summary-grid"><article><CheckCircle2 size={20}/><h3>Is it the same DNA change?</h3><p>{summary.identity}</p><small>Matching supplied text alone does not independently verify a reference genome.</small>{identityEvidence&&<button className="text-button" onClick={()=>onEvidence(identityEvidence)}>How was this checked? <ArrowRight size={13}/></button>}</article><article><ListFilter size={20}/><h3>What changed?</h3><p>{summary.count===0?'No compared values changed.':`${summary.count} ${summary.count===1?'value changed':'values changed'}; ${summary.important} marked important by the comparison rules.`}</p><small>“Important” describes the comparison settings, not medical significance.</small><button className="text-button" onClick={onChanges}>See the changes <ArrowRight size={13}/></button></article><article><CircleHelp size={20}/><h3>Do we know why?</h3><p>{summary.explanation}</p><small>A difference can be real even when its cause is uncertain.</small></article></div>
    <details className="terms-guide"><summary>Explain the terms</summary><dl><div><dt>DNA change (variant)</dt><dd>A difference in DNA letters at a particular location.</dd></div><div><dt>Transcript</dt><dd>One RNA version produced from a gene. Different versions can receive different predictions.</dd></div><div><dt>Predicted effect (consequence)</dt><dd>What an analysis tool predicts a DNA change might affect. A prediction is not a diagnosis.</dd></div><div><dt>Source version</dt><dd>The release of a database or reference used by an analysis.</dd></div><div><dt>Supporting details (evidence)</dt><dd>The saved inputs and comparisons behind a conclusion. They help you check how it was reached.</dd></div></dl></details>
  </section>
}
