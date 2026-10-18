import { useEffect, useState } from 'react'

interface Item {id:string;title:string;created_at?:string|null}
export default function InvestigationLibrary({onOpen,onDeleted,onImport}:{onOpen:(id:string)=>void;onDeleted:(id:string)=>void;onImport:(file:File)=>void}) {
  const [query,setQuery] = useState('')
  const [offset,setOffset] = useState(0)
  const [hasMore,setHasMore] = useState(false)
  const [items,setItems] = useState<Item[]>([])
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  useEffect(()=>{
    let live = true
    fetch(`/api/investigations?q=${encodeURIComponent(query)}&limit=101&offset=${offset}`).then(async response=>{
      if (!response.ok) throw new Error(`Investigation list unavailable (${response.status})`)
      return await response.json() as Item[]
    }).then(found=>{if(live){setItems(found.slice(0,100));setHasMore(found.length>100);setError('')}}).catch(e=>{if(live)setError(e instanceof Error?e.message:'Unable to load investigations')})
    return ()=>{live=false}
  },[query,offset])
  async function remove(item:Item) {
    if (!window.confirm(`Delete “${item.title}” (${item.id}) from this local database? This cannot be undone.`)) return
    setBusy(true);setError('')
    try {
      const response = await fetch(`/api/investigations/${item.id}`,{method:'DELETE'})
      if (!response.ok) {const body=await response.json();throw new Error(body.detail||`Deletion failed (${response.status})`)}
      setItems(previous=>previous.filter(existing=>existing.id!==item.id));onDeleted(item.id)
    } catch(e) {setError(e instanceof Error?e.message:'Deletion failed')}
    finally {setBusy(false)}
  }
  return <section className="panel library-panel"><div className="panel-heading"><div><span className="eyebrow">LOCAL RECORDS</span><h2>Investigation library</h2><p>Search saved investigations by title or record ID. Records with pinned regression cases are protected from deletion.</p></div><span className="count-badge">{items.length} shown</span></div>
    <label className="button secondary bundle-import">Import replay-checked bundle<input aria-label="Import replay-checked bundle" type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files?.[0];if(file)onImport(file);e.target.value=''}}/></label><p className="source-caveat">The import check recomputes investigation results and stored hashes. It cannot authenticate who supplied external source data.</p>
    <label className="guide-field">Search investigations<input aria-label="Search investigations" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0)}} placeholder="Title or record ID"/></label>
    {error&&<div className="error" role="alert">{error}</div>}
    <div className="source-actions"><button className="button secondary" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-100))}>Previous records</button><span>Page {offset/100+1}</span><button className="button secondary" disabled={!hasMore} onClick={()=>setOffset(offset+100)}>Next records</button></div>
    <div className="library-list">{items.map(item=><div className="library-row" key={item.id}><div><strong>{item.title}</strong><small>{item.created_at?new Date(item.created_at).toLocaleString():'Date unavailable for legacy record'} · {item.id}</small></div><div><button className="button secondary" onClick={()=>onOpen(item.id)}>Open</button><button className="button danger" disabled={busy} onClick={()=>remove(item)}>Delete</button></div></div>)}{items.length===0&&<p>No saved investigations match this search.</p>}</div>
  </section>
}
