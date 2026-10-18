import {useEffect,useRef,useState} from 'react'
import {ArrowLeft, ArrowRight, CheckCircle2, Fingerprint, FlaskConical, FolderOpen, Search, Sparkles} from 'lucide-react'
import type {InvestigationInput,Result} from './types'
import AnimatedReplay from './AnimatedReplay'

interface Mission {id:string;number:string;title:string;theme:string;skill:string;brief:string;question:string;clues:string[];hypotheses:{id:string;label:string}[]}
interface Assessment {hypothesis_id:string;matches_evidence:boolean;conclusion:string;explanation:string;evidence_ids:string[]}
const PROGRESS='genomedebugger-mysteries-v1'
function progress():string[]{try{const saved=JSON.parse(localStorage.getItem(PROGRESS)||'[]');return Array.isArray(saved)?saved.filter((id:unknown)=>typeof id==='string'):[]}catch{return []}}

export default function MysteryLab({onOpen}:{onOpen:(input:InvestigationInput)=>Promise<void>}) {
  const [missions,setMissions]=useState<Mission[]>([])
  const [selected,setSelected]=useState<{mission:Mission;result:Result}|null>(null)
  const [completed,setCompleted]=useState<string[]>(progress)
  const [choice,setChoice]=useState('')
  const [assessment,setAssessment]=useState<Assessment|null>(null)
  const [evidenceId,setEvidenceId]=useState<string|null>(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const revision=useRef(0)
  useEffect(()=>{
    let live=true
    fetch('/api/mysteries').then(async response=>{if(!response.ok)throw new Error(`Mysteries unavailable (${response.status})`);return response.json()}).then(items=>{if(live)setMissions(items)}).catch(e=>{if(live)setError(e instanceof Error?e.message:'Unable to load mysteries')})
    return ()=>{live=false;revision.current++}
  },[])
  async function open(id:string){
    const current=++revision.current
    setBusy(true);setError('');setAssessment(null);setChoice('');setEvidenceId(null);setSelected(null)
    try{const response=await fetch(`/api/mysteries/${id}`);if(!response.ok)throw new Error(`Case unavailable (${response.status})`);const body=await response.json();if(current===revision.current)setSelected(body)}
    catch(e){if(current===revision.current)setError(e instanceof Error?e.message:'Unable to open case')}
    finally{if(current===revision.current)setBusy(false)}
  }
  async function check(){
    if(!selected||!choice)return
    const current=++revision.current
    const submitted=choice
    setBusy(true);setError('')
    try{
      const response=await fetch(`/api/mysteries/${selected.mission.id}/check`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hypothesis_id:submitted})})
      const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:`Hypothesis check failed (${response.status})`)
      if(current!==revision.current)return
      setAssessment(body.assessment);setSelected({...selected,result:body.result})
      if(body.assessment.matches_evidence){const next=[...new Set([...completed,selected.mission.id])];setCompleted(next);try{localStorage.setItem(PROGRESS,JSON.stringify(next))}catch{/* The current visit still keeps progress. */}}
    }catch(e){if(current===revision.current)setError(e instanceof Error?e.message:'Unable to check hypothesis')}
    finally{if(current===revision.current)setBusy(false)}
  }
  const evidence=selected?.result.evidence.find(item=>item.id===evidenceId)
  const solved=missions.filter(item=>completed.includes(item.id)).length
  return <div className="mystery-lab">
    <section className="mystery-hero"><div><span className="eyebrow"><Fingerprint size={16}/> THE MYSTERY LAB</span><h2>Every discrepancy leaves a trail.</h2><p>Three small cases. A few tempting suspects. Follow the evidence and decide how much you can actually conclude.</p><div className="mystery-hero-foot"><span><FlaskConical size={14}/> Synthetic training cases · works offline with the local engine</span><b>{solved} / {missions.length||3} evidence trails completed</b></div></div><div className="mystery-emblem" aria-hidden="true"><Fingerprint size={94}/><span>RESEARCH<br/>CASE FILES</span></div></section>
    {error&&<div className="error" role="alert">{error}</div>}
    {!selected?<><div className="mystery-grid">{missions.map(item=><article className={`mystery-card theme-${item.theme}`} key={item.id}><div className="mystery-card-top"><span>CASE {item.number}</span>{completed.includes(item.id)?<span className="case-complete"><CheckCircle2 size={14}/> Evidence traced</span>:<Search size={18}/>}</div><h3>{item.title}</h3><p>{item.brief}</p><div className="mystery-card-bottom"><small>{item.skill}</small><button className="button secondary" disabled={busy} onClick={()=>open(item.id)}>Open case {item.number} <ArrowRight size={14}/></button></div></article>)}</div>{busy&&<p aria-live="polite">Opening the case file…</p>}<p className="mystery-footnote">All genes, annotations, and scenarios here are fabricated. A supported “unresolved” conclusion completes a trail, too. Completed trails are saved in this browser when storage is available.</p></>:<>
      <div className="case-heading"><button className="text-button" onClick={()=>{revision.current++;setSelected(null);setBusy(false);setError('')}}><ArrowLeft size={14}/> All case files</button><span>CASE {selected.mission.number} · SYNTHETIC</span></div>
      <section className="panel case-brief"><div><span className="eyebrow">YOUR ASSIGNMENT</span><h2>{selected.mission.title}</h2><p>{selected.mission.brief}</p></div><ol>{selected.mission.clues.map(clue=><li key={clue}>{clue}</li>)}</ol></section>
      <AnimatedReplay key={selected.result.id} result={selected.result} onEvidence={setEvidenceId}/>
      {evidence&&<section className="panel case-evidence"><div className="case-evidence-heading"><h3>{evidence.description}</h3><button className="text-button" onClick={()=>setEvidenceId(null)}>Close evidence</button></div><code>{evidence.id}</code><pre>{JSON.stringify(evidence.data,null,2)}</pre></section>}
      <section className="panel hypothesis-panel"><span className="eyebrow">MAKE THE CALL</span><h2>{selected.mission.question}</h2><p>Choose a hypothesis after inspecting the clues. You can revise it as often as you like.</p><fieldset disabled={busy}><legend className="sr-only">Your hypothesis</legend>{selected.mission.hypotheses.map(option=><label className={`hypothesis-option ${choice===option.id?'chosen':''}`} key={option.id}><input type="radio" name="hypothesis" value={option.id} checked={choice===option.id} onChange={()=>{setChoice(option.id);setAssessment(null)}}/><span>{option.label}</span></label>)}</fieldset><button className="button primary" disabled={busy||!choice} onClick={check}><Search size={15}/>{busy?'Checking evidence…':'Check hypothesis'}</button>
        {assessment&&<div className={`case-assessment ${assessment.matches_evidence?'supported':'review'}`} aria-live="polite"><div>{assessment.matches_evidence?<CheckCircle2 size={22}/>:<Search size={22}/>}<h3>{assessment.matches_evidence?'Evidence traced':'A clue worth revisiting'}</h3></div><strong>{assessment.conclusion}</strong><p>{assessment.explanation}</p><div className="replay-evidence">{assessment.evidence_ids.map(id=><button key={id} className="text-button" onClick={()=>setEvidenceId(id)}>Inspect {id} <ArrowRight size={12}/></button>)}</div></div>}
      </section>
      <section className="case-workbench"><div><FolderOpen size={22}/><div><h3>Take the case into the workbench</h3><p>Save the comparison, explore every field, export its bundle, or pin a regression test.</p></div></div><button className="button secondary" disabled={busy} onClick={async()=>{setBusy(true);try{await onOpen(selected.result.input)}finally{setBusy(false)}}}><Sparkles size={15}/> Open & save investigation</button></section>
    </>}
  </div>
}
