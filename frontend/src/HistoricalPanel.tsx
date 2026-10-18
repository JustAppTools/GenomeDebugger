import { useState } from 'react'
import type { Result } from './types'

interface Source {
  id:string;origin:'current_api'|'historical_artifact';releases:number[];retrieved_at:string
  query:{chromosome:string;position:number;ref:string;alt:string}
  transcripts:{transcript_id:string;consequence_terms:string[]}[]
  artifact?:{generated_at:string;sha256:string;tool_version:string}|null
}

export default function HistoricalPanel({onCompare}:{onCompare:(value:Result)=>void}) {
  const [raw,setRaw]=useState('')
  const [query,setQuery]=useState({chromosome:'1',position:'6524705',ref:'C',alt:'T'})
  const [release,setRelease]=useState('')
  const [version,setVersion]=useState('')
  const [date,setDate]=useState('')
  const [assembly,setAssembly]=useState('GCA_000001405.29')
  const [uri,setUri]=useState('')
  const [records,setRecords]=useState<Source[]>([])
  const [hasMore,setHasMore]=useState(false)
  const [ids,setIds]=useState(['',''])
  const [transcripts,setTranscripts]=useState(['',''])
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  async function readArtifact(file:File) {
    setRaw('');setError('');setNotice('')
    if(file.size>250000){setError('Historical VEP output exceeds 250 KB');return}
    try {
      // Preserve a UTF-8 BOM if present so the saved hash covers original bytes.
      setRaw(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await file.arrayBuffer()))
    } catch {setError('Historical VEP output must be valid UTF-8 text')}
  }
  async function list(more=false) {
    const response=await fetch(more?`/api/sources/records?offset=${records.length}&limit=200`:'/api/sources/records')
    if(!response.ok)throw new Error('Preserved sources are unavailable')
    const found=await response.json() as Source[]
    setHasMore(found.length===200)
    setRecords(more?[...records,...found]:found)
    if(more)return
    const selected=[found[0],found[1]??found[0]]
    setIds(selected.map(item=>item?.id??''));setTranscripts(selected.map(item=>item?.transcripts[0]?.transcript_id??''))
  }
  async function run(action:'list'|'more'|'import'|'compare') {
    setBusy(true);setError('');setNotice('')
    try {
      if(action==='list'||action==='more'){await list(action==='more');return}
      const url=action==='import'?'/api/sources/historical-vep':'/api/sources/compare'
      const payload=action==='import'?{query:{...query,position:Number(query.position)},raw_json:raw,
        source_release:Number(release),tool_version:version,generated_at:new Date(date).toISOString(),
        assembly_accession:assembly,source_uri:uri}:
        {source_a:ids[0],source_b:ids[1],transcript_a:transcripts[0],transcript_b:transcripts[1],title:'Historical and preserved source comparison'}
      const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
      const body=await response.json()
      if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:`Preserved source action failed (${response.status}); check the declared fields`)
      if(action==='import'){setNotice(`Historical output preserved as ${body.id}. Its date, release, and software version are user declared.`);await list()}
      else onCompare(body)
    } catch(e){setError(e instanceof Error?e.message:'Preserved source action failed')}
    finally{setBusy(false)}
  }
  return <section className="panel source-panel"><span className="eyebrow">PRESERVED HISTORICAL OUTPUT</span><h2>Reconstruct a comparison from saved VEP output</h2>
    <p>Import an actual VEP JSON output for one GRCh38 SNV with its original run metadata, then compare it with another preserved source. The uploaded bytes and metadata are hashed and bundled. Declared dates and versions are not independently authenticated; current API responses are never treated as historical evidence.</p>
    <details><summary>Import historical VEP output</summary>
      <label className="guide-field">VEP JSON file<input aria-label="Historical VEP JSON file" type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files?.[0];if(file)void readArtifact(file);e.target.value=''}}/></label>
      <div className="source-fields">{(['chromosome','position','ref','alt'] as const).map(key=><label key={key}>{key}<input aria-label={`Historical ${key}`} value={query[key]} onChange={e=>setQuery({...query,[key]:e.target.value})}/></label>)}</div>
      <div className="source-fields"><label>Ensembl release<input aria-label="Historical Ensembl release" type="number" min="1" value={release} onChange={e=>setRelease(e.target.value)}/></label><label>VEP software version<input aria-label="Historical VEP version" value={version} onChange={e=>setVersion(e.target.value)}/></label><label>Original run time (local)<input aria-label="Historical run time" type="datetime-local" value={date} onChange={e=>setDate(e.target.value)}/></label><label>Assembly accession<input aria-label="Historical assembly accession" value={assembly} onChange={e=>setAssembly(e.target.value)}/></label></div>
      <label className="guide-field">Original run source or artifact location<input aria-label="Historical artifact source" value={uri} onChange={e=>setUri(e.target.value)}/></label>
      <button className="button secondary" disabled={busy||!raw||!release||!version||!date||!uri} onClick={()=>run('import')}>Preserve historical output</button>
    </details>
    <div className="source-actions"><button className="button secondary" disabled={busy} onClick={()=>run('list')}>Load preserved sources</button></div>
    {hasMore&&<button className="button secondary" disabled={busy} onClick={()=>run('more')}>Load older sources</button>}
    {records.length>0&&<><div className="guide-grid">{ids.map((id,index)=>{
      const selected=records.find(item=>item.id===id)
      return <div key={index}><h3>Analysis {index?'B':'A'}</h3><label className="guide-field">Source record<select aria-label={`Preserved analysis ${index+1} source`} value={id} onChange={e=>{const next=[...ids];next[index]=e.target.value;setIds(next);const rows=[...transcripts];rows[index]=records.find(item=>item.id===e.target.value)?.transcripts[0]?.transcript_id??'';setTranscripts(rows)}}>{records.map(item=><option value={item.id} key={item.id}>{item.origin==='historical_artifact'?'Historical artifact':'Current API capture'} · release {item.releases.join(',')} · {item.query.chromosome}:{item.query.position} · {item.id}</option>)}</select></label>
        <label className="guide-field">Transcript<select aria-label={`Preserved analysis ${index+1} transcript`} value={transcripts[index]} onChange={e=>{const next=[...transcripts];next[index]=e.target.value;setTranscripts(next)}}>{selected?.transcripts.map(row=><option key={row.transcript_id} value={row.transcript_id}>{row.transcript_id} · {row.consequence_terms.join(', ')}</option>)}</select></label>
        {selected?.artifact&&<p className="record-hash">Declared run: {selected.artifact.generated_at} · VEP {selected.artifact.tool_version} · Original artifact SHA-256 {selected.artifact.sha256}</p>}
      </div>
    })}</div><button className="button primary" disabled={busy||ids.some(id=>!id)||transcripts.some(id=>!id)||(ids[0]===ids[1]&&transcripts[0]===transcripts[1])} onClick={()=>run('compare')}>Compare preserved sources</button></>}
    {error&&<div className="error" role="alert">{error}</div>}{notice&&<div className="input-notice" role="status">{notice}</div>}
  </section>
}
