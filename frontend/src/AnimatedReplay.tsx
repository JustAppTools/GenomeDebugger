import {useEffect, useState} from 'react'
import {ArrowRight, Check, CircleHelp, Pause, Play, RotateCcw, SkipBack, SkipForward} from 'lucide-react'
import type {Result} from './types'

type Step = {name:string; title:string; a:string; b:string; detail:string; signal:'same'|'changed'|'open'|'info'; evidence:string[]}
const shown=(value:string|null|undefined)=>value || 'Not supplied'

export function replaySteps(result:Result):Step[] {
  const [a,b]=result.input.snapshots
  const differences=result.differences
  const ids=(test:(field:string)=>boolean)=>differences.filter(d=>test(d.field)).flatMap(d=>d.evidence_ids)
  const transcripts=(snapshot:typeof a)=>[...new Set([snapshot.annotation,...(snapshot.annotations??[])].map(row=>row.transcript_id))]
  const summary=(snapshot:typeof a)=>`${snapshot.annotation.transcript_id} · ${transcripts(snapshot).length} transcript ID${transcripts(snapshot).length===1?'':'s'}`
  const annotationChanged=differences.some(d=>d.field==='transcript_id'||d.field.startsWith('annotations['))
  const outputChanged=differences.some(d=>['consequence','protein_consequence','gene_id'].includes(d.field))
  return [
    {name:'Input',title:'Two snapshots enter the workbench',a:`${a.provenance.tool} ${a.provenance.tool_version} · ${a.provenance.source_release}`,b:`${b.provenance.tool} ${b.provenance.tool_version} · ${b.provenance.source_release}`,
      detail:'Read the recorded software and source releases first. A version difference is a clue; it does not establish a cause.',signal:'info',evidence:ids(field=>['tool','tool_version','source_release','source_name'].includes(field)||field.startsWith('configuration.'))},
    {name:'Reference',title:'Do the allele descriptions line up?',a:`${a.variant.sequence_id}:${a.variant.position} ${a.variant.ref} → ${a.variant.alt}`,b:`${b.variant.sequence_id}:${b.variant.position} ${b.variant.ref} → ${b.variant.alt}`,
      detail:result.identity.explanation,signal:result.identity.status==='verified'?'same':result.identity.status==='rejected'?'changed':'open',evidence:result.identity.evidence_ids},
    {name:'Transcript',title:'Follow the selected transcript and its companions',a:summary(a),b:summary(b),
      detail:'Counts include the selected transcript and additional rows for the primary variant. Open the linked field evidence to inspect missing rows.',signal:annotationChanged?'changed':'same',evidence:ids(field=>field==='transcript_id'||field.startsWith('annotations['))},
    {name:'Consequence',title:'Where do the predictions diverge?',a:`${a.annotation.consequence} · ${shown(a.annotation.protein_consequence)}`,b:`${b.annotation.consequence} · ${shown(b.annotation.protein_consequence)}`,
      detail:'These are the recorded primary predictions. A changed prediction is an observation, not a clinical classification or a demonstrated causal explanation.',signal:outputChanged?'changed':'same',evidence:ids(field=>['consequence','protein_consequence','gene_id'].includes(field))},
    {name:'Comparison',title:'Keep the conclusion as strong as the evidence',a:`${differences.length} observed field differences`,b:`${differences.filter(d=>d.meaningful).length} meaningful differences`,
      detail:result.findings.length?result.findings.map(f=>`${f.status.toUpperCase()}: ${f.explanation}`).join(' '):'No explanatory finding was established by this comparison.',signal:result.findings.some(f=>f.status==='verified')?'same':'open',evidence:[...new Set(result.findings.flatMap(f=>f.evidence_ids))]},
  ]
}

export default function AnimatedReplay({result,onEvidence}:{result:Result;onEvidence:(id:string)=>void}) {
  const [index,setIndex]=useState(0)
  const [playing,setPlaying]=useState(false)
  const [stopped,setStopped]=useState(false)
  const steps=replaySteps(result)
  const firstChange=steps.findIndex(step=>step.signal==='changed')
  const step=steps[index]
  useEffect(()=>{
    if(!playing)return
    if(index===steps.length-1){setPlaying(false);return}
    const timer=window.setTimeout(()=>{
      const next=index+1
      setIndex(next)
      if(next===firstChange){setPlaying(false);setStopped(true)}
    },1600)
    return ()=>window.clearTimeout(timer)
  },[playing,index,firstChange,steps.length])
  useEffect(()=>{
    const pause=()=>{if(document.hidden)setPlaying(false)}
    document.addEventListener('visibilitychange',pause)
    return ()=>document.removeEventListener('visibilitychange',pause)
  },[])
  function go(next:number){setPlaying(false);setStopped(false);setIndex(next)}
  const evidence=[...new Set(step.evidence)].filter(id=>result.evidence.some(item=>item.id===id))
  return <section className="panel replay-panel" aria-label="Recorded analysis replay">
    <div className="replay-heading"><div><span className="eyebrow">FOLLOW THE EVIDENCE</span><h2>Watch the discrepancy unfold</h2><p>Walk through recorded inputs and findings. Playback illustrates this comparison; it does not rerun an annotation tool.</p></div><span className="replay-record">{result.input.synthetic?'SYNTHETIC CASE':'RECORDED COMPARISON'}</span></div>
    <div className="replay-track" aria-label="Replay stages">{steps.map((item,i)=><button key={item.name} className={`replay-step ${i===index?'active':''} ${i<index?'visited':''}`} aria-current={i===index?'step':undefined} aria-label={`Replay stage ${i+1}: ${item.name}`} onClick={()=>go(i)}><span>{i<index?<Check size={14}/>:String(i+1).padStart(2,'0')}</span><b><span className="replay-label-long">{item.name}</span><span className="replay-label-short">{['Input','Reference','Transcript','Effect','Review'][i]}</span></b></button>)}</div>
    <div className={`replay-scene signal-${step.signal}`} key={index} aria-live="polite" aria-atomic="true">
      <div className="replay-scene-title"><h3>{step.title}</h3><span>{step.signal==='changed'?'Observed difference':step.signal==='open'?<><CircleHelp size={13}/> Evidence limit</>:step.signal==='same'?'Values checked':'Starting clues'}</span></div>
      <div className="replay-pair"><div><small>{index===4?'COMPARISON':'ANALYSIS A'}</small><strong>{step.a}</strong></div><ArrowRight size={18}/><div><small>{index===4?'REVIEW':'ANALYSIS B'}</small><strong>{step.b}</strong></div></div>
      <p>{step.detail}</p>{evidence.length>0&&<div className="replay-evidence">{evidence.slice(0,5).map(id=><button className="text-button" key={id} onClick={()=>onEvidence(id)}>Inspect {id} <ArrowRight size={12}/></button>)}</div>}
    </div>
    <div className="replay-controls"><button className="button secondary" aria-label="Previous replay step" disabled={index===0} onClick={()=>go(index-1)}><SkipBack size={15}/></button><button className="button primary" onClick={()=>{setStopped(false);if(index===steps.length-1)setIndex(0);setPlaying(!playing)}}>{playing?<Pause size={15}/>:<Play size={15}/>} {playing?'Pause replay':'Play replay'}</button><button className="button secondary" aria-label="Next replay step" disabled={index===steps.length-1} onClick={()=>go(index+1)}><SkipForward size={15}/></button><button className="text-button" aria-label="Restart replay" onClick={()=>go(0)}><RotateCcw size={14}/> Reset</button><span>{stopped?'Paused at an observed difference.':`Step ${index+1} of ${steps.length}`}</span></div>
  </section>
}
