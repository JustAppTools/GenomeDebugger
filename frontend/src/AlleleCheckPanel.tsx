import { useState } from 'react'

interface Observation {
  accession:string;reference_matches:boolean;reference_uri:string;reference_sha256:string
  contextual_uri:string;contextual_sha256:string|null;hgvs:string|null
  normalized:{seq_id:string;position:number;deleted_sequence:string;inserted_sequence:string}|null
}
interface Check {id:string;status:'agree'|'disagree';explanation:string;checked_at:string;observations:Observation[]}

export default function AlleleCheckPanel({id,synthetic}:{id:string;synthetic:boolean}) {
  const [check,setCheck]=useState<Check|null>(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  async function run(mode:'fetch'|'cache_only') {
    setBusy(true);setError('')
    try {
      const response=await fetch(`/api/investigations/${id}/allele-check`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})})
      const body=await response.json()
      if(!response.ok) throw new Error(typeof body.detail==='string'?body.detail:`Reference check failed (${response.status})`)
      setCheck(body)
    } catch(e) {setError(e instanceof Error?e.message:'Reference check failed')}
    finally {setBusy(false)}
  }
  return <section className="panel source-panel"><span className="eyebrow">REFERENCE-BACKED ALLELE IDENTITY</span><h2>Normalize both alleles with NCBI</h2>
    <p className="source-caveat">Check each submitted reference against pinned GRCh38.p14 RefSeq sequence, then compare NCBI contextual SPDI alleles, including length-changing variants. Clicking Check sends the two accessions, coordinates and alleles to NCBI. Results and raw responses stay linked to this investigation and its bundle. Cross-assembly identity remains outside this check.</p>
    {synthetic&&<p>Synthetic demonstrations cannot be submitted as real reference observations.</p>}
    <div className="source-actions"><button className="button secondary" disabled={busy} onClick={()=>run('cache_only')}>Load saved allele check</button><button className="button primary" disabled={busy||synthetic} onClick={()=>run('fetch')}>Check allele identity with NCBI</button></div>
    {error&&<div className="error" role="alert">{error}</div>}
    {check&&<div className="snpeff-result"><p><strong>{check.status.toUpperCase()}</strong> · {check.explanation}</p><small>Check {check.id} · {new Date(check.checked_at).toLocaleString()}</small>
      {check.observations.map((item,index)=><div className="guide-extra" key={index}><h3>Analysis {index?'B':'A'}</h3><p>Reference matches: {item.reference_matches?'Yes':'No'}</p><code>{item.normalized?`${item.normalized.seq_id}:${item.normalized.position}:${item.normalized.deleted_sequence}:${item.normalized.inserted_sequence}`:'Normalization skipped'}</code><p>{item.hgvs}</p><a href={item.contextual_uri} target="_blank" rel="noreferrer">NCBI contextual SPDI observation</a><p className="record-hash">Response SHA-256 {item.contextual_sha256 ?? 'not retrieved'}</p></div>)}
    </div>}
  </section>
}
