import type {Result} from './types'
import {displayValue} from './explanations'

export default function ClinicalAssertions({result,compact=false}:{result:Result;compact?:boolean}) {
  const rows=result.input.snapshots.flatMap((snapshot,index)=>[
    {variant:snapshot.variant,annotations:[snapshot.annotation,...snapshot.annotations??[]]},...snapshot.variant_records??[],
  ].flatMap(record=>record.annotations.flatMap(annotation=>annotation.clinical?[{analysis:`Analysis ${'AB'[index]} · ${snapshot.label}`,variant:record.variant,annotation,clinical:annotation.clinical}]:[])))
  if(!rows.length)return null
  const content=<><p>These are the classifications supplied by each analysis. A classification applies to its stated condition and framework. GenomeDebugger does not assess clinical significance.</p><div className="table-scroll"><table><thead><tr><th>Analysis and DNA change</th><th>Gene / transcript</th><th>Condition</th><th>Framework</th><th>Classification as supplied</th><th>Review and date</th></tr></thead><tbody>{rows.map((row,index)=><tr key={index}><td>{row.analysis}<small>{row.variant.assembly} · {row.variant.sequence_id}:{row.variant.position} {row.variant.ref} → {row.variant.alt}</small></td><td>{row.annotation.gene_id}<small>{row.annotation.transcript_id}</small></td><td>{row.clinical.condition_id}</td><td>{row.clinical.framework}</td><td>{row.clinical.classification}</td><td>{displayValue(row.clinical.review_status)}<small>{displayValue(row.clinical.assertion_date)}</small></td></tr>)}</tbody></table></div></>
  return <section className="panel clinical-assertions" aria-label="Supplied clinical assertions">{compact?<details><summary>Clinical assertions: conditions and frameworks</summary>{content}</details>:<><h2>Clinical assertions and their context</h2>{content}</>}</section>
}
