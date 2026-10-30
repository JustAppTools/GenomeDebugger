import { useEffect, useRef, useState } from 'react'
import { ArrowRight, CheckCircle2, ClipboardCheck, FlaskConical, History, Play, Save, XCircle } from 'lucide-react'
import type { RegressionCase, RegressionRun, RegressionRunSummary, Result, Snapshot } from './types'
import { isGuidedInput, normalizeGuidedInput } from './GuidedInput'
import {useRetainedState} from './retainedState'

const API = '/api'
function pretty(value: unknown): string { return value === undefined ? '—' : typeof value === 'string' ? value : JSON.stringify(value) }
function preservedVep(snapshot:Snapshot) {
  return Boolean(snapshot.provenance.configuration?.source_record_id)&&['Ensembl VEP REST','Ensembl VEP historical output'].includes(snapshot.provenance.tool)
}
interface CaseSummary {id:string;name?:string;source_investigation_id:string}

async function listBaselines(investigationId:string):Promise<CaseSummary[]> {
  const all=new Map<string,CaseSummary>()
  for(let offset=0;;offset+=100){
    const response=await fetch(`${API}/regression-cases?source_investigation_id=${encodeURIComponent(investigationId)}${offset?`&offset=${offset}`:''}`)
    if(!response.ok)throw new Error(`Regression cases unavailable (${response.status})`)
    const found=await response.json() as CaseSummary[]
    found.forEach(item=>all.set(item.id,item))
    if(found.length<100)return Array.from(all.values())
  }
}

