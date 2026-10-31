import {useEffect,useRef,useState} from 'react'
import {mergeLibraryRevision,reconcileLibrarySave,subscribeToLibrarySaves} from './libraryDrafts'
export interface LibraryEditDraft {details_revision?:string;label_revision?:string;id:string;title:string;created_at?:string|null;display_name?:string;notes?:string;tags?:string[];favorite?:boolean;archived?:boolean;variant?:string;tools?:string[];synthetic?:boolean;identity_status?:string;difference_count?:number}
type Item=LibraryEditDraft
function labelOf(item:Item){return {display_name:item.display_name??'',notes:item.notes??'',tags:item.tags??[],favorite:item.favorite??false,archived:item.archived??false}}
export default function WorkspaceLibrary({onOpen,onDeleted,onImport,onOrganized,drafts:retainedDrafts}:{onOpen:(id:string)=>void;onDeleted:(id:string)=>void;onImport:(file:File)=>void;onOrganized?:(item:{id:string;title:string;display_name:string;created_at?:string|null;archived:boolean})=>void;drafts?:Map<string,LibraryEditDraft>}) {
  const localDrafts=useRef(new Map<string,Item>()),drafts=retainedDrafts??localDrafts.current
  const [query,setQuery]=useState(''),[offset,setOffset]=useState(0),[items,setItems]=useState<Item[]>([]),[total,setTotal]=useState(0),[hasMore,setHasMore]=useState(false)
  const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[refresh,setRefresh]=useState(0)
  const [view,setView]=useState('active'),[favorite,setFavorite]=useState(false),[source,setSource]=useState(''),[since,setSince]=useState(''),[sort,setSort]=useState('newest')
  const [editing,setEditing]=useState<Item|null>(()=>[...drafts.values()].at(-1)??null),[selected,setSelected]=useState<string[]>([])
  function editDetails(item:Item){setEditing(drafts.get(item.id)??{...item})}
  function updateEditing(item:Item){drafts.delete(item.id);drafts.set(item.id,item);setEditing(item)}
  const requestRevision=useRef(0),live=useRef(true)
  const cursors=useRef<(string|null)[]>([null]),ceiling=useRef<number|null>(null)
  const [nextCursor,setNextCursor]=useState<string|null>(null)
  useEffect(()=>subscribeToLibrarySaves(drafts,(id,saved,details)=>{
    setEditing(previous=>previous?.id===id?mergeLibraryRevision(previous,saved,details):previous)
  }),[drafts])
  useEffect(()=>{live.current=true;return()=>{live.current=false;requestRevision.current++}},[])
  function resetPages(){cursors.current=[null];ceiling.current=null;setOffset(0)}
  function change(fn:()=>void){requestRevision.current++;resetPages();fn();setSelected([])}
  useEffect(()=>{
    const revision=++requestRevision.current;setLoading(true)
    const params=new URLSearchParams({q:query,offset:String(offset),limit:'50',view,favorite:String(favorite),source,since,sort})
    if(since){const midnight=new Date(`${since}T00:00:00`);if(Number.isFinite(midnight.getTime()))params.set('since_instant',midnight.toISOString())}
    const cursor=cursors.current[offset/50];if(cursor)params.set('cursor',cursor)
    if(ceiling.current!==null)params.set('ceiling',String(ceiling.current))
    fetch(`/api/workspace/library?${params}`).then(async response=>{if(!response.ok)throw new Error(`Comparison library unavailable (${response.status})`);return response.json()}).then(body=>{
      if(!live.current||revision!==requestRevision.current)return
      if(!body.items.length&&offset>0){setOffset(Math.max(0,offset-50));return}
      ceiling.current=body.ceiling;cursors.current=cursors.current.slice(0,offset/50+1);setNextCursor(body.next_cursor)
      setItems(body.items);setTotal(body.total);setHasMore(body.has_more);setError('')
    }).catch(e=>{if(live.current&&revision===requestRevision.current)setError(e.message)}).finally(()=>{if(live.current&&revision===requestRevision.current)setLoading(false)})
  },[query,offset,view,favorite,source,since,sort,refresh])
  async function organize(item:Item,patch:Partial<ReturnType<typeof labelOf>>,guardRevision=false) {
    setBusy(true);setError('')
    try{
      const guard=guardRevision?(item.details_revision?{expected_details_revision:item.details_revision}:item.label_revision?{expected_revision:item.label_revision}:{}):{}
      const response=await fetch(`/api/workspace/library/${item.id}/label`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...patch,...guard})})
      if(!response.ok){const body=await response.json();throw new Error(typeof body.detail==='string'?body.detail:'Library label could not be saved')}
      const saved=await response.json()
      reconcileLibrarySave(drafts,item,saved,guardRevision)
      onOrganized?.({id:item.id,title:item.title,created_at:item.created_at,display_name:saved.display_name??item.display_name??'',archived:saved.archived??item.archived??false})
      if(live.current){requestRevision.current++;if(guardRevision)setEditing(null);else setEditing(previous=>{
        if(previous?.id!==item.id)return previous
        const next={...previous,favorite:saved.favorite,archived:saved.archived}
        if(drafts.has(item.id))drafts.set(item.id,next)
        return next
      });resetPages();setRefresh(v=>v+1);setNotice(patch.archived===true?'Comparison archived. Restore it from the Archived view.':patch.archived===false?'Comparison restored.':'Library details saved. Scientific inputs and fingerprints are unchanged.')}
    }catch(e){if(live.current)setError(e instanceof Error?e.message:'Unable to save library details')}
    finally{if(live.current)setBusy(false)}
  }
  async function remove(item:Item) {
    if(!window.confirm(`Permanently delete “${item.display_name||item.title}” (${item.id}) from this local database? This cannot be undone. Archive it instead to keep a recovery path.`))return
    setBusy(true);setError('')
    try{
      const response=await fetch(`/api/investigations/${item.id}`,{method:'DELETE'})
      if(!response.ok){const body=await response.json();throw new Error(body.detail||'Deletion failed')}
      drafts.delete(item.id)
      if(live.current){requestRevision.current++;setEditing(previous=>previous?.id===item.id?null:previous);setLoading(true);setItems(previous=>previous.filter(old=>old.id!==item.id));onDeleted(item.id);setSelected(old=>old.filter(id=>id!==item.id));setRefresh(v=>v+1)}
    }catch(e){if(live.current)setError(e instanceof Error?e.message:'Deletion failed')}
    finally{if(live.current)setBusy(false)}
  }
  async function exportSelected(){
    setBusy(true);setError('')
    try{
      const response=await fetch('/api/workspace/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:selected})})
      if(!response.ok){const body=await response.json();throw new Error(body.detail||'Export failed')}
      const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='genomedebugger-selected-bundles.zip';a.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
      if(live.current)setNotice('Downloaded individual replay-checked bundles in an archive. Extract it and import each bundle from Saved comparisons.')
    }catch(e){if(live.current)setError(e instanceof Error?e.message:'Export failed')}
    finally{if(live.current)setBusy(false)}
  }
  return <section className="panel library-panel"><div className="panel-heading"><div><span className="eyebrow">Your saved work</span><h2>Your saved comparisons</h2><p>Find comparisons by name, notes, tags, or record ID. Archive keeps a comparison available for restoration; permanent deletion does not. Pinned tests protect their underlying records from deletion.</p></div><span className="count-badge">{items.length} of {total} shown</span></div>
    <label className="button secondary bundle-import">Import replay-checked bundle<input aria-label="Import replay-checked bundle" type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files?.[0];if(file)onImport(file);e.target.value=''}}/></label><p className="source-caveat">Replay and hashes check stored consistency, not who supplied external source data.</p>
    <div className="library-filters"><label className="guide-field">Search investigations<input value={query} onChange={e=>change(()=>setQuery(Array.from(e.target.value).slice(0,200).join('')))} placeholder="Name, notes, tag, or record ID"/></label><label className="guide-field">Show<select aria-label="Show" value={view} onChange={e=>change(()=>setView(e.target.value))}><option value="active">Active comparisons</option><option value="archived">Archived comparisons</option><option value="all">All comparisons</option></select></label><label className="guide-field">Sort<select aria-label="Sort" value={sort} onChange={e=>change(()=>setSort(e.target.value))}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="name">Name</option></select></label></div>
    <details className="optional-fields"><summary>More filters</summary><div className="readable-pair"><label className="guide-field">Source name<input value={source} maxLength={100} onChange={e=>change(()=>setSource(e.target.value))}/></label><label className="guide-field">Saved on or after (your local date)<input type="date" value={since} onChange={e=>change(()=>setSince(e.target.value))}/></label></div><label><input type="checkbox" checked={favorite} onChange={e=>change(()=>setFavorite(e.target.checked))}/> Favorites only</label></details>
    {error&&<p className="error" role="alert">{error}</p>}{notice&&<p role="status" className="input-notice">{notice}</p>}
    <div className="source-actions"><button className="button secondary" disabled={busy||loading||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous records</button><span>Page {offset/50+1}</span><button className="button secondary" disabled={busy||loading||!hasMore} onClick={()=>{cursors.current[offset/50+1]=nextCursor;setOffset(offset+50)}}>Next records</button><button className="button secondary" disabled={busy||loading} onClick={()=>{requestRevision.current++;resetPages();setRefresh(v=>v+1)}}>Refresh records</button><button className="button secondary" disabled={busy||!selected.length} onClick={()=>void exportSelected()}>Export selected bundles ({selected.length})</button></div>
    <div className="library-list" aria-busy={loading}>{items.map(item=><article className="library-row" key={item.id}><div><label className="library-select"><input type="checkbox" aria-label={`Select ${item.display_name||item.title}`} checked={selected.includes(item.id)} disabled={!selected.includes(item.id)&&selected.length>=20} onChange={e=>setSelected(previous=>e.target.checked?[...previous,item.id]:previous.filter(id=>id!==item.id))}/><strong>{item.display_name||item.title}</strong></label><small>{item.created_at?new Date(item.created_at).toLocaleString():'Date unavailable for legacy record'} · {item.id}</small>{item.variant&&<p>{item.variant}</p>}{item.tools&&<p>{item.tools.join(' compared with ')}</p>}{item.identity_status&&<small>{item.synthetic?'Made-up example · ':''}DNA context: {item.identity_status} · {item.difference_count} changed values{item.archived?' · Archived':''}</small>}{!!item.tags?.length&&<p>{item.tags.map((tag,i)=><span className="library-tag" key={i}>{tag}</span>)}</p>}{item.notes&&<details><summary>Notes</summary><p>{item.notes}</p></details>}</div><div className="library-actions"><button className="button primary" onClick={()=>onOpen(item.id)}>Open</button><button className="button secondary" disabled={busy} onClick={()=>editDetails(item)}>Edit details</button><button className="button secondary" aria-pressed={item.favorite??false} disabled={busy} onClick={()=>void organize(item,{favorite:!item.favorite})}>{item.favorite?'Unfavorite':'Favorite'}</button><button className="button secondary" disabled={busy} onClick={()=>void organize(item,{archived:!item.archived})}>{item.archived?'Restore':'Archive'}</button><details><summary>Permanent deletion</summary><button className="button danger" disabled={busy} onClick={()=>void remove(item)}>Delete</button></details></div></article>)}{!loading&&!items.length&&<p>No saved investigations match these filters. Try clearing the search or changing the view.</p>}</div>
    {editing&&<section className="library-editor" aria-label="Edit comparison details"><h3>Edit library details</h3><p><strong>{editing.display_name||editing.title}</strong>. Unsaved details stay available when you switch records or sections while this app is open. Save them before closing the app.</p><p>These labels do not change the saved scientific input or its fingerprint.</p><label className="guide-field">Display name<input disabled={busy} value={editing.display_name??''} maxLength={150} onChange={e=>updateEditing({...editing,display_name:e.target.value})}/></label><label className="guide-field">Notes<textarea disabled={busy} value={editing.notes??''} maxLength={4000} onChange={e=>updateEditing({...editing,notes:e.target.value})}/></label><label className="guide-field">Tags (comma separated)<input disabled={busy} value={(editing.tags??[]).join(',')} onChange={e=>updateEditing({...editing,tags:e.target.value.split(',')})}/></label><div className="source-actions"><button className="button primary" disabled={busy} onClick={()=>void organize(editing,{display_name:editing.display_name??'',notes:editing.notes??'',tags:(editing.tags??[]).map(t=>t.trim()).filter(Boolean)},true)}>Save library details</button><button className="button secondary" disabled={busy} onClick={()=>{drafts.delete(editing.id);setEditing(null)}}>Cancel editing</button></div></section>}
  </section>
}
