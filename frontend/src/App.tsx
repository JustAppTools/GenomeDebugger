import { useEffect, useMemo, useRef, useState } from 'react'
import { Activity, ArrowRight, Braces, Check, ChevronDown, ClipboardCheck, ClipboardList, Database, Dna, FileJson, FileText, FlaskConical, GitCompareArrows, Globe2, Info, Layers3, LibraryBig, Search, ShieldCheck, SlidersHorizontal, Sparkles, Workflow } from 'lucide-react'
import type { Difference, Evidence, InvestigationInput, Result, Snapshot } from './types'
import RegressionPanel from './RegressionPanel'
import PublicSourcePanel from './PublicSourcePanel'
import GuidedInput, { blankInput, isGuidedInput, normalizeGuidedInput, validateGuidedInput } from './GuidedInput'
import InvestigationLibrary from './InvestigationLibrary'
import AlleleCheckPanel from './AlleleCheckPanel'
import MysteryLab from './MysteryLab'
import AnimatedReplay from './AnimatedReplay'
import './mystery.css'
import { MAX_BUNDLE_BYTES, MAX_INPUT_BYTES } from './limits'

type Tab = 'overview' | 'differences' | 'evidence' | 'regression' | 'input' | 'source' | 'library' | 'mysteries'
const API = '/api'

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click()
  URL.revokeObjectURL(url)
}

function pill(status: string) { return <span className={`pill pill-${status}`}>{status}</span> }
function identityPill(status: string) { return <span className={`pill pill-${status}`}>{status === 'verified' ? 'local context match' : status}</span> }
function pretty(value: unknown) { return value === null || value === undefined || value === '' ? '—' : String(value) }
function validationMessage(detail: unknown): string {
  if (!Array.isArray(detail)) return typeof detail === 'string' ? detail : 'The input does not match the required schema.'
  return detail.map(item => {
    const path = Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== 'body').join('.') : 'Input'
    return `${path || 'Input'}: ${item.msg || 'Invalid value'}`
  }).join('; ')
}

function SnapshotCard({ snapshot, side }: {snapshot: Snapshot; side: 'A'|'B'}) {
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
    {snapshot.provenance.configuration?.source_record_id&&<div className="snapshot-linkage">Source record <code>{snapshot.provenance.configuration.source_record_id}</code>{snapshot.provenance.configuration.reference_check_id&&<> · NCBI check <code>{snapshot.provenance.configuration.reference_check_id}</code></>}{snapshot.provenance.configuration.annotation_check_id&&<> · SnpEff check <code>{snapshot.provenance.configuration.annotation_check_id}</code></>}</div>}
  </article>
}

function DifferenceTable({ differences, onEvidence }: {differences: Difference[]; onEvidence: (id: string) => void}) {
  const [category, setCategory] = useState('all')
  const [query, setQuery] = useState('')
  const [meaningfulOnly, setMeaningfulOnly] = useState(true)
  const categories = ['all', ...new Set(differences.map(d => d.category))]
  const visible = differences.filter(d => (category === 'all' || d.category === category) && (!meaningfulOnly || d.meaningful) && d.field.toLowerCase().includes(query.toLowerCase()))
  return <section className="panel table-panel">
    <div className="panel-heading"><div><span className="eyebrow">STRUCTURED COMPARISON</span><h2>Field-level differences</h2><p>Observed changes from the two versioned snapshots.</p></div><span className="count-badge">{visible.length} shown</span></div>
    <div className="filters"><label className="search"><Search size={16}/><input aria-label="Search fields" placeholder="Search fields" value={query} onChange={e=>setQuery(e.target.value)}/></label><label className="select-wrap"><SlidersHorizontal size={16}/><select aria-label="Filter category" value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(c=><option key={c} value={c}>{c === 'all' ? 'All categories' : c.replace('_',' ')}</option>)}</select><ChevronDown size={14}/></label><label className="check"><input type="checkbox" checked={meaningfulOnly} onChange={e=>setMeaningfulOnly(e.target.checked)}/> Meaningful only</label></div>
    <div className="table-scroll"><table><thead><tr><th>FIELD</th><th>ANALYSIS A</th><th>ANALYSIS B</th><th>TYPE</th><th>EVIDENCE</th></tr></thead><tbody>{visible.map(d=><tr key={d.field}><td className="field-name">{d.field}</td><td className="mono">{pretty(d.before)}</td><td className="mono">{pretty(d.after)}</td><td><span className="type-tag">{d.category.replace('_',' ')}</span></td><td><button className="text-button" onClick={()=>onEvidence(d.evidence_ids[0])}>Inspect <ArrowRight size={13}/></button></td></tr>)}</tbody></table>{visible.length===0 && <div className="empty-row">No differences match these filters.</div>}</div>
  </section>
}