export default function RegressionPanel({ result,drafts }: {result: Result;drafts?:Map<string,unknown>}) {
  const [name, setName] = useRetainedState(drafts,`${result.id}:name`,Array.from(`Regression: ${result.input.title}`).slice(0,200).join(''))
  const [regressionCase, setRegressionCase] = useState<RegressionCase | null>(null)
  const [baselines,setBaselines] = useState<CaseSummary[]>([])
  const caseRevision=useRef(0)
  const [candidateText, setCandidateText] = useRetainedState(drafts,`${result.id}:candidate`,JSON.stringify(result.input, null, 2))
  const [advanced,setAdvanced] = useRetainedState(drafts,`${result.id}:advanced`,false)
  const [run, setRun] = useState<RegressionRun | null>(null)
  const [runDraft, setRunDraft] = useState<string | null>(null)
  const [history, setHistory] = useState<RegressionRunSummary[]>([])
  const [hasOlder,setHasOlder] = useState(false)
  const [busy, setBusy] = useState(false)
  const [discovering, setDiscovering] = useState(true)
  const [error, setError] = useState('')
  const validName=name.trim().length>0 && Array.from(name).length<=200

  useEffect(() => {
    let live = true
    const revision=++caseRevision.current
    setDiscovering(true)
    async function findExisting() {
      try {
        const cases = await listBaselines(result.id)
        if(live&&revision===caseRevision.current)setBaselines(cases)
        const match = cases.find(item => item.source_investigation_id === result.id)
        if (!match) return
        const detail = await fetch(`${API}/regression-cases/${match.id}`)
        if (!detail.ok) throw new Error(`Regression case unavailable (${detail.status})`)
        const item = await detail.json() as RegressionCase
        const runs = await fetch(`${API}/regression-cases/${match.id}/runs`)
        if (!runs.ok) throw new Error(`Regression history unavailable (${runs.status})`)
        const found=await runs.json() as RegressionRunSummary[]
        if (live&&revision===caseRevision.current) {setRegressionCase(item); setHistory(found);setHasOlder(found.length===100)}
      } catch (e) { if (live) setError(e instanceof Error ? e.message : 'Unable to load regression cases') }
      finally {if(live)setDiscovering(false)}
    }
    void findExisting()
    return () => { live = false;caseRevision.current++ }
  }, [result.id])

  async function installBaseline(id:string,revision:number) {
    const [detail,runs]=await Promise.all([fetch(`${API}/regression-cases/${id}`),fetch(`${API}/regression-cases/${id}/runs`)])
    if(!detail.ok||!runs.ok)throw new Error('Saved baseline or its run history is unavailable')
    const item=await detail.json() as RegressionCase
    const found=await runs.json() as RegressionRunSummary[]
    if(item.source_investigation.id!==result.id)throw new Error('Saved baseline belongs to another investigation')
    if(revision===caseRevision.current){setRegressionCase(item);setHistory(found);setHasOlder(found.length===100);setRun(null);setRunDraft(null)}
  }

  async function chooseBaseline(id?:string) {
    const revision=++caseRevision.current
    setBusy(true);setError('')
    try {
      if(id)await installBaseline(id,revision)
      else {
        const cases=await listBaselines(result.id)
        if(revision!==caseRevision.current)return
        setBaselines(cases)
        const selected=cases.find(item=>item.id===regressionCase?.id)??cases[0]
        if(selected)await installBaseline(selected.id,revision)
      }
    } catch(e){if(revision===caseRevision.current)setError(e instanceof Error?e.message:'Unable to load saved baselines')}
    finally {if(revision===caseRevision.current)setBusy(false)}
  }

  async function saveCase() {
    if(!validName){setError('Test name must contain 1–200 characters.');return}
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/investigations/${result.id}/regression-cases`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})})
      if (!response.ok) {
        const body=await response.json().catch(()=>null)
        const detail=body?.detail
        const message=typeof detail==='string'?detail:Array.isArray(detail)?detail.map(item=>
          `${Array.isArray(item.loc)?item.loc.filter((part:unknown)=>part!=='body').join('.'):'Test name'}: ${item.msg??'Invalid value'}`).join('; '):''
        throw new Error(message||`Unable to save regression case (${response.status})`)
      }
      const item=await response.json() as RegressionCase
      setRegressionCase(item)
      setBaselines(previous=>[{id:item.id,name:item.name,source_investigation_id:item.source_investigation.id},...previous.filter(row=>row.id!==item.id)])
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save regression case') }
    finally { setBusy(false) }
  }

  async function runCase(mode: 'pinned'|'candidate') {
    if (!regressionCase) return
    const submittedText = candidateText
    setBusy(true); setError('')
    try {
      const body = mode === 'pinned' ? {} : {candidate: JSON.parse(candidateText)}
      const response = await fetch(`${API}/regression-cases/${regressionCase.id}/runs`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      if (!response.ok) { const detail = await response.json(); throw new Error(typeof detail.detail === 'string' ? detail.detail : `Regression run failed (${response.status})`) }
      const item = await response.json() as RegressionRun
      setRunDraft(mode === 'candidate' ? submittedText : null)
      setRun(item)
      setHistory(previous => [{id:item.id,created_at:item.created_at,mode:item.mode,status:item.status},...previous.filter(row=>row.id!==item.id)])
    } catch (e) { setError(e instanceof Error ? e.message : 'Regression run failed') }
    finally { setBusy(false) }
  }

  async function loadOlderRuns() {
    if(!regressionCase)return
    setBusy(true);setError('')
    try {
      const response=await fetch(`${API}/regression-cases/${regressionCase.id}/runs?before=${encodeURIComponent(history[history.length-1].id)}&limit=100`)
      if(!response.ok)throw new Error('Older regression history unavailable')
      const found=await response.json() as RegressionRunSummary[]
      setHistory(previous=>Array.from(new Map([...previous,...found].map(item=>[item.id,item])).values()));setHasOlder(found.length===100)
    }catch(e){setError(e instanceof Error?e.message:'Older regression history unavailable')}
    finally{setBusy(false)}
  }

  async function openRun(id: string) {
    setBusy(true); setError('')
    try { const response = await fetch(`${API}/regression-runs/${id}`); if (!response.ok) throw new Error('Saved run unavailable'); const item=await response.json() as RegressionRun;setRunDraft(null);setRun(item) }
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
  function useCustomOutput(index:number) {
    try {
      const next=normalizeGuidedInput(JSON.parse(candidateText))
      if(!isGuidedInput(next))throw new Error('Invalid candidate')
      const snapshot=next.snapshots[index]
      const configuration={...snapshot.provenance.configuration,
        input_tool:snapshot.provenance.tool,input_tool_version:snapshot.provenance.tool_version,
        candidate_output_origin:'user_declared_transformation'}
      delete (configuration as Record<string,string>).source_annotation_scope
      snapshot.provenance={...snapshot.provenance,tool:'Custom transformed output',tool_version:'not declared',configuration}
      // This check compared SnpEff with the original VEP output, not a custom
      // candidate. Allele-only reference evidence still applies to these variants.
      next.annotation_check=null
      for(const row of next.snapshots){
        const settings={...row.provenance.configuration}
        for(const key of ['annotation_check_id','annotation_check_status','annotation_check_origin'])delete settings[key]
        row.provenance.configuration=settings
      }
      setCandidateText(JSON.stringify(next,null,2));setError('')
    } catch {setError('Candidate JSON is invalid. Repair it in Advanced JSON mode.')}
  }
  let candidate: Result['input'] | null = null
  try {const parsed=normalizeGuidedInput(JSON.parse(candidateText));candidate=isGuidedInput(parsed)?parsed:null} catch { /* handled when submitted */ }

  const criticalFailures = run?.checks.filter(check => check.required && !check.passed) ?? []
  const evidenceChanges = run?.checks.filter(check => check.path.startsWith('evidence.') && !check.passed) ?? []
  const checkCount = run?.checks.filter(check => check.required).length ?? 0
  const passCount = run?.checks.filter(check => check.required && check.passed).length ?? 0
  const staleCandidate = run?.mode === 'candidate' && runDraft !== null && candidateText !== runDraft
  const savedCandidate = run?.mode === 'candidate' && runDraft === null
  return <div className="regression-stack">
    <section className="panel regression-intro"><div className="panel-heading"><div><span className="eyebrow">Saved expectations</span><h2>Save an expected result</h2><p>Keep this comparison as an expected result. Later, check whether a new analysis still matches it. Passing a saved test does not establish biological correctness.</p></div><div className="regression-symbol"><ClipboardCheck size={25}/></div></div>
      {discovering&&<p role="status">Loading saved tests…</p>}
      <div className="source-actions">{baselines.length>0&&<label className="guide-field baseline-picker">Saved baseline<select aria-label="Saved baseline" value={regressionCase?.id??''} disabled={busy||discovering} onChange={e=>void chooseBaseline(e.target.value)}>{baselines.map(item=><option key={item.id} value={item.id}>{item.name??item.id} · {item.id}</option>)}</select></label>}<button className="button secondary" disabled={busy||discovering} onClick={()=>void chooseBaseline()}>Refresh baselines</button></div>
      {!regressionCase ? <div className="case-create"><label htmlFor="case-name">Test name</label><div><input id="case-name" disabled={busy||discovering} value={name} onChange={e=>setName(e.target.value)} aria-describedby="case-name-help" aria-invalid={!validName}/><button className="button primary" onClick={saveCase} disabled={busy||discovering||!validName}><Save size={16}/> Save regression case</button></div><small id="case-name-help">{Array.from(name).length}/200 characters. The saved baseline is immutable. It includes both snapshots and the controlled lookup.</small></div> : <div className="case-record"><div><span className="record-label">SAVED CASE</span><strong>{regressionCase.name}</strong><code>{regressionCase.id}</code></div><div><span className="record-label">BASELINE INPUT SHA-256</span><code>{regressionCase.source_investigation.input_sha256}</code></div></div>}
    </section>
    {error&&<div className="error" role="alert">{error}</div>}
    {regressionCase&&<><section className="panel regression-actions"><div className="panel-heading"><div><span className="eyebrow">REPLAY</span><h2>Check a new analysis</h2><p>A pinned run checks the current comparison engine. A candidate run checks new analysis outputs for the same submitted allele descriptions.</p></div></div><div className="run-options"><div className="run-option"><div className="option-head"><div className="card-icon blue"><Play size={17}/></div><div><h3>Recheck the saved result</h3><p>Rerun the saved snapshots and require the same evidence data.</p></div></div><button className="button secondary" onClick={()=>runCase('pinned')} disabled={busy}><Play size={15}/> Run pinned baseline</button></div><div className="run-option"><div className="option-head"><div className="card-icon green"><FlaskConical size={17}/></div><div><h3>Try new analysis outputs</h3><p>Edit key outputs below; evidence changes are shown separately.</p></div></div><button className="button primary" onClick={()=>runCase('candidate')} disabled={busy||!candidate}><ArrowRight size={15}/> Check candidate</button></div></div><div className="candidate-preview"><strong>Pinned expectations</strong><span>Identity: {result.identity.status}; {result.differences.length} differences; {result.findings.length} findings.</span></div>{candidate?.snapshots?.map((snapshot,index)=>{
        const preserved=preservedVep(snapshot)
        return <div className="candidate-fields" key={index}>
          <h3>Analysis {index===0?'A':'B'} · {snapshot.annotation.transcript_id}</h3>
          {preserved&&<div className="candidate-origin"><p>These values come from preserved VEP output. To test edits, first declare your own transformed output.</p><button className="button secondary" disabled={busy} onClick={()=>useCustomOutput(index)}>Use custom output for analysis {index===0?'A':'B'}</button></div>}
          {snapshot.provenance.configuration?.candidate_output_origin==='user_declared_transformation'&&<p className="candidate-origin source-caveat">Your custom output cites the saved source as an input. The SnpEff check against the original output is detached; allele reference checks are retained.</p>}
          <label className="guide-field">Consequence<input aria-label={`Candidate analysis ${index+1} consequence`} disabled={preserved} value={snapshot.annotation.consequence} onChange={e=>changeCandidate(index,'annotation','consequence',e.target.value)}/></label>
          <label className="guide-field">Protein consequence<input aria-label={`Candidate analysis ${index+1} protein consequence`} disabled={preserved} value={snapshot.annotation.protein_consequence??''} onChange={e=>changeCandidate(index,'annotation','protein_consequence',e.target.value)}/></label>
          <label className="guide-field">Tool name<input aria-label={`Candidate analysis ${index+1} tool name`} disabled={preserved} value={snapshot.provenance.tool} onChange={e=>changeCandidate(index,'provenance','tool',e.target.value)}/></label>
          <label className="guide-field">Tool version<input aria-label={`Candidate analysis ${index+1} tool version`} disabled={preserved} value={snapshot.provenance.tool_version} onChange={e=>changeCandidate(index,'provenance','tool_version',e.target.value)}/></label>
          <label className="guide-field">Source release<input aria-label={`Candidate analysis ${index+1} source release`} disabled={preserved} value={snapshot.provenance.source_release} onChange={e=>changeCandidate(index,'provenance','source_release',e.target.value)}/></label>
        </div>
      })}<button className="text-button" onClick={()=>setAdvanced(!advanced)}>{advanced?'Hide advanced JSON':'Advanced JSON'}</button>{advanced&&<><label className="candidate-label" htmlFor="candidate-json">CANDIDATE INPUT JSON</label><textarea id="candidate-json" aria-label="Candidate input JSON" spellCheck={false} value={candidateText} onChange={e=>setCandidateText(e.target.value)}/></>}<div className="editor-foot">Both candidate variants must exactly match the saved allele descriptions. Tool and source versions may change.</div></section>
      {run&&<section className="panel regression-result"><div className="result-header"><div className={`result-icon ${run.status}`}>{run.status==='passed'?<CheckCircle2 size={24}/>:<XCircle size={24}/>}</div><div><span className="eyebrow">{run.mode.toUpperCase()} RUN · {run.id}</span><h2>{staleCandidate?`Previous candidate ${run.status}`:savedCandidate?`Saved candidate ${run.status}`:run.status==='passed'?'Regression passed':'Regression failed'}</h2><p>{passCount} of {checkCount} required checks passed. {run.input_changes.length} input field{run.input_changes.length===1?'':'s'} changed; {evidenceChanges.length} evidence item{evidenceChanges.length===1?'':'s'} changed.</p></div></div>{staleCandidate&&<div className="input-notice" role="status">Candidate input has changed. This saved result uses an earlier input; check the candidate again to test your edits.</div>}{savedCandidate&&<div className="input-notice" role="status">You are viewing a saved candidate run. Check the candidate to test the input currently in the editor.</div>}{criticalFailures.length>0&&<div className="check-section"><h3>Failed assertions</h3>{criticalFailures.map(check=><div className="check-row" key={check.path}><code>{check.path}</code><div><span>Expected: {pretty(check.expected)}</span><span>Actual: {pretty(check.actual)}</span></div></div>)}</div>}{evidenceChanges.length>0&&<div className="check-section"><h3>Changed evidence</h3><p>Evidence changes in candidate runs are reported even when expected outputs still pass.</p>{evidenceChanges.map(check=><div className="check-row" key={check.path}><code>{check.path}</code><div><span>Baseline hash: {pretty(check.expected)}</span><span>Current hash: {pretty(check.actual)}</span></div></div>)}</div>}{run.input_changes.length>0&&<div className="check-section"><h3>Input fields changed</h3><div className="input-change-list">{run.input_changes.map(path=><code key={path}>{path}</code>)}</div></div>}</section>}
      {history.length>0&&<section className="panel run-history"><div className="card-title"><div className="card-icon blue"><History size={18}/></div><div><span className="eyebrow">SAVED RESULTS</span><h2>Run history</h2></div></div><div className="history-list">{history.map(item=><button key={item.id} onClick={()=>openRun(item.id)} disabled={busy}><code>{item.id}</code><span>{item.mode}</span><span className={`pill pill-${item.status}`}>{item.status}</span><ArrowRight size={14}/></button>)}</div>{hasOlder&&<button className="button secondary" disabled={busy} onClick={loadOlderRuns}>Load older runs</button>}</section>}</>}
  </div>
}
