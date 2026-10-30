import {useMemo,useState} from 'react'
import type {Annotation,Result,Variant} from './types'
interface Row {key:string;variant:Variant;a:Annotation[];b:Annotation[]}
export default function VariantReview({result}:{result:Result}) {
  const [query,setQuery]=useState(''),[selected,setSelected]=useState<string[]>([])
  const rows=useMemo(()=>{
    const map=new Map<string,Row>()
    result.input.snapshots.forEach((snapshot,index)=>{
      for(const record of [{variant:snapshot.variant,annotations:[snapshot.annotation,...snapshot.annotations??[]]},...snapshot.variant_records??[]]){
        const v=record.variant,key=JSON.stringify([v.assembly,v.sequence_id,v.position,v.ref,v.alt])
        const row=map.get(key)??{key,variant:v,a:[],b:[]};row[index===0?'a':'b']=record.annotations;map.set(key,row)
      }
    })
    return [...map.values()]
  },[result.id])
  if(!result.input.snapshots.some(s=>s.variant_records?.length||s.annotations?.length))return null
  const visible=rows.filter(row=>`${row.variant.assembly} ${row.variant.sequence_id} ${row.variant.position} ${row.variant.ref} ${row.variant.alt} ${[...row.a,...row.b].map(a=>`${a.gene_id} ${a.transcript_id} ${a.consequence}`).join(' ')}`.toLowerCase().includes(query.toLowerCase()))
  function exportRows(){const content={format:'GenomeDebugger selected-row reading summary',comparison_id:result.id,matching:'Exact submitted representation only; not independent allele equivalence or causal proof',rows:rows.filter(row=>selected.includes(row.key))};const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=`genomedebugger-${result.id}-selected-rows.json`;a.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return <section className="panel variant-review"><h2>Review all represented variants</h2><p>Rows are aligned by exact assembly, accession, position, and alleles. Unmatched rows are shown explicitly. This table does not normalize additional variants or establish cross-assembly equivalence.</p><label className="guide-field">Find a variant or annotation<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label><p>{visible.length} of {rows.length} representations shown.</p><div className="table-scroll"><table><thead><tr><th>Select</th><th>DNA description</th><th>Present in</th><th>Annotation rows A / B</th></tr></thead><tbody>{visible.map(row=><tr key={row.key}><td><input type="checkbox" aria-label={`Select variant ${row.variant.sequence_id}:${row.variant.position} ${row.variant.ref}>${row.variant.alt}`} checked={selected.includes(row.key)} onChange={e=>setSelected(previous=>e.target.checked?[...previous,row.key]:previous.filter(key=>key!==row.key))}/></td><th>{row.variant.assembly} {row.variant.sequence_id}:{row.variant.position} {row.variant.ref}→{row.variant.alt}</th><td>{row.a.length&&row.b.length?'Both analyses':row.a.length?'Analysis A only':'Analysis B only'}</td><td>{row.a.length} / {row.b.length}<details><summary>Reported outputs</summary><p>A: {row.a.map(a=>`${a.transcript_id}: ${a.consequence}`).join('; ')||'No exact representation'}</p><p>B: {row.b.map(a=>`${a.transcript_id}: ${a.consequence}`).join('; ')||'No exact representation'}</p></details></td></tr>)}</tbody></table></div><button className="button secondary" disabled={!selected.length} onClick={exportRows}>Export selected row summary ({selected.length})</button><p className="source-caveat">This reading summary is not an importable investigation or a full evidence bundle. Use Full bundle to transfer a reproducible comparison.</p></section>
}
