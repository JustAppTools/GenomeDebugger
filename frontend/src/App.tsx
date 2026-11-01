import { useEffect, useMemo, useRef, useState } from 'react'
import { readUtf8 } from './readUtf8'
import { ArrowRight, Check, ChevronDown, ClipboardList, Database, FileJson, FileText, FlaskConical, Info, Search, SlidersHorizontal } from 'lucide-react'
import type { Difference, InvestigationInput, Result, Snapshot } from './types'
import RegressionPanel from './RegressionPanel'
import PublicSourcePanel from './PublicSourcePanel'
import GuidedInput, { blankInput, isGuidedInput, normalizeGuidedInput, validateGuidedInput } from './GuidedInput'
import InvestigationLibrary,{type LibraryEditDraft} from './WorkspaceLibrary'
import AlleleCheckPanel from './AlleleCheckPanel'
import ResultsSummary from './ResultsSummary'
import ClinicalAssertions from './ClinicalAssertions'
import { MAX_BUNDLE_BYTES, MAX_INPUT_BYTES } from './limits'
import EvidenceInspector from './EvidenceInspector'
import ImportWorkspace from './ImportWorkspace'
import HelpPanel from './HelpPanel'
import LocalDataPanel from './LocalDataPanel'
import DraftTools,{DRAFT_KEY,readSavedDraft} from './DraftTools'
import ExampleGuide from './ExampleGuide'
import ReadableReport,{reportHtml} from './ReadableReport'
import {readRoute,writeRoute,type Tab} from './routing'
import SourceProvenance from './SourceProvenance'
import VariantReview from './VariantReview'
import OperationStatus from './OperationStatus'
import {describeEffect} from './explanations'
import {ComparisonSteps,StartComparison,WorkspaceFooter,WorkspaceHeader} from './WorkspaceNavigation'

const API = '/api'

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click()
  window.setTimeout(()=>URL.revokeObjectURL(url),1000)
}

function pill(status: string) { return <span className={`pill pill-${status}`}>{status}</span> }
function identityPill(status: string) { return <span className={`pill pill-${status}`}>{status === 'verified' ? 'local context match' : status}</span> }
function pretty(value: unknown) {
  if(value===null||value===undefined)return 'Not provided'
  if(value==='')return 'Empty text'
  if(typeof value==='string'&&!value.trim())return 'Whitespace only'
  return String(value)
}
function RecordedValue({value,field}:{value:string|null;field:string}){
  const text=pretty(value)
  if(text.length>240)return <details><summary>Recorded text ({text.length} characters)</summary><pre>{text}</pre></details>
  return <><span>{text}</span>{(field==='consequence'||field.endsWith('.consequence'))&&<small className="effect-help">{describeEffect(value)}</small>}</>
}
function validationMessage(detail: unknown): string {
  if (!Array.isArray(detail)) return typeof detail === 'string' ? detail : 'The input does not match the required schema.'
  return detail.map(item => {
    const path = Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== 'body').join('.') : 'Input'
    return `${path || 'Input'}: ${item.msg || 'Invalid value'}`
  }).join('; ')
}

function SnapshotCard({ snapshot, side, referenceCheck, annotationCheck }: {snapshot: Snapshot; side: 'A'|'B'; referenceCheck?: InvestigationInput['reference_check']; annotationCheck?: InvestigationInput['annotation_check']}) {
  return <article className="snapshot-card">
    <div className="snapshot-top"><span className={`side-tag side-${side.toLowerCase()}`}>ANALYSIS {side}</span><span className="mono muted">{snapshot.id}</span></div>
    <h3>{snapshot.label}</h3>
    <div className="variant-string mono"><span>{snapshot.variant.assembly}</span><span>{snapshot.variant.sequence_id}:{snapshot.variant.position}</span><strong>{snapshot.variant.ref} → {snapshot.variant.alt}</strong></div>
    <div className="snapshot-fields">
      <div><label>Gene</label><b>{snapshot.annotation.gene_id}</b></div>
      <div><label>Transcript</label><b>{snapshot.annotation.transcript_id}</b></div>
      <div><label>Consequence</label><b>{snapshot.annotation.consequence}</b></div>
      <div><label>Protein</label><b>{pretty(snapshot.annotation.protein_consequence)}</b></div>
    </div>
    <div className="snapshot-source"><Database size={14}/>{snapshot.provenance.source_name} · {snapshot.provenance.source_release}</div>
    {(snapshot.annotations?.length || snapshot.variant_records?.length) ? <div className="snapshot-linkage">{snapshot.annotations?.length ?? 0} additional annotations · {snapshot.variant_records?.length ?? 0} additional variants</div> : null}
    {snapshot.provenance.configuration?.source_record_id&&<div className="snapshot-linkage">Source record <code>{snapshot.provenance.configuration.source_record_id}</code>{referenceCheck&&<> · NCBI check <code>{referenceCheck.id}</code> ({referenceCheck.status})</>}{annotationCheck&&<> · SnpEff check <code>{annotationCheck.id}</code> ({annotationCheck.status})</>}</div>}
  </article>
}

