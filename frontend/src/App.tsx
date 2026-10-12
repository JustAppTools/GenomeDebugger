import { useEffect, useMemo, useState } from 'react'
import { Activity, ArrowRight, Braces, Check, ChevronDown, ClipboardCheck, ClipboardList, Database, Dna, FileJson, FileText, FlaskConical, GitCompareArrows, Info, Layers3, Search, ShieldCheck, SlidersHorizontal, Sparkles, Workflow } from 'lucide-react'
import type { Difference, Evidence, InvestigationInput, Result, Snapshot } from './types'
import RegressionPanel from './RegressionPanel'

type Tab = 'overview' | 'differences' | 'evidence' | 'regression' | 'input'
const API = '/api'

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click()
  URL.revokeObjectURL(url)
}

function pill(status: string) { return <span className={`pill pill-${status}`}>{status}</span> }
function pretty(value: unknown) { return value === null || value === undefined || value === '' ? '—' : String(value) }

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
  const [inputText, setInputText] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null)
  const [recent, setRecent] = useState<{id:string;title:string}[]>([])
  const parsed = useMemo(() => { try { return JSON.parse(inputText) as InvestigationInput } catch { return null } }, [inputText])

  useEffect(() => {
    let live = true
    fetch(`${API}/investigations`).then(response => response.ok ? response.json() : []).then(items => { if (live) setRecent(items) }).catch(() => {})
    return () => { live = false }
  }, [])

  async function openInvestigation(id: string) {
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/investigations/${id}`)
      if (!response.ok) throw new Error(`Saved investigation unavailable (${response.status})`)
      const saved = await response.json() as Result
      setResult(saved); setInputText(JSON.stringify(saved.input,null,2)); setTab('overview'); setSelectedEvidence(null)
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to open investigation') }
    finally { setBusy(false) }
  }

  async function loadDemo() {
    setBusy(true); setError('')
    try { const response = await fetch(`${API}/demos/transcript-switch`); if (!response.ok) throw new Error(`Demo unavailable (${response.status})`); const body = await response.json(); setInputText(JSON.stringify(body,null,2)); setResult(null); setTab('input') }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load demo') }
    finally { setBusy(false) }
  }
  async function run() {
    setBusy(true); setError('')
    try {
      if (!parsed) throw new Error('Input is not valid JSON.')
      const response = await fetch(`${API}/investigations`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(parsed)})
      if (!response.ok) { const detail = await response.json(); throw new Error(response.status===422 ? `Schema validation failed: ${JSON.stringify(detail.detail)}` : detail.detail || `Comparison failed (${response.status})`) }
      const next = await response.json() as Result
      setResult(next); setTab('overview'); setSelectedEvidence(null)
      setRecent(previous => [{id:next.id,title:next.input.title},...previous.filter(item=>item.id!==next.id)].slice(0,100))
    } catch (e) { setError(e instanceof Error ? e.message : 'Comparison failed') }
    finally { setBusy(false) }
  }
  async function exportMarkdown() {
    if (!result) return
    try { const response = await fetch(`${API}/investigations/${result.id}/report.md`); if (!response.ok) throw new Error('Report unavailable'); download(`genomedebugger-${result.id}.md`, await response.text(), 'text/markdown') }
    catch (e) { setError(e instanceof Error ? e.message : 'Report export failed') }
  }
  function inspectEvidence(id: string) { setSelectedEvidence(id); setTab('evidence') }
  const a = result?.input.snapshots[0], b = result?.input.snapshots[1]
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="brand-mark"><Dna size={23}/></div><div><strong>Genome<span>Debugger</span></strong><small>DISCREPANCY WORKSTATION</small></div></div>
      <div className="sidebar-section"><span className="sidebar-label">WORKSPACE</span><button className={`nav ${tab==='overview'?'active':''}`} onClick={()=>setTab('overview')}><GitCompareArrows size={18}/> Investigation {tab==='overview'&&<span className="nav-dot"/>}</button><button className={`nav ${tab==='differences'?'active':''}`} onClick={()=>setTab('differences')} disabled={!result}><Layers3 size={18}/> Discrepancies</button><button className={`nav ${tab==='evidence'?'active':''}`} onClick={()=>setTab('evidence')} disabled={!result}><Workflow size={18}/> Evidence trail</button><button className={`nav ${tab==='regression'?'active':''}`} onClick={()=>setTab('regression')} disabled={!result}><ClipboardCheck size={18}/> Regression test</button><button className={`nav ${tab==='input'?'active':''}`} onClick={()=>setTab('input')}><Braces size={18}/> Snapshot input</button></div>
      {recent.length>0&&<div className="recent-section"><span className="sidebar-label">RECENT INVESTIGATIONS</span>{recent.slice(0,5).map(item=><button key={item.id} className={`recent-item ${result?.id===item.id?'current':''}`} onClick={()=>openInvestigation(item.id)} disabled={busy}><span>{item.title}</span><code>{item.id}</code></button>)}</div>}
      <div className="sidebar-bottom"><div className="offline"><span className="online-dot"/> OFFLINE ENGINE <span>v0.2.0</span></div><div className="sidebar-note"><ShieldCheck size={17}/><p>Local research tool. Synthetic demo data. No external upload.</p></div></div>
    </aside>
    <main className="main"><header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> Investigations <span>/</span> <b>{result ? result.id : 'New investigation'}</b></div><div className="top-actions"><span className="local-badge"><span className="online-dot"/> Local session</span></div></header>
      <div className="content"><div className="page-intro"><div><span className="eyebrow accent"><Activity size={15}/> GENOMIC REPRODUCIBILITY</span><h1>Investigation workspace</h1><p>Trace why two analyses disagree, inspect the evidence, and preserve a reproducible record.</p></div><div className="intro-actions"><button className="button secondary" onClick={loadDemo} disabled={busy}><FlaskConical size={17}/> Load synthetic demo</button><button className="button primary" onClick={run} disabled={busy || !parsed}><Sparkles size={17}/>{busy?'Working…':'Run comparison'}</button></div></div>
      {error && <div role="alert" className="error"><Info size={17}/><span>{error}</span></div>}
      {!result && tab !== 'input' && <div className="welcome"><div className="welcome-icon"><Dna size={34}/></div><span className="eyebrow">START HERE</span><h2>Debug an analysis discrepancy</h2><p>Load the synthetic transcript switch example, inspect the two structured snapshots, then run the comparison to see a controlled explanation.</p><div className="welcome-steps"><span><b>01</b> Load snapshots</span><ArrowRight size={16}/><span><b>02</b> Compare fields</span><ArrowRight size={16}/><span><b>03</b> Inspect cause</span></div><button className="button primary" onClick={loadDemo}><FlaskConical size={17}/> Load synthetic demo</button></div>}
      {result && <><div className="summary-strip"><div><span>IDENTITY</span>{pill(result.identity.status)}</div><div><span>DIFFERENCES</span><strong>{result.differences.length}</strong></div><div><span>MEANINGFUL</span><strong>{result.differences.filter(d=>d.meaningful).length}</strong></div><div><span>ROOT CAUSE</span>{pill(result.findings[0]?.status ?? 'unresolved')}</div><div><span>RECORD</span><code>{result.id}</code></div></div><nav className="tabs" aria-label="Investigation sections"><button className={tab==='overview'?'selected':''} onClick={()=>setTab('overview')}>Overview</button><button className={tab==='differences'?'selected':''} onClick={()=>setTab('differences')}>Differences <span>{result.differences.length}</span></button><button className={tab==='evidence'?'selected':''} onClick={()=>setTab('evidence')}>Evidence <span>{result.evidence.length}</span></button><button className={tab==='regression'?'selected':''} onClick={()=>setTab('regression')}>Regression</button><button className={tab==='input'?'selected':''} onClick={()=>setTab('input')}>Snapshot JSON</button></nav></>}
      {result && tab==='overview' && a && b && <><div className="section-title"><div><span className="eyebrow">SIDE BY SIDE</span><h2>Compared analyses</h2></div>{result.input.synthetic&&<span className="synthetic-label"><FlaskConical size={14}/> SYNTHETIC DATA</span>}</div><div className="snapshot-grid"><SnapshotCard snapshot={a} side="A"/><SnapshotCard snapshot={b} side="B"/></div><div className="two-col"><section className="panel identity-card"><div className="card-title"><div className="card-icon blue"><Dna size={19}/></div><div><span className="eyebrow">VARIANT IDENTITY</span><h2>Same allele?</h2></div>{pill(result.identity.status)}</div><p>{result.identity.explanation}</p><div className="edit-pair"><div><label>ANALYSIS A EDIT</label><code>{pretty(result.identity.normalized_a)}</code></div><div><label>ANALYSIS B EDIT</label><code>{pretty(result.identity.normalized_b)}</code></div></div><button className="text-button" onClick={()=>inspectEvidence(result.identity.evidence_ids[0])}>Inspect identity evidence <ArrowRight size={14}/></button></section><section className="panel finding-card"><div className="card-title"><div className="card-icon green"><Workflow size={19}/></div><div><span className="eyebrow">ROOT CAUSE WORKBENCH</span><h2>Investigation findings</h2></div></div>{result.findings.map((f,i)=><div className="finding" key={i}><div className="finding-header">{pill(f.status)}<strong>{f.cause}</strong></div><p>{f.explanation}</p><div className="finding-footer"><span>{f.affected_fields.join(' · ')}</span><button className="text-button" onClick={()=>inspectEvidence(f.evidence_ids[0])}>View test <ArrowRight size={13}/></button></div></div>)}</section></div><div className="export-card"><div className="export-icon"><ClipboardList size={21}/></div><div><h3>Reproducible investigation record</h3><p>Includes original inputs, field comparisons, findings, evidence, and SHA-256 input hash.</p></div><div className="export-actions"><button className="button secondary" onClick={()=>download(`genomedebugger-${result.id}.json`, JSON.stringify(result,null,2),'application/json')}><FileJson size={16}/> JSON</button><button className="button secondary" onClick={exportMarkdown}><FileText size={16}/> Markdown</button></div></div></>}
      {result && tab==='differences' && <DifferenceTable differences={result.differences} onEvidence={inspectEvidence}/>}
      {result && tab==='evidence' && <EvidencePanel evidence={result.evidence} selected={selectedEvidence} onSelect={setSelectedEvidence}/>}
      {result && tab==='regression' && <RegressionPanel result={result}/>}
      {tab==='input' && <section className="panel input-panel"><div className="panel-heading"><div><span className="eyebrow">VERSIONED INPUT</span><h2>Analysis snapshots</h2><p>Paste two snapshots in the documented JSON schema. Local input is sent only to the local backend.</p></div><div className="input-actions"><button className="button secondary" onClick={loadDemo}><FlaskConical size={16}/> Demo</button><button className="button primary" onClick={run} disabled={!parsed||busy}><GitCompareArrows size={16}/> Compare</button></div></div><textarea aria-label="Investigation JSON" spellCheck={false} value={inputText} onChange={e=>setInputText(e.target.value)} placeholder="Load the synthetic demo or paste an InvestigationInput JSON document…"/><div className="editor-foot"><span>{inputText ? parsed ? <><Check size={15}/> Valid JSON · schema checked on submit</> : 'Invalid JSON' : 'No input loaded'}</span><a href="/api/demos/transcript-switch" target="_blank" rel="noreferrer">View example schema <ArrowRight size={13}/></a></div></section>}
      <footer><span><Dna size={15}/> GenomeDebugger · Research and bioinformatics QA</span><span>Not for clinical diagnosis</span></footer></div>
    </main></div>
}
