import { useEffect, useState } from 'react'
import { ArrowRight, CheckCircle2, ClipboardCheck, FlaskConical, History, Play, Save, XCircle } from 'lucide-react'
import type { RegressionCase, RegressionRun, RegressionRunSummary, Result } from './types'
import { isGuidedInput } from './GuidedInput'

const API = '/api'
function pretty(value: unknown): string { return value === undefined ? '—' : typeof value === 'string' ? value : JSON.stringify(value) }

export default function RegressionPanel({ result }: {result: Result}) {
  const [name, setName] = useState(`Regression: ${result.input.title}`)
  const [regressionCase, setRegressionCase] = useState<RegressionCase | null>(null)
  const [candidateText, setCandidateText] = useState(JSON.stringify(result.input, null, 2))
  const [advanced,setAdvanced] = useState(false)
  const [run, setRun] = useState<RegressionRun | null>(null)
  const [history, setHistory] = useState<RegressionRunSummary[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    async function findExisting() {
      try {
        const response = await fetch(`${API}/regression-cases`)
        if (!response.ok) throw new Error(`Regression cases unavailable (${response.status})`)
        const cases = await response.json() as {id:string;source_investigation_id:string}[]
        const match = cases.find(item => item.source_investigation_id === result.id)
        if (!match) return
        const detail = await fetch(`${API}/regression-cases/${match.id}`)
        if (!detail.ok) throw new Error(`Regression case unavailable (${detail.status})`)
        const item = await detail.json() as RegressionCase
        const runs = await fetch(`${API}/regression-cases/${match.id}/runs`)
        if (!runs.ok) throw new Error(`Regression history unavailable (${runs.status})`)
        if (live) {setRegressionCase(item); setHistory(await runs.json())}
      } catch (e) { if (live) setError(e instanceof Error ? e.message : 'Unable to load regression cases') }
    }
    void findExisting()
    return () => { live = false }
  }, [result.id])

  async function saveCase() {
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/investigations/${result.id}/regression-cases`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})})
      if (!response.ok) throw new Error(`Unable to save regression case (${response.status})`)
      setRegressionCase(await response.json())
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save regression case') }
    finally { setBusy(false) }
  }

  async function runCase(mode: 'pinned'|'candidate') {
    if (!regressionCase) return
    setBusy(true); setError('')
    try {
      const body = mode === 'pinned' ? {} : {candidate: JSON.parse(candidateText)}
      const response = await fetch(`${API}/regression-cases/${regressionCase.id}/runs`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      if (!response.ok) { const detail = await response.json(); throw new Error(typeof detail.detail === 'string' ? detail.detail : `Regression run failed (${response.status})`) }
      const item = await response.json() as RegressionRun
      setRun(item)
      setHistory(previous => [{id:item.id,created_at:item.created_at,mode:item.mode,status:item.status},...previous])
    } catch (e) { setError(e instanceof Error ? e.message : 'Regression run failed') }
    finally { setBusy(false) }
  }

  async function openRun(id: string) {
    setBusy(true); setError('')
    try { const response = await fetch(`${API}/regression-runs/${id}`); if (!response.ok) throw new Error('Saved run unavailable'); setRun(await response.json()) }
    catch (e) { setError(e instanceof Error ? e.message : 'Saved run unavailable') }
    finally { setBusy(false) }
  }

  function changeCandidate(index:number, group:'annotation'|'provenance', key:string, value:string) {
    try {
      const candidate = JSON.parse(candidateText)
      candidate.snapshots[index][group][key] = value
      setCandidateText(JSON.stringify(candidate,null,2));setError('')
    } catch {setError('Candidate JSON is invalid. Repair it in Advanced JSON mode.')}
  }
  let candidate: Result['input'] | null = null
  try {const parsed:unknown=JSON.parse(candidateText);candidate=isGuidedInput(parsed)?parsed:null} catch { /* handled when submitted */ }

  const criticalFailures = run?.checks.filter(check => check.required && !check.passed) ?? []
  const evidenceChanges = run?.checks.filter(check => check.path.startsWith('evidence.') && !check.passed) ?? []
  const checkCount = run?.checks.filter(check => check.required).length ?? 0
  const passCount = run?.checks.filter(check => check.required && check.passed).length ?? 0
  return <div className="regression-stack">
    <section className="panel regression-intro"><div className="panel-heading"><div><span className="eyebrow">SCIENTIFIC REGRESSION</span><h2>Preserve this discrepancy as a test</h2><p>Pin expected annotations, field differences, findings, and evidence from this investigation.</p></div><div className="regression-symbol"><ClipboardCheck size={25}/></div></div>
      {!regressionCase ? <div className="case-create"><label htmlFor="case-name">Test name</label><div><input id="case-name" value={name} onChange={e=>setName(e.target.value)} maxLength={200}/><button className="button primary" onClick={saveCase} disabled={busy||!name.trim()}><Save size={16}/> Save regression case</button></div><small>The saved baseline is immutable. It includes both snapshots and the controlled lookup.</small></div> : <div className="case-record"><div><span className="record-label">SAVED CASE</span><strong>{regressionCase.name}</strong><code>{regressionCase.id}</code></div><div><span className="record-label">BASELINE INPUT SHA-256</span><code>{regressionCase.source_investigation.input_sha256}</code></div></div>}
    </section>
    {error&&<div className="error" role="alert">{error}</div>}
    {regressionCase&&<><section className="panel regression-actions"><div className="panel-heading"><div><span className="eyebrow">REPLAY</span><h2>Run the assertion</h2><p>A pinned run checks the current comparison engine. A candidate run checks new analysis outputs for the same submitted allele descriptions.</p></div></div><div className="run-options"><div className="run-option"><div className="option-head"><div className="card-icon blue"><Play size={17}/></div><div><h3>Pinned replay</h3><p>Rerun the saved snapshots and require the same evidence data.</p></div></div><button className="button secondary" onClick={()=>runCase('pinned')} disabled={busy}><Play size={15}/> Run pinned baseline</button></div><div className="run-option"><div className="option-head"><div className="card-icon green"><FlaskConical size={17}/></div><div><h3>Candidate snapshots</h3><p>Edit key outputs below; evidence changes are shown separately.</p></div></div><button className="button primary" onClick={()=>runCase('candidate')} disabled={busy||!candidate}><ArrowRight size={15}/> Check candidate</button></div></div><div className="candidate-preview"><strong>Pinned expectations</strong><span>Identity: {result.identity.status}; {result.differences.length} differences; {result.findings.length} findings.</span></div>{candidate?.snapshots?.map((snapshot,index)=><div className="candidate-fields" key={index}><h3>Analysis {index===0?'A':'B'} · {snapshot.annotation.transcript_id}</h3><label className="guide-field">Consequence<input aria-label={`Candidate analysis ${index+1} consequence`} value={snapshot.annotation.consequence} onChange={e=>changeCandidate(index,'annotation','consequence',e.target.value)}/></label><label className="guide-field">Protein consequence<input aria-label={`Candidate analysis ${index+1} protein consequence`} value={snapshot.annotation.protein_consequence??''} onChange={e=>changeCandidate(index,'annotation','protein_consequence',e.target.value)}/></label><label className="guide-field">Tool version<input aria-label={`Candidate analysis ${index+1} tool version`} value={snapshot.provenance.tool_version} onChange={e=>changeCandidate(index,'provenance','tool_version',e.target.value)}/></label><label className="guide-field">Source release<input aria-label={`Candidate analysis ${index+1} source release`} value={snapshot.provenance.source_release} onChange={e=>changeCandidate(index,'provenance','source_release',e.target.value)}/></label></div>)}<button className="text-button" onClick={()=>setAdvanced(!advanced)}>{advanced?'Hide advanced JSON':'Advanced JSON'}</button>{advanced&&<><label className="candidate-label" htmlFor="candidate-json">CANDIDATE INPUT JSON</label><textarea id="candidate-json" aria-label="Candidate input JSON" spellCheck={false} value={candidateText} onChange={e=>setCandidateText(e.target.value)}/></>}<div className="editor-foot">Both candidate variants must exactly match the saved allele descriptions. Tool and source versions may change.</div></section>
      {run&&<section className="panel regression-result"><div className="result-header"><div className={`result-icon ${run.status}`}>{run.status==='passed'?<CheckCircle2 size={24}/>:<XCircle size={24}/>}</div><div><span className="eyebrow">{run.mode.toUpperCase()} RUN · {run.id}</span><h2>{run.status==='passed'?'Regression passed':'Regression failed'}</h2><p>{passCount} of {checkCount} required checks passed. {run.input_changes.length} input field{run.input_changes.length===1?'':'s'} changed; {evidenceChanges.length} evidence item{evidenceChanges.length===1?'':'s'} changed.</p></div></div>{criticalFailures.length>0&&<div className="check-section"><h3>Failed assertions</h3>{criticalFailures.map(check=><div className="check-row" key={check.path}><code>{check.path}</code><div><span>Expected: {pretty(check.expected)}</span><span>Actual: {pretty(check.actual)}</span></div></div>)}</div>}{evidenceChanges.length>0&&<div className="check-section"><h3>Changed evidence</h3><p>Evidence changes in candidate runs are reported even when expected outputs still pass.</p>{evidenceChanges.map(check=><div className="check-row" key={check.path}><code>{check.path}</code><div><span>Baseline hash: {pretty(check.expected)}</span><span>Current hash: {pretty(check.actual)}</span></div></div>)}</div>}{run.input_changes.length>0&&<div className="check-section"><h3>Input fields changed</h3><div className="input-change-list">{run.input_changes.map(path=><code key={path}>{path}</code>)}</div></div>}</section>}
      {history.length>0&&<section className="panel run-history"><div className="card-title"><div className="card-icon blue"><History size={18}/></div><div><span className="eyebrow">SAVED RESULTS</span><h2>Run history</h2></div></div><div className="history-list">{history.map(item=><button key={item.id} onClick={()=>openRun(item.id)} disabled={busy}><code>{item.id}</code><span>{item.mode}</span><span className={`pill pill-${item.status}`}>{item.status}</span><ArrowRight size={14}/></button>)}</div></section>}</>}
  </div>
}