const fieldNames:Record<string,string>={source_uri:'Source location',input_sha256:'Original input fingerprint',assembly:'Reference genome',sequence_id:'DNA sequence',position:'Position',ref:'Original DNA letters',alt:'Changed DNA letters',gene_id:'Gene',transcript_id:'Transcript',consequence:'Predicted effect',protein_consequence:'Predicted protein change',source_release:'Source version',tool:'Analysis tool',tool_version:'Tool version','configuration.original_utf8':'Original imported file text','configuration.import_filename':'Imported filename','configuration.import_output_edited':'Imported output was edited'}
const categoryNames:Record<string,string>={identity:'DNA identity',representation:'How the change is written',annotation:'Predicted effects',provenance:'Tool and source',configuration:'Analysis settings',clinical:'Clinical assertions',clinical_context:'Assertion context',clinical_metadata:'Assertion dates',variant:'DNA changes'}

function DifferenceTable({ differences, onEvidence }: {differences: Difference[]; onEvidence: (id: string) => void}) {
  const [category, setCategory] = useState('all')
  const [query, setQuery] = useState('')
  const [meaningfulOnly, setMeaningfulOnly] = useState(true)
  const categories = ['all', ...new Set(differences.map(d => d.category))]
  const search = query.trim().toLocaleLowerCase()
  const visible = differences.filter(d => (category === 'all' || d.category === category) && (!meaningfulOnly || d.meaningful) && `${fieldNames[d.field] ?? ''} ${d.field}`.toLocaleLowerCase().includes(search))
  return <section className="panel table-panel">
    <div className="panel-heading"><div><span className="eyebrow">WHAT CHANGED</span><h2>Changes between the results</h2><p>Each row shows a changed value. Priority is set by comparison rules, not medical significance.</p></div><span className="count-badge">{visible.length} of {differences.length} changes shown</span></div>
    <div className="filters"><label className="search"><Search size={16}/><input aria-label="Search fields" placeholder="Search fields" value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="select-wrap"><SlidersHorizontal size={16}/><select aria-label="Filter category" value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(c=><option key={c} value={c}>{c === 'all' ? 'All categories' : categoryNames[c] ?? c.replace('_',' ')}</option>)}</select><ChevronDown size={14}/></label><label className="check" title="Uses comparison rules and overrides; this is not a measure of medical significance."><input type="checkbox" checked={meaningfulOnly} onChange={e=>setMeaningfulOnly(e.target.checked)}/> Prioritized changes only</label></div><p className="filter-summary">{meaningfulOnly?'Other changed values are hidden by this priority filter.':'All priority levels are included.'} {(query||category!=='all')&&'Search or category filters are also active.'} <button className="text-button" onClick={()=>{setMeaningfulOnly(false);setQuery('');setCategory('all')}}>Show every change</button></p>
    <div className="table-scroll"><table><thead><tr><th>FIELD</th><th>ANALYSIS A</th><th>ANALYSIS B</th><th>TYPE</th><th>EVIDENCE</th></tr></thead><tbody>{visible.map(d=><tr key={d.field}><td className="field-name">{fieldNames[d.field] ?? d.field}{fieldNames[d.field]&&<small>{d.field}</small>}</td><td className="mono"><RecordedValue value={d.before} field={d.field}/></td><td className="mono"><RecordedValue value={d.after} field={d.field}/></td><td><span className="type-tag">{categoryNames[d.category] ?? d.category.replace('_',' ')}</span></td><td><button className="text-button" onClick={()=>onEvidence(d.evidence_ids[0])}>Inspect <ArrowRight size={13}/></button></td></tr>)}</tbody></table>{visible.length===0 && <div className="empty-row">No differences match these filters.</div>}</div>
  </section>
}

function inputSignature(text:string):string {
  try {return JSON.stringify(normalizeGuidedInput(JSON.parse(text)),function(_key,value){return value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,value[key]])):value})}
  catch{return text}
}

