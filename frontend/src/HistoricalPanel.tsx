import { useRef, useState } from 'react'
import type { Result } from './types'

interface Source {
  id:string;origin:'current_api'|'historical_artifact';releases:number[];retrieved_at:string
  query:{chromosome:string;position:number;ref:string;alt:string}
  transcripts:{transcript_id:string;consequence_terms:string[]}[]
  artifact?:{generated_at:string;sha256:string;tool_version:string}|null
}

export default function HistoricalPanel({onCompare,getWorkspaceRevision=()=>0,onWorkspaceChange=()=>{}}:{onCompare:(value:Result)=>void;getWorkspaceRevision?:()=>number;onWorkspaceChange?:()=>void}) {
  const selectionRevision = useRef(0)
  const artifactRevision = useRef(0)
  const [raw,setRaw]=useState('')
  const [query,setQuery]=useState({chromosome:'1',position:'6524705',ref:'C',alt:'T'})
  const [release,setRelease]=useState('')
  const [version,setVersion]=useState('')
  const [date,setDate]=useState('')
  const [assembly,setAssembly]=useState('GCA_000001405.29')
  const [uri,setUri]=useState('')
  const [records,setRecords]=useState<Source[]>([])
  const [hasMore,setHasMore]=useState(false)
  const pageOffset=useRef(0)
  const selection=useRef({ids:['',''],transcripts:['','']})
  const [chosen,setChosen]=useState(selection.current)
  const {ids,transcripts}=chosen
  function choose(next:typeof chosen) {
    if(JSON.stringify(next)!==JSON.stringify(selection.current))onWorkspaceChange()
    selectionRevision.current++;selection.current=next;setChosen(next)
  }
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  async function readArtifact(file:File) {
    const revision=++artifactRevision.current
    setRaw('');setError('');setNotice('')
    if(file.size>250000){setError('Historical VEP output exceeds 250 KB');return}
    try {
      // Preserve a UTF-8 BOM if present so the saved hash covers original bytes.
      const content=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(await file.arrayBuffer())
      if(revision===artifactRevision.current){onWorkspaceChange();setRaw(content)}
    } catch {if(revision===artifactRevision.current)setError('Historical VEP output must be valid UTF-8 text')}
  }
  async function list(more=false) {
    const response=await fetch(more?`/api/sources/records?offset=${pageOffset.current}&limit=200`:'/api/sources/records')
    if(!response.ok)throw new Error('Preserved sources are unavailable')
    const found=await response.json() as Source[]
    if(more){
      pageOffset.current+=found.length
      setHasMore(found.length===200)
      setRecords(previous=>Array.from(new Map([...previous,...found].map(item=>[item.id,item])).values()))
      return
    }
    // A valid selected record may be outside the refreshed first page.
    const retained=new Map(found.map(item=>[item.id,item]))
    const checked=new Set<string>()
    while(true){
      const missing=selection.current.ids.filter(id=>id&&!retained.has(id)&&!checked.has(id))
      if(!missing.length)break
      await Promise.all(missing.map(async id=>{
        checked.add(id)
        const detail=await fetch(`/api/sources/ensembl/records/${encodeURIComponent(id)}`)
        if(detail.status===404)return
        if(!detail.ok)throw new Error('Selected preserved source could not be refreshed; your selection was kept')
        const item=await detail.json() as Source
        retained.set(item.id,item)
      }))
    }
    pageOffset.current=found.length
    setHasMore(found.length===200)
    setRecords(Array.from(retained.values()))
    const previous=selection.current
    const selected=previous.ids.map((id,index)=>retained.get(id)??found[index]??found[0])
    const next={ids:selected.map(item=>item?.id??''),transcripts:selected.map((item,index)=>
      item?.transcripts.some(row=>row.transcript_id===previous.transcripts[index])&&item.id===previous.ids[index]
        ?previous.transcripts[index]:item?.transcripts[0]?.transcript_id??'')}
    if(previous.ids.some((id,index)=>id&&(id!==next.ids[index]||previous.transcripts[index]!==next.transcripts[index])))
      setNotice('A selected source or transcript is no longer available. Review the replacement selection before comparing.')
    choose(next)
  }
  async function run(action:'list'|'more'|'import'|'compare') {
    const selected = selectionRevision.current
    const workspace = getWorkspaceRevision()
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
      else if(selected!==selectionRevision.current)setNotice('Selection changed while comparing. Compare again to use the current selection.')
      else if(workspace!==getWorkspaceRevision())setNotice('Source workspace changed while comparing. Your newer draft was kept; the completed comparison is in Saved comparisons.')
      else onCompare(body)
    } catch(e){if(action==='compare'&&selected!==selectionRevision.current)setNotice('Selection changed while comparing. Compare again to use the current selection.');else setError(e instanceof Error?e.message:'Preserved source action failed')}
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
      return <div key={index}><h3>Analysis {index?'B':'A'}</h3><label className="guide-field">Source record<select aria-label={`Preserved analysis ${index+1} source`} value={id} onChange={e=>{const next=[...ids];next[index]=e.target.value;const rows=[...transcripts];rows[index]=records.find(item=>item.id===e.target.value)?.transcripts[0]?.transcript_id??'';choose({ids:next,transcripts:rows})}}>{records.map(item=><option value={item.id} key={item.id}>{item.origin==='historical_artifact'?'Historical artifact':'Current API capture'} · release {item.releases.join(',')} · {item.query.chromosome}:{item.query.position} · {item.id}</option>)}</select></label>
        <label className="guide-field">Transcript<select aria-label={`Preserved analysis ${index+1} transcript`} value={transcripts[index]} onChange={e=>{const next=[...transcripts];next[index]=e.target.value;choose({ids,transcripts:next})}}>{selected?.transcripts.map(row=><option key={row.transcript_id} value={row.transcript_id}>{row.transcript_id} · {row.consequence_terms.join(', ')}</option>)}</select></label>
        {selected?.artifact&&<p className="record-hash">Declared run: {selected.artifact.generated_at} · VEP {selected.artifact.tool_version} · Original artifact SHA-256 {selected.artifact.sha256}</p>}
      </div>
    })}</div><button className="button primary" disabled={busy||ids.some(id=>!id)||transcripts.some(id=>!id)||(ids[0]===ids[1]&&transcripts[0]===transcripts[1])} onClick={()=>run('compare')}>Compare preserved sources</button></>}
    {error&&<div className="error" role="alert">{error}</div>}{notice&&<div className="input-notice" role="status">{notice}</div>}
  </section>
}