function EvidencePanel({ evidence, selected, onSelect }: {evidence: Evidence[]; selected: string | null; onSelect: (id: string) => void}) {
  const active = evidence.find(e=>e.id===selected) ?? evidence[0]
  return <section className="panel evidence-panel"><div className="panel-heading"><div><span className="eyebrow">AUDIT TRAIL</span><h2>Evidence inspector</h2><p>Every conclusion links back to an input comparison or replay.</p></div></div><div className="evidence-layout"><div className="evidence-list">{evidence.map(e=><button key={e.id} className={`evidence-item ${active?.id===e.id?'selected':''}`} onClick={()=>onSelect(e.id)}><span className="mono">{e.id}</span><small>{e.kind.replace('_',' ')}</small></button>)}</div><div className="evidence-detail">{active ? <><div className="detail-head"><span className="eyebrow">{active.kind.replace('_',' ')}</span><code>{active.id}</code></div><h3>{active.description}</h3><pre>{JSON.stringify(active.data,null,2)}</pre></> : <p>No evidence recorded.</p>}</div></div></section>
}

export default function App() {
  const [inputText, setInputTextState] = useState('')
  const draft = useRef('')
  const selection = useRef(0)
  const pendingOpen = useRef<string|null>(null)
  function setInputText(value:string) {draft.current=value;setInputTextState(value)}
  const [inputDirty, setInputDirty] = useState(false)
  const [inputMode,setInputMode] = useState<'guided'|'json'>('guided')
  const [engineState,setEngineState] = useState<'checking'|'online'|'offline'>('checking')
  const [engineVersion,setEngineVersion] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null)
  const [recent, setRecent] = useState<{id:string;title:string;created_at?:string|null}[]>([])
  const parsed = useMemo(() => { try { return normalizeGuidedInput(JSON.parse(inputText)) as InvestigationInput } catch { return null } }, [inputText])
  const guidedInvalid = inputMode === 'guided' && validateGuidedInput(parsed).length > 0
  const inputChanged = result !== null && inputDirty

  useEffect(() => {
    let live = true
    fetch(`${API}/investigations`).then(response => response.ok ? response.json() : []).then(items => { if (live) setRecent(items) }).catch(() => {})
    return () => { live = false }
  }, [])

  useEffect(() => {
    let live = true
    async function checkHealth() {
      try {
        const response = await fetch(`${API}/health`)
        if (!response.ok) throw new Error('Backend unavailable')
        const body = await response.json()
        if (live) {setEngineState('online');setEngineVersion(body.version)}
      } catch {if(live)setEngineState('offline')}
    }
    void checkHealth()
    const interval = window.setInterval(checkHealth,15000)
    return ()=>{live=false;window.clearInterval(interval)}
  },[])

  function selectTab(next:Tab) {setTab(next);setError('');setNotice('')}

  function openGuided() {
    if (!inputText.trim()) setInputText(JSON.stringify(blankInput(),null,2))
    else if (!isGuidedInput(parsed)) {
      setError(`Repair the JSON before opening the guide: ${validateGuidedInput(parsed).join('; ')}`)
      return
    }
    setError('');setInputMode('guided')
  }

  async function openInvestigation(id: string, revision=++selection.current) {
    if(revision!==selection.current)return
    pendingOpen.current=id
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/investigations/${id}`)
      if (!response.ok) throw new Error(`Saved investigation unavailable (${response.status})`)
      const saved = await response.json() as Result
      if(revision!==selection.current)return
      setResult(saved); setInputText(JSON.stringify(saved.input,null,2)); setInputDirty(false); setInputMode('json'); setTab('overview'); setSelectedEvidence(null)
    } catch (e) { if(revision===selection.current)setError(e instanceof Error ? e.message : 'Unable to open investigation') }
    finally { if(revision===selection.current){setBusy(false);pendingOpen.current=null} }
  }

  async function loadDemo() {
    const revision=++selection.current;pendingOpen.current=null
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/demos/transcript-switch`)
      if (!response.ok) throw new Error(`Demo unavailable (${response.status})`)
      const body = await response.json() as InvestigationInput
      if(revision!==selection.current)return
      const submittedText = JSON.stringify(body,null,2)
      setInputText(submittedText)
      setResult(null); setInputDirty(false); setInputMode('json'); setTab('input')
      const comparison = await fetch(`${API}/investigations`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      if (!comparison.ok) throw new Error(`Demo comparison failed (${comparison.status})`)
      showResult(await comparison.json() as Result, submittedText, revision)
    }
    catch (e) { if(revision===selection.current)setError(e instanceof Error ? e.message : 'Unable to load demo') }
    finally { if(revision===selection.current)setBusy(false) }
  }
  function showResult(next: Result, submittedText?:string, revision?:number) {
    if(revision!==undefined && revision!==selection.current)return
    if(revision===undefined){selection.current++;pendingOpen.current=null;setBusy(false)}
    setResult(next); setInputDirty(submittedText !== undefined && draft.current !== submittedText); setTab('overview'); setSelectedEvidence(null); setNotice('')
    setRecent(previous => [{id:next.id,title:next.input.title},...previous.filter(item=>item.id!==next.id)].slice(0,100))
  }
  async function run() {
    const revision=++selection.current;pendingOpen.current=null
    setBusy(true); setError('')
    try {
      if (!parsed) throw new Error('Input is not valid JSON.')
      const submittedText = inputText
      const response = await fetch(`${API}/investigations`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(parsed)})
      if (!response.ok) { const detail = await response.json(); throw new Error(response.status===422 ? `Schema validation failed: ${validationMessage(detail.detail)}` : detail.detail || `Comparison failed (${response.status})`) }
      showResult(await response.json() as Result, submittedText, revision)
    } catch (e) { if(revision===selection.current)setError(e instanceof Error ? e.message : 'Comparison failed') }
    finally { if(revision===selection.current)setBusy(false) }
  }
  async function exportMarkdown() {
    if (!result) return
    try { const response = await fetch(`${API}/investigations/${result.id}/report.md`); if (!response.ok) throw new Error('Report unavailable'); download(`genomedebugger-${result.id}.md`, await response.text(), 'text/markdown') }
    catch (e) { setError(e instanceof Error ? e.message : 'Report export failed') }
  }
  async function exportBundle() {
    if (!result) return
    try {
      const response = await fetch(`${API}/investigations/${result.id}/bundle`)
      if (!response.ok) throw new Error(`Bundle unavailable (${response.status})`)
      const bundle = await response.json()
      const exportedId = bundle.entries.investigation.id as string
      download(`genomedebugger-${exportedId}-bundle.json`, JSON.stringify(bundle), 'application/json')
      if (bundle.replayed_from_id) setNotice(`This older investigation was replayed with the current engine for portable export. The bundle contains record ${exportedId}; the original record remains saved as ${bundle.replayed_from_id}.`)
    } catch(e) {setError(e instanceof Error?e.message:'Bundle export failed')}
  }
  async function loadInputFile(file:File) {
    setError('')
    try {
      if (file.size > MAX_INPUT_BYTES) throw new Error('JSON input exceeds the 1 MB limit')
      const content = await file.text()
      JSON.parse(content)
      setInputText(content);setInputDirty(true);setInputMode('json');setTab('input')
    } catch(e) {setError(e instanceof Error?e.message:'Unable to read JSON file')}
  }
  async function importBundle(file:File) {
    const revision=++selection.current;pendingOpen.current=null
    setBusy(true);setError('')
    try {
      if (file.size > MAX_BUNDLE_BYTES) throw new Error('Bundle exceeds the 32 MB import limit')
      const content = JSON.parse(await file.text())
      const options = {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(content)}
      const verified = await fetch(`${API}/bundles/verify`,options)
      if (!verified.ok) {const body=await verified.json();throw new Error(body.detail||'Bundle failed verification')}
      const imported = await fetch(`${API}/bundles/import`,options)
      if (!imported.ok) {const body=await imported.json();throw new Error(body.detail||'Bundle import failed')}
      const body = await imported.json()
      if(revision===selection.current)await openInvestigation(body.imported,revision)
    } catch(e) {if(revision===selection.current)setError(e instanceof Error?e.message:'Bundle import failed')}
    finally {if(revision===selection.current)setBusy(false)}
  }
  async function openMystery(input:InvestigationInput) {
    const current=++selection.current;pendingOpen.current=null
    setBusy(true);setError('')
    const submitted=JSON.stringify(input,null,2)
    setInputText(submitted);setInputDirty(false);setInputMode('json')
    try {
      const response=await fetch(`${API}/investigations`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)})
      if(!response.ok)throw new Error(`Unable to save this case (${response.status})`)
      showResult(await response.json() as Result,submitted,current)
    }catch(e){if(current===selection.current)setError(e instanceof Error?e.message:'Unable to save this case')}
    finally{if(current===selection.current)setBusy(false)}
  }
  function inspectEvidence(id: string) { setSelectedEvidence(id); setTab('evidence') }
  const a = result?.input.snapshots[0], b = result?.input.snapshots[1]
  const visibleSelection = selection.current
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="brand-mark"><Dna size={23}/></div><div><strong>Genome<span>Debugger</span></strong><small>DISCREPANCY WORKSTATION</small></div></div>
      <div className="sidebar-section"><span className="sidebar-label">WORKSPACE</span><button className={`nav ${tab==='overview'?'active':''}`} onClick={()=>selectTab('overview')}><GitCompareArrows size={18}/> Investigation {tab==='overview'&&<span className="nav-dot"/>}</button><button className={`nav ${tab==='differences'?'active':''}`} onClick={()=>selectTab('differences')} disabled={!result}><Layers3 size={18}/> Discrepancies</button><button className={`nav ${tab==='evidence'?'active':''}`} onClick={()=>selectTab('evidence')} disabled={!result}><Workflow size={18}/> Evidence trail</button><button className={`nav ${tab==='regression'?'active':''}`} onClick={()=>selectTab('regression')} disabled={!result}><ClipboardCheck size={18}/> Regression test</button><button className={`nav ${tab==='input'?'active':''}`} onClick={()=>selectTab('input')}><Braces size={18}/> Snapshot input</button><button className={`nav ${tab==='source'?'active':''}`} onClick={()=>selectTab('source')}><Globe2 size={18}/> Public source</button><button className={`nav ${tab==='mysteries'?'active':''}`} onClick={()=>selectTab('mysteries')}><Search size={18}/> Mystery lab</button><button className={`nav ${tab==='library'?'active':''}`} onClick={()=>selectTab('library')}><LibraryBig size={18}/> Saved records</button></div>
      {recent.length>0&&<div className="recent-section"><span className="sidebar-label">RECENT INVESTIGATIONS</span>{recent.slice(0,5).map(item=><button key={item.id} className={`recent-item ${result?.id===item.id?'current':''}`} onClick={()=>openInvestigation(item.id)} disabled={busy}><span>{item.title}</span><code>{item.id}</code></button>)}</div>}
      <div className="sidebar-bottom"><div className="offline"><span className={`online-dot ${engineState}`}/> LOCAL ENGINE <span>{engineState==='online'?`v${engineVersion}`:engineState}</span></div><div className="sidebar-note"><ShieldCheck size={17}/><p>Local research tool. External requests only when you click Fetch or Check.</p></div></div>
    </aside>
    <main className="main"><header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> Investigations <span>/</span> <b>{tab==='mysteries'?'Mystery Lab':result ? result.id : 'New investigation'}</b></div><div className="top-actions"><span className="local-badge"><span className={`online-dot ${engineState}`}/> {engineState==='online'?'Local engine connected':engineState==='offline'?'Local engine offline':'Checking local engine'}</span></div></header>
      <div className="content"><div className="page-intro"><div><span className="eyebrow accent"><Activity size={15}/> GENOMIC REPRODUCIBILITY</span><h1>{tab==='source'?'Public source inspector':tab==='library'?'Saved investigations':tab==='mysteries'?'The Mystery Lab':'Investigation workspace'}</h1><p>{tab==='source'?'Query current public Ensembl data and preserve the response locally.':tab==='library'?'Find, reopen, and manage local records.':tab==='mysteries'?'Play detective. Follow the clues. Know when to leave a case open.':'Trace why two analyses disagree, inspect the evidence, and preserve a reproducible record.'}</p></div>{tab!=='source'&&tab!=='library'&&tab!=='mysteries'&&<div className="intro-actions"><button className="button secondary" onClick={loadDemo} disabled={busy}><FlaskConical size={17}/> Load synthetic demo</button><button className="button primary" onClick={run} disabled={busy || !parsed || guidedInvalid}><Sparkles size={17}/>{busy?'Working…':'Run comparison'}</button></div>}</div>
      {error && <div role="alert" className="error"><Info size={17}/><span>{error}</span></div>}{notice && <div role="status" className="input-notice">{notice}</div>}
      {result && engineVersion && (result.engine_version ?? '0.5.0') !== engineVersion && <div className="input-notice" role="status">Historical result from engine {result.engine_version ?? '0.5.0'}. Run comparison to save a separate result with engine {engineVersion}.</div>}
      {!result && tab !== 'input' && tab !== 'source' && tab !== 'library' && tab !== 'mysteries' && <div className="welcome"><div className="welcome-icon"><Dna size={34}/></div><span className="eyebrow">START HERE</span><h2>A discrepancy. A trail. Your next discovery.</h2><p>Try three bite-sized synthetic mysteries, or jump into the original transcript demo. Inspect the clues, test a hypothesis, and build a reproducible investigation.</p><div className="welcome-steps"><span><b>01</b> Compare snapshots</span><ArrowRight size={16}/><span><b>02</b> Inspect cause</span><ArrowRight size={16}/><span><b>03</b> Review evidence</span></div><div className="welcome-actions"><button className="button primary" onClick={()=>selectTab('mysteries')}><Search size={17}/> Explore the Mystery Lab</button><button className="button secondary" onClick={loadDemo} disabled={busy}><FlaskConical size={17}/> Load synthetic demo</button></div></div>}
      {result && tab!=='source' && tab!=='library' && tab!=='mysteries' && <><div className="summary-strip"><div><span>IDENTITY</span>{identityPill(result.identity.status)}</div><div><span>DIFFERENCES</span><strong>{result.differences.length}</strong></div><div><span>MEANINGFUL</span><strong>{result.differences.filter(d=>d.meaningful).length}</strong></div><div><span>ROOT CAUSE</span>{pill(result.findings[0]?.status ?? 'unresolved')}</div><div><span>RECORD</span><code>{result.id}</code></div></div>{inputChanged && <div className="input-notice" role="status">The snapshot JSON has changed. The displayed investigation still reflects the previous input; run comparison to update it.</div>}<nav className="tabs" aria-label="Investigation sections"><button className={tab==='overview'?'selected':''} onClick={()=>setTab('overview')}>Overview</button><button className={tab==='differences'?'selected':''} onClick={()=>setTab('differences')}>Differences <span>{result.differences.length}</span></button><button className={tab==='evidence'?'selected':''} onClick={()=>setTab('evidence')}>Evidence <span>{result.evidence.length}</span></button><button className={tab==='regression'?'selected':''} onClick={()=>setTab('regression')}>Regression</button><button className={tab==='input'?'selected':''} onClick={()=>setTab('input')}>Snapshot JSON</button></nav></>}
      {result && tab==='overview' && a && b && <><AnimatedReplay key={result.id} result={result} onEvidence={inspectEvidence}/><div className="section-title"><div><span className="eyebrow">SIDE BY SIDE</span><h2>Compared analyses</h2></div>{result.input.synthetic&&<span className="synthetic-label"><FlaskConical size={14}/> SYNTHETIC DATA</span>}</div><div className="snapshot-grid"><SnapshotCard snapshot={a} side="A"/><SnapshotCard snapshot={b} side="B"/></div><div className="two-col"><section className="panel identity-card"><div className="card-title"><div className="card-icon blue"><Dna size={19}/></div><div><span className="eyebrow">VARIANT IDENTITY</span><h2>Same allele?</h2></div>{identityPill(result.identity.status)}</div><p>{result.identity.explanation}</p><div className="edit-pair"><div><label>ANALYSIS A EDIT</label><code>{pretty(result.identity.normalized_a)}</code></div><div><label>ANALYSIS B EDIT</label><code>{pretty(result.identity.normalized_b)}</code></div></div><button className="text-button" onClick={()=>inspectEvidence(result.identity.evidence_ids[0])}>Inspect identity evidence <ArrowRight size={14}/></button></section><section className="panel finding-card"><div className="card-title"><div className="card-icon green"><Workflow size={19}/></div><div><span className="eyebrow">ROOT CAUSE WORKBENCH</span><h2>Investigation findings</h2></div></div>{result.findings.map((f,i)=><div className="finding" key={i}><div className="finding-header">{pill(f.status)}<strong>{f.cause}</strong></div><p>{f.explanation}</p><div className="finding-footer"><span>{f.affected_fields.join(' · ')}</span><button className="text-button" onClick={()=>inspectEvidence(f.evidence_ids[0])}>View test <ArrowRight size={13}/></button></div></div>)}</section></div><div className="export-card"><div className="export-icon"><ClipboardList size={21}/></div><div><h3>Reproducible investigation record</h3><p>Includes original inputs, field comparisons, findings, evidence, and SHA-256 input hash.</p><code className="record-hash">{result.input_sha256}</code></div><div className="export-actions"><button className="button secondary" onClick={()=>download(`genomedebugger-${result.id}.json`, JSON.stringify(result,null,2),'application/json')}><FileJson size={16}/> JSON</button><button className="button secondary" onClick={exportMarkdown}><FileText size={16}/> Markdown</button><button className="button secondary" onClick={exportBundle}><FileJson size={16}/> Bundle</button></div></div></>}
      {result && tab==='overview' && <AlleleCheckPanel key={result.id} id={result.id} synthetic={result.input.synthetic}/>}
      {result && tab==='differences' && <DifferenceTable differences={result.differences} onEvidence={inspectEvidence}/>}
      {result && tab==='evidence' && <EvidencePanel evidence={result.evidence} selected={selectedEvidence} onSelect={setSelectedEvidence}/>}
      {result && tab==='regression' && <RegressionPanel result={result}/>}
      {tab==='mysteries' && <MysteryLab onOpen={openMystery}/>}
      {tab==='source' && <PublicSourcePanel onCompare={next=>{if(visibleSelection!==selection.current)return;setInputText(JSON.stringify(next.input,null,2)); showResult(next)}}/>}
      {tab==='library' && <InvestigationLibrary onOpen={openInvestigation} onImport={file=>{void importBundle(file)}} onDeleted={id=>{setRecent(previous=>previous.filter(item=>item.id!==id));if(pendingOpen.current===id){selection.current++;pendingOpen.current=null;setBusy(false)};setResult(previous=>previous?.id===id?null:previous)}}/>}
      {tab==='input' && <section className="panel input-panel">
        <div className="panel-heading"><div><span className="eyebrow">VERSIONED INPUT</span><h2>Analysis snapshots</h2><p>Build two analyses with the guide, or edit the complete JSON schema. Data is sent only to the local backend when you compare.</p></div><div className="input-actions"><button className="button secondary" onClick={loadDemo} disabled={busy}><FlaskConical size={16}/> Run demo</button><button className="button primary" onClick={run} disabled={!parsed||busy||guidedInvalid}><GitCompareArrows size={16}/> Compare</button></div></div>
        <div className="input-toolbar"><button className={inputMode==='guided'?'selected':''} onClick={openGuided}>Guided form</button><button className={inputMode==='json'?'selected':''} onClick={()=>setInputMode('json')}>JSON editor</button><label className="button secondary">Import JSON<input aria-label="Import input JSON" type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files?.[0];if(file)void loadInputFile(file);e.target.value=''}}/></label></div>
        {inputMode==='guided' ? <GuidedInput value={parsed} onChange={next=>{setInputText(JSON.stringify(next,null,2));setInputDirty(true)}} onRun={run} busy={busy}/> : <><textarea aria-label="Investigation JSON" spellCheck={false} value={inputText} onChange={e=>{setInputText(e.target.value);setInputDirty(true)}} placeholder="Run the synthetic demo or paste an InvestigationInput JSON document…"/><div className="editor-foot"><span>{inputText ? parsed ? <><Check size={15}/> Valid JSON · schema checked on submit</> : 'Invalid JSON' : 'No input loaded'}</span><a href="/api/demos/transcript-switch" target="_blank" rel="noreferrer">View example schema <ArrowRight size={13}/></a></div></>}
      </section>}
      <footer><span><Dna size={15}/> GenomeDebugger · Research and bioinformatics QA</span><span>Not for clinical diagnosis</span></footer></div>
    </main></div>
}