export default function App() {
  const [inputText, setInputTextState] = useState('')
  const draft = useRef('')
  const draftRevision = useRef(0)
  const selection = useRef(0)
  const exportRequest = useRef(0)
  const pendingOpen = useRef<string|null>(null)
  const undoStack=useRef<string[]>([]),redoStack=useRef<string[]>([])
  function setInputText(value:string) {if(value!==draft.current){undoStack.current=[...undoStack.current,draft.current].slice(-20);redoStack.current=[]};draftRevision.current++;draft.current=value;setInputTextState(value)}
  const comparedDraft=useRef('')
  const libraryDrafts=useRef(new Map<string,LibraryEditDraft>())
  const regressionDrafts=useRef(new Map<string,unknown>())
  const [sourceVisited,setSourceVisited]=useState(false)
  const [inputMode,setInputMode] = useState<'guided'|'json'>('guided')
  const [engineState,setEngineState] = useState<'checking'|'online'|'offline'>('checking')
  const [engineVersion,setEngineVersion] = useState('')
  const [hosted,setHosted]=useState(false)
  const [result, setResult] = useState<Result | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  useEffect(()=>{if(tab==='source')setSourceVisited(true)},[tab])
  const [busy, setBusy] = useState(false)
  const [operation,setOperation]=useState('Working on the requested operation')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reportPreview,setReportPreview]=useState(false)
  const [guideSession,setGuideSession]=useState(0)
  const [savedDraftAvailable,setSavedDraftAvailable]=useState(()=>!!readSavedDraft())
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null)
  const [recent, setRecent] = useState<{id:string;title:string;display_name?:string;archived?:boolean;created_at?:string|null}[]>([])
  const deletedRecent = useRef(new Set<string>())
  const recentMetadataRevision=useRef(0)
  const parsedState = useMemo(() => { try { return {valid:true,value:normalizeGuidedInput(JSON.parse(inputText))} } catch { return {valid:false,value:null} } }, [inputText])
  const parsed=parsedState.value as InvestigationInput|null
  const jsonObject=parsed!==null&&typeof parsed==='object'&&!Array.isArray(parsed)
  const guidedInvalid = inputMode === 'guided' && validateGuidedInput(parsed).length > 0
  const inputChanged = result !== null && inputSignature(inputText)!==inputSignature(comparedDraft.current)
  const routeHandler=useRef<()=>void>(()=>{})
  const handledHash=useRef<string|null>(null)
  const focusDestination=useRef('overview:')
  function routeTo(next:Tab,id?:string|null){writeRoute(next,id);handledHash.current=window.location.hash}
  routeHandler.current=()=>{
    if(handledHash.current===window.location.hash)return
    handledHash.current=window.location.hash
    const route=readRoute();selection.current++;pendingOpen.current=null;setBusy(false)
    if(route.id&&route.id!==result?.id){setResult(null);void openInvestigation(route.id,selection.current,draftRevision.current,route.tab)}
    else {if(!route.id&&route.tab==='overview')setResult(null);setTab(route.tab)}
  }
  useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(libraryDrafts.current.size){event.preventDefault();event.returnValue=''}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[])
  useEffect(()=>{if(window.location.hash)routeHandler.current();const handler=()=>routeHandler.current();window.addEventListener('popstate',handler);window.addEventListener('hashchange',handler);return()=>{window.removeEventListener('popstate',handler);window.removeEventListener('hashchange',handler)}},[])
  useEffect(()=>{
    setReportPreview(false)
    const destination=`${tab}:${result?.id??''}`
    // Initial rendering must not steal focus from someone already tabbing.
    // Only an actual destination change moves focus to the page heading.
    if(focusDestination.current===destination)return
    focusDestination.current=destination
    document.querySelector<HTMLHeadingElement>('main h1')?.focus()
  },[tab,result?.id])

  function restoreDraft(text:string){setGuideSession(value=>value+1);setInputText(text);try{setInputMode(isGuidedInput(normalizeGuidedInput(JSON.parse(text)))?'guided':'json')}catch{setInputMode('json')};selectTab('input');setSavedDraftAvailable(!!readSavedDraft())}
  function historyEdit(direction:'undo'|'redo'){
    const from=direction==='undo'?undoStack:redoStack,to=direction==='undo'?redoStack:undoStack
    const previous=from.current.pop();if(previous===undefined)return
    to.current=[...to.current,draft.current].slice(-20);draftRevision.current++;draft.current=previous;setInputTextState(previous)
  }

  useEffect(() => {
    try{localStorage.removeItem('genomedebugger-mysteries-v1')}catch{/* Storage may be unavailable. */}
    let live = true
    fetch(`${API}/investigations`).then(response => response.ok ? response.json() : []).then(items => { if (live) setRecent(previous=>{
      const seen=new Set<string>()
      return [...previous,...items].filter(item=>{
        if(seen.has(item.id))return false
        seen.add(item.id)
        if(item.archived){deletedRecent.current.add(item.id);return false}
        return !deletedRecent.current.has(item.id)
      }).slice(0,100)
    }) }).catch(() => {})
    return () => { live = false }
  }, [])

  useEffect(() => {
    let live = true
    let revision = 0
    let active:AbortController|null = null
    async function checkHealth() {
      const current=++revision
      active?.abort()
      const controller=new AbortController()
      active=controller
      const timeout=window.setTimeout(()=>controller.abort(),10000)
      try {
        const response = await fetch(`${API}/health`,{signal:controller.signal})
        if (!response.ok) throw new Error('Backend unavailable')
        const body = await response.json()
        if (live&&current===revision) {setEngineState('online');setEngineVersion(body.version);setHosted(body.hosted===true)}
      } catch {if(live&&current===revision)setEngineState('offline')}
      finally {window.clearTimeout(timeout);if(active===controller)active=null}
    }
    void checkHealth()
    const interval = window.setInterval(checkHealth,15000)
    return ()=>{live=false;revision++;active?.abort();window.clearInterval(interval)}
  },[])

  function selectTab(next:Tab) {
    // Navigation is a newer workspace intent. Older work may finish saving,
    // but cannot replace this screen or unmount its newer local drafts.
    if(next!==tab){selection.current++;pendingOpen.current=null;setBusy(false)}
    setTab(next);routeTo(next,result?.id);setError('');setNotice('')
  }

  function openGuided() {
    if (!inputText.trim()) setInputText(JSON.stringify(blankInput(),null,2))
    else if (!isGuidedInput(parsed)) {
      setError(`Repair the JSON before opening the guide: ${validateGuidedInput(parsed).join('; ')}`)
      return
    }
    setError('');setInputMode('guided')
  }

  async function openInvestigation(id: string, revision=++selection.current, draftVersion=draftRevision.current, target:Tab='overview') {
    if(revision!==selection.current)return
    pendingOpen.current=id
    setOperation('Opening a saved comparison');setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/investigations/${id}`)
      if (!response.ok) throw new Error(`Saved investigation unavailable (${response.status})`)
      const saved = await response.json() as Result
      if(revision!==selection.current)return
      if(draftVersion!==draftRevision.current){setNotice('Your input changed while the comparison was opening. Your draft was kept. Open the saved comparison again when ready.');return}
      comparedDraft.current=JSON.stringify(saved.input,null,2);setResult(saved); setInputText(JSON.stringify(saved.input,null,2));  setInputMode('json'); setTab(target);routeTo(target,saved.id); setSelectedEvidence(null)
    } catch (e) { if(revision===selection.current)setError(e instanceof Error ? e.message : 'Unable to open investigation') }
    finally { if(revision===selection.current){setBusy(false);pendingOpen.current=null} }
  }

  async function loadDemo(){await loadTeachingCase('transcript-switch')}
  async function loadExampleVariant(kind:'matching'|'uncertain'){await loadTeachingCase(kind)}
  async function loadTeachingCase(kind:string) {
    const revision=++selection.current;pendingOpen.current=null
    const draftVersion=draftRevision.current
    setOperation('Loading teaching inputs');setBusy(true); setError('');setNotice('')
    try {
      const response = await fetch(`${API}/demos/${kind}`)
      if (!response.ok) throw new Error(`Demo unavailable (${response.status})`)
      const body = await response.json() as InvestigationInput
      if(revision!==selection.current)return
      if(draftVersion!==draftRevision.current){setNotice('Your input changed while the example was loading. Your draft was kept; try the example again when ready.');return}
      const submittedText = JSON.stringify(body,null,2)
      setInputText(submittedText)
      setResult(null);  setInputMode('json'); setTab('input');routeTo('input',null)
      setOperation('Comparing teaching analyses')
      const comparison = await fetch(`${API}/investigations`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      if (!comparison.ok) throw new Error(`Demo comparison failed (${comparison.status})`)
      showResult(await comparison.json() as Result, submittedText, revision)
    }
    catch (e) { if(revision===selection.current)setError(e instanceof Error ? e.message : 'Unable to load demo') }
    finally { if(revision===selection.current)setBusy(false) }
  }
  function refreshRecentMetadata(id:string) {
    const revision=++recentMetadataRevision.current
    void fetch(`${API}/workspace/library/${encodeURIComponent(id)}/label`).then(async response=>response.ok?response.json():null).then(item=>{
      if(revision!==recentMetadataRevision.current||item?.id!==id||typeof item.title!=='string'||typeof item.archived!=='boolean')return
      if(item.archived){deletedRecent.current.add(id);setRecent(previous=>previous.filter(old=>old.id!==id))}
      else {deletedRecent.current.delete(id);setRecent(previous=>[item,...previous.filter(old=>old.id!==id)].slice(0,100))}
    }).catch(()=>{/* Preserve cached labels if the metadata request fails. */})
  }
  useEffect(()=>{
    const changed=(event:StorageEvent)=>{if(event.key===DRAFT_KEY||event.key===null)setSavedDraftAvailable(!!readSavedDraft())}
    window.addEventListener('storage',changed)
    return()=>{window.removeEventListener('storage',changed);recentMetadataRevision.current++}
  },[])
  function showResult(next: Result, submittedText?:string, revision?:number) {
    if(revision!==undefined && revision!==selection.current)return
    if(revision===undefined){selection.current++;pendingOpen.current=null;setBusy(false)}
    setResult(next); comparedDraft.current=submittedText??JSON.stringify(next.input,null,2); setTab('overview');routeTo('overview',next.id); setSelectedEvidence(null); setNotice('')
    setRecent(previous => deletedRecent.current.has(next.id)?previous:[{...previous.find(item=>item.id===next.id),id:next.id,title:next.input.title},...previous.filter(item=>item.id!==next.id)].slice(0,100))
    refreshRecentMetadata(next.id)
  }
  async function run() {
    const revision=++selection.current;pendingOpen.current=null
    setOperation('Comparing supplied analysis outputs');setBusy(true); setError('')
    try {
      if (!parsedState.valid) throw new Error('Input is not valid JSON.')
      if (!jsonObject) throw new Error('Enter a two-analysis JSON object before comparing.')
      const submittedText = inputText
      const response = await fetch(`${API}/investigations`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(parsed)})
      if (!response.ok) { const detail = await response.json(); throw new Error(response.status===422 ? `Schema validation failed: ${validationMessage(detail.detail)}` : detail.detail || `Comparison failed (${response.status})`) }
      showResult(await response.json() as Result, submittedText, revision)
    } catch (e) { if(revision===selection.current)setError(e instanceof Error ? e.message : 'Comparison failed') }
    finally { if(revision===selection.current)setBusy(false) }
  }
  async function exportMarkdown() {
    if (!result) return
    const request=++exportRequest.current, workspace=selection.current, draftVersion=draftRevision.current
    const current=()=>request===exportRequest.current&&workspace===selection.current&&draftVersion===draftRevision.current
    try { const response = await fetch(`${API}/investigations/${result.id}/report.md`); if (!response.ok) throw new Error('Report unavailable'); download(`genomedebugger-${result.id}.md`, await response.text(), 'text/markdown') }
    catch (e) { if(current())setError(e instanceof Error ? e.message : 'Report export failed') }
  }
  async function exportBundle() {
    if (!result) return
    const request=++exportRequest.current, workspace=selection.current, draftVersion=draftRevision.current
    const current=()=>request===exportRequest.current&&workspace===selection.current&&draftVersion===draftRevision.current
    try {
      const response = await fetch(`${API}/investigations/${result.id}/bundle`)
      if (!response.ok) throw new Error(`Bundle unavailable (${response.status})`)
      const content = await response.text()
      const bundle = JSON.parse(content)
      const exportedId = bundle.entries.investigation.id as string
      download(`genomedebugger-${exportedId}-bundle.json`, content, 'application/json')
      if (current()&&bundle.replayed_from_id) setNotice(`This older investigation was replayed with the current engine for portable export. The bundle contains record ${exportedId}; the original record remains saved as ${bundle.replayed_from_id}.`)
    } catch(e) {if(current())setError(e instanceof Error?e.message:'Bundle export failed')}
  }
  async function loadInputFile(file:File) {
    const revision=++selection.current;pendingOpen.current=null
    const draftVersion=draftRevision.current
    setOperation('Reading and checking the input file');setBusy(true);setError('');setNotice('')
    try {
      if (file.size > MAX_INPUT_BYTES) throw new Error('JSON input exceeds the 2 MB request limit')
      const content = await readUtf8(file)
      if(revision!==selection.current)return
      if(draftVersion!==draftRevision.current){setNotice('Your input changed while the file was loading. Your draft was kept; import the file again when ready.');return}
      JSON.parse(content)
      setInputText(content);setInputMode('json');setTab('input')
    } catch(e) {if(revision===selection.current)setError(e instanceof Error?e.message:'Unable to read JSON file')}
    finally {if(revision===selection.current)setBusy(false)}
  }
  async function importBundle(file:File) {
    const revision=++selection.current;pendingOpen.current=null
    const draftVersion=draftRevision.current
    setOperation('Reading the comparison bundle');setBusy(true);setError('');setNotice('')
    try {
      if (file.size > MAX_BUNDLE_BYTES) throw new Error('Bundle exceeds the 32 MB import limit')
      const content = await readUtf8(file)
      JSON.parse(content)
      // Forward the original JSON text: parsing and reserializing in JavaScript
      // would change large integers and values such as 1.0 before hash checks.
      const options = {method:'POST',headers:{'Content-Type':'application/json'},body:content}
      if(revision===selection.current)setOperation('Checking bundle hashes and reproducible results')
      const verified = await fetch(`${API}/bundles/verify`,options)
      if (!verified.ok) {const body=await verified.json();throw new Error(body.detail||'Bundle failed verification')}
      if(revision===selection.current)setOperation('Saving the verified bundle')
      const imported = await fetch(`${API}/bundles/import`,options)
      if (!imported.ok) {const body=await imported.json();throw new Error(body.detail||'Bundle import failed')}
      const body = await imported.json()
      if(revision===selection.current){
        if(draftVersion!==draftRevision.current)setNotice('Your input changed while the bundle was importing. Your draft was kept. The imported comparison is in Saved work.')
        else await openInvestigation(body.imported,revision,draftVersion)
      }
    } catch(e) {if(revision===selection.current)setError(e instanceof Error?e.message:'Bundle import failed')}
    finally {if(revision===selection.current)setBusy(false)}
  }
  async function copyLocalLink(){
    const url=window.location.href,workspace=selection.current
    try{if(!navigator.clipboard?.writeText)throw new Error('Clipboard unavailable');await navigator.clipboard.writeText(url);if(workspace===selection.current)setNotice(hosted?'Workspace link copied. It opens in this browser workspace; share a report or full bundle to transfer the data.':'Local comparison link copied. It only opens on this installation; use a report or bundle to share the data.')}
    catch{if(workspace===selection.current)setNotice(`Local link: ${url}. This does not transfer the underlying data.`)}
  }
  function newComparison(){
    selection.current++;pendingOpen.current=null;setBusy(false);setResult(null);setSelectedEvidence(null);setGuideSession(value=>value+1)
    setInputText(JSON.stringify(blankInput(),null,2));setInputMode('guided');setTab('input');routeTo('input',null);setError('');setNotice('A new comparison is ready for your inputs. Completed comparisons remain in Saved work.')
  }
  function inspectEvidence(id: string) { setSelectedEvidence(id); selectTab('evidence') }
  const a = result?.input.snapshots[0], b = result?.input.snapshots[1]
  const visibleSelection = selection.current
  const visibleDraft = draftRevision.current
  const sectionTitle:Record<Tab,string>={overview:result?'Your comparison':'Why did these results differ?',differences:'Review changed values',evidence:'Supporting details',regression:'Saved tests',input:'Review your inputs',source:'Look up a DNA change',library:'Saved work',help:'Your guide to comparisons',data:hosted?'Workspace data and settings':'Local data and settings'}
  function startInput(){selectTab('input');if(inputText.trim()&&!isGuidedInput(parsed))setInputMode('json');openGuided()}
  function chooseInputs(){selection.current++;pendingOpen.current=null;setBusy(false);setResult(null);setSelectedEvidence(null);setTab('overview');routeTo('overview',null);setError('');setNotice('')}
  const inComparison=!['source','library','help','data','input'].includes(tab)&&!!result
  return <div className="app-shell guided-workspace">
    <a className="skip-link" href="#main-content" tabIndex={0} onClick={e=>{e.preventDefault();document.getElementById('main-content')?.focus()}}>Skip to main content</a>
    <WorkspaceHeader tab={tab} resultId={result?.id} onNavigate={selectTab} onHome={chooseInputs}/>
    <main className="main" id="main-content" tabIndex={-1}>
      <div className={`content ${tab==='overview'&&!result?'start-content':''}`}><div className="workspace-status"><span>{inComparison?result?.input.title:'Understand analysis differences'}</span><span className="local-badge"><span className={`online-dot ${engineState}`}/> {engineState==='online'?(hosted?'Preview engine connected':'Local engine connected'):engineState==='offline'?(hosted?'Preview engine offline':'Local engine offline'):(hosted?'Checking preview engine':'Checking local engine')}</span></div><div className="page-intro"><div><span className="eyebrow accent">{tab==='overview'&&!result?'A clearer view of your analysis':'Your comparison workspace'}</span><h1 tabIndex={-1}>{sectionTitle[tab]}</h1><p>{tab==='source'?'Capture current public predictions, then choose two outputs to compare.':tab==='library'?'Reopen, organize, and download your comparisons.':tab==='help'?'Find your starting point and understand the terms.':tab==='data'?'Your storage, backups, and data choices.':tab==='input'?'Import the original outputs or enter their reported values. Check both analyses before comparing.':result?'Follow the differences, their supporting evidence, and the limits of the explanation.':'Bring two analysis outputs. Follow the evidence behind their differences.'}</p></div>{inComparison&&<div className="intro-actions"><button className="button secondary" onClick={newComparison}>New comparison</button><button className="text-button" onClick={copyLocalLink}>{hosted?'Copy workspace link':'Copy local link'}</button></div>}</div>
      {!['library','help','data'].includes(tab)&&<ComparisonSteps tab={tab} hasResult={!!result} onChoose={chooseInputs} onReview={startInput} onUnderstand={()=>selectTab('overview')}/>}
      {inComparison&&<nav className="comparison-sections" aria-label="This comparison"><div>{([{tab:'overview',name:'Summary'},{tab:'differences',name:`Changes ${result?.differences.length??0}`},{tab:'evidence',name:'Supporting details'}] as const).map(section=><button key={section.tab} aria-current={tab===section.tab?'page':undefined} onClick={()=>selectTab(section.tab)}>{section.name}</button>)}</div><details key={tab}><summary>Advanced tools</summary><div><button onClick={()=>selectTab('regression')}>Saved tests</button><button onClick={()=>{setInputMode('json');selectTab('input')}}>Input JSON</button><button onClick={run} disabled={busy||!jsonObject||guidedInvalid}>Run comparison</button></div></details></nav>}
      {error&&<div role="alert" className="error"><Info size={17}/><span>{error}</span><button className="text-button" onClick={()=>selectTab('help')}>Input and recovery help</button></div>}{notice&&<div role="status" className="input-notice">{notice}</div>}
      {hosted&&<aside className="hosted-notice" aria-label="Public preview storage"><div><strong>Public preview · temporary storage</strong><span>Inputs are processed on this server. Download bundles or reports to keep your work.</span></div><details><summary>About this workspace</summary><p>This browser has its own workspace. Free hosting can clear saved work when the server sleeps or restarts; inactive workspaces expire after 24 hours. A copied link does not transfer your records to another visitor.</p></details></aside>}
      <OperationStatus active={busy} label={operation}><button className="text-button" onClick={()=>{selection.current++;pendingOpen.current=null;setBusy(false);setNotice('Stopped waiting for the response. This does not cancel work already running on the server. Check Saved work before retrying.')}}>Stop waiting</button></OperationStatus>
      {result&&engineVersion&&(result.engine_version??'0.5.0')!==engineVersion&&<div className="input-notice">Historical result from engine {result.engine_version??'0.5.0'}. Run comparison to save a separate result with engine {engineVersion}.</div>}
      {!result&&tab==='overview'&&<><StartComparison busy={busy} onInput={startInput} onSource={()=>selectTab('source')} onExample={loadDemo}/>{savedDraftAvailable&&<div className="input-notice saved-draft-notice"><p>An explicitly saved browser draft is available.</p><button className="button secondary" onClick={()=>{const saved=readSavedDraft();if(saved)restoreDraft(saved.text)}}>Resume saved draft</button></div>}<p className="welcome-limit">Start with analysis outputs and their original metadata. This tool does not diagnose a condition or decide whether a DNA change is harmful. <button className="text-button" onClick={()=>selectTab('help')}>Where do my inputs come from?</button></p>{recent.length>0&&<section className="launcher-recent" aria-label="Recent comparisons"><h2>Pick up where you left off</h2>{recent.slice(0,4).map(item=><button key={item.id} className="recent-item" onClick={()=>openInvestigation(item.id)} disabled={busy}><span>{item.display_name||item.title}</span><code>{item.id}</code><small>{item.created_at?new Date(item.created_at).toLocaleDateString():'Saved comparison'}</small><ArrowRight size={16}/></button>)}</section>}</>}
      {result&&!['source','library','help','data'].includes(tab)&&inputChanged&&<div className="input-notice" role="status">Your input has changed. The displayed comparison uses the previous input; compare again to update it.</div>}
      {result&&tab==='overview'&&a&&b&&<>
        <ResultsSummary result={result} onChanges={()=>selectTab('differences')} onEvidence={inspectEvidence}/>
        <ClinicalAssertions result={result}/>
        <SourceProvenance result={result}/>
        <VariantReview key={result.id} result={result}/>
        {result.input.synthetic&&<ExampleGuide result={result} busy={busy} onMatching={()=>void loadExampleVariant('matching')} onUncertain={()=>void loadExampleVariant('uncertain')} onSwitch={()=>void loadDemo()}/>}
        <section className="panel findings-readable"><h2>What the evidence supports</h2>{result.findings.length?result.findings.map((f,i)=><article className="finding" key={i}><div className="finding-header">{pill(f.status)}<h3>{f.cause}</h3></div><p>{f.explanation}</p><div className="finding-footer"><span>{f.affected_fields.join(' · ')}</span>{f.evidence_ids[0]&&<button className="text-button" onClick={()=>inspectEvidence(f.evidence_ids[0])}>View test <ArrowRight size={13}/></button>}</div></article>):<p>No additional causal finding was established.</p>}<h3>Your next step</h3><p>{result.identity.status!=='verified'?'Review assembly, accession, coordinates, and available reference context before interpreting annotation differences.':result.differences.length?'Review the changed predictions and transcript/source settings. A difference alone does not prove its cause.':'Keep the tool and source metadata with this comparison. Matching outputs alone do not establish correctness.'}</p><div className="source-actions"><button className="button primary" onClick={()=>selectTab(result.differences.length?'differences':'input')}>{result.differences.length?'Review changed outputs':'Review the inputs'}</button><button className="button secondary" onClick={()=>setReportPreview(true)}>Preview readable report</button></div></section>
        <div className="section-title"><h2>Compared analyses</h2>{result.input.synthetic&&<span className="synthetic-label"><FlaskConical size={14}/> SYNTHETIC DATA</span>}</div><details className="technical-comparison"><summary>Show technical details</summary><div className="snapshot-grid"><SnapshotCard snapshot={a} side="A" referenceCheck={result.input.reference_check} annotationCheck={result.input.annotation_check}/><SnapshotCard snapshot={b} side="B" referenceCheck={result.input.reference_check} annotationCheck={result.input.annotation_check}/></div><section className="panel identity-card"><h2>Same allele?</h2>{identityPill(result.identity.status)}<p>{result.identity.explanation}</p><div className="edit-pair"><div><label>ANALYSIS A EDIT</label><code>{pretty(result.identity.normalized_a)}</code></div><div><label>ANALYSIS B EDIT</label><code>{pretty(result.identity.normalized_b)}</code></div></div><button className="text-button" onClick={()=>inspectEvidence(result.identity.evidence_ids[0])}>Inspect identity evidence</button></section></details>
        <div className="export-card"><div className="export-icon"><ClipboardList size={21}/></div><div><h3>Save or share this comparison</h3><p>Readable report for people; full bundle for reproducible transfer. Local links do not transfer records.</p><details className="export-fingerprint"><summary>Data fingerprint</summary><code className="record-hash">{result.input_sha256}</code></details></div><div className="export-actions"><button className="button secondary" onClick={()=>setReportPreview(true)}><FileText size={16}/> Readable report</button><details><summary>Other export formats</summary><div className="source-actions"><button className="button secondary" onClick={()=>download(`genomedebugger-${result.id}.json`,JSON.stringify(result,null,2),'application/json')}><FileJson size={16}/> Data (JSON)</button><button className="button secondary" onClick={exportMarkdown}>Text report</button></div></details><button className="button secondary" onClick={exportBundle}>Full bundle</button></div></div>
        {reportPreview&&<ReadableReport result={result} onClose={()=>setReportPreview(false)} onDownload={()=>download(`genomedebugger-${result.id}-report.html`,reportHtml(result),'text/html')}/>}
      </>}
      {result&&tab==='overview'&&!result.input.synthetic&&<details className="technical-comparison"><summary>Optional reference check (advanced)</summary><AlleleCheckPanel key={result.id} id={result.id} synthetic={result.input.synthetic}/></details>}
      {!result&&['differences','evidence','regression'].includes(tab)&&<section className="panel"><h2>Choose a comparison first</h2><p>Open saved work or choose inputs to see changes, supporting details, and tests.</p><div className="source-actions"><button className="button primary" onClick={()=>selectTab('library')}>Open saved work</button><button className="button secondary" onClick={()=>selectTab('overview')}>Choose inputs</button></div></section>}
      {result&&tab==='differences'&&<><ClinicalAssertions result={result} compact/><DifferenceTable differences={result.differences} onEvidence={inspectEvidence}/></>}
      {result&&tab==='evidence'&&<EvidenceInspector result={result} selected={selectedEvidence} onSelect={setSelectedEvidence}/>}
      {result&&tab==='regression'&&<RegressionPanel key={result.id} result={result} drafts={regressionDrafts.current}/>}
      {(tab==='source'||sourceVisited)&&<div hidden={tab!=='source'}><PublicSourcePanel active={tab==='source'} onCompare={next=>{if(visibleSelection!==selection.current||visibleDraft!==draftRevision.current)return;setInputText(JSON.stringify(next.input,null,2));showResult(next)}}/></div>}
      {tab==='library'&&<InvestigationLibrary drafts={libraryDrafts.current} onOpen={openInvestigation} onImport={file=>{void importBundle(file)}} onOrganized={item=>refreshRecentMetadata(item.id)} onDeleted={id=>{recentMetadataRevision.current++;deletedRecent.current.add(id);setRecent(previous=>previous.filter(item=>item.id!==id));if(pendingOpen.current===id){selection.current++;pendingOpen.current=null;setBusy(false)};setResult(previous=>previous?.id===id?null:previous)}}/>}
      {tab==='help'&&<HelpPanel hosted={hosted} onInput={startInput} onSource={()=>selectTab('source')}/>}
      {tab==='data'&&<LocalDataPanel hosted={hosted||engineState==='online'?hosted:undefined}/>}
      {tab==='input'&&<section className="panel input-panel"><div className="panel-heading"><div><span className="eyebrow">Original analysis outputs</span><h2>The two results to compare</h2><p>Import supported outputs, or copy values from the original analyses. Advanced JSON preserves all supported fields.</p></div></div>
        <ImportWorkspace onSources={()=>selectTab('source')} onUse={input=>{setGuideSession(value=>value+1);setInputText(JSON.stringify(input,null,2));setInputMode('guided')}}/>
        <DraftTools onSavedChange={setSavedDraftAvailable} text={inputText} onRestore={restoreDraft} onUndo={()=>historyEdit('undo')} onRedo={()=>historyEdit('redo')} canUndo={undoStack.current.length>0} canRedo={redoStack.current.length>0}/>
        <div className="input-toolbar"><button className={inputMode==='guided'?'selected':''} onClick={openGuided}>Guided form</button><button className={inputMode==='json'?'selected':''} onClick={()=>setInputMode('json')}>JSON editor</button><label className="button secondary">Import JSON<input aria-label="Import input JSON" type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files?.[0];if(file)void loadInputFile(file);e.target.value=''}}/></label></div>
        {inputMode==='guided'?<GuidedInput key={guideSession} value={parsed} onChange={next=>{setInputText(JSON.stringify(next,null,2))}} onRun={run} busy={busy}/>:<><label htmlFor="investigation-json" className="editor-label">Advanced two-analysis input (JSON)</label><textarea id="investigation-json" aria-label="Investigation JSON" spellCheck={false} value={inputText} onChange={e=>{setInputText(e.target.value)}} placeholder="Import a supported input document, or copy its documented structure…"/><div className="editor-foot"><span>{inputText?parsedState.valid?<><Check size={15}/> {jsonObject?'Valid JSON · schema checked on submit':'Valid JSON · enter a two-analysis object'}</>:'Invalid JSON':'No input loaded'}</span><a href="/api/demos/transcript-switch" target="_blank" rel="noreferrer">View example schema</a></div>{isGuidedInput(parsed)&&<details className="readiness-review"><summary>Review imported analysis metadata</summary>{parsed.snapshots.map(s=><p key={s.id}>{s.label}: {s.variant.assembly} {s.variant.sequence_id}:{s.variant.position} {s.variant.ref}→{s.variant.alt} · {s.provenance.tool} {s.provenance.tool_version} · {s.provenance.source_name} {s.provenance.source_release}</p>)}<p>Schema and linked-evidence checks still run on submission. Missing reference context can leave identity unresolved.</p></details>}<button className="button primary" onClick={run} disabled={!parsedState.valid||!jsonObject||busy}>Compare</button></>}
        <div className="source-actions input-example"><button className="text-button" onClick={loadDemo} disabled={busy}>Try example again</button><button className="text-button" onClick={()=>selectTab('help')}>Where do these values come from?</button></div>
      </section>}
      <WorkspaceFooter hosted={hosted} engineState={engineState} engineVersion={engineVersion} onData={()=>selectTab('data')}/></div>
    </main></div>
}
