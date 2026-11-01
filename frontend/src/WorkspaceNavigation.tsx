import type {MouseEvent} from 'react'
import {ArrowRight, FileJson, FlaskConical, GitCompareArrows, Globe2} from 'lucide-react'
import {version as appVersion} from '../package.json'
import type {Tab} from './routing'

type EngineState='checking'|'online'|'offline'

export function WorkspaceHeader({tab,resultId,onNavigate,onHome}:{tab:Tab;resultId?:string;onNavigate:(tab:Tab)=>void;onHome:()=>void}) {
  function navigate(event:MouseEvent<HTMLAnchorElement>,next:Tab) {
    if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return
    event.preventDefault();onNavigate(next)
  }
  return <header className="workspace-header">
    <button className="workspace-brand" onClick={onHome} aria-label="GenomeDebugger home"><GitCompareArrows size={25}/><span>GenomeDebugger</span></button>
    <nav className="workspace-navigation" aria-label="Main navigation">
      <a href={resultId?`#/comparison/${resultId}/overview`:'#/overview'} aria-current={!['library','help','data'].includes(tab)?'page':undefined} onClick={event=>navigate(event,'overview')}>Compare</a>
      <a href="#/library" aria-current={tab==='library'?'page':undefined} onClick={event=>navigate(event,'library')}>Saved work</a>
      <a href="#/help" aria-current={tab==='help'?'page':undefined} onClick={event=>navigate(event,'help')}>Guide</a>
    </nav>
  </header>
}

export function ComparisonSteps({tab,hasResult,onChoose,onReview,onUnderstand}:{tab:Tab;hasResult:boolean;onChoose:()=>void;onReview:()=>void;onUnderstand:()=>void}) {
  const active=tab==='input'?1:!hasResult||tab==='source'?0:2
  return <nav className="comparison-steps" aria-label="Comparison steps"><ol>
    {[{name:'Choose inputs',action:onChoose},{name:'Review inputs',action:onReview},{name:'Understand',action:onUnderstand}].map((step,index)=><li key={step.name}><button aria-current={active===index?'step':undefined} onClick={step.action} disabled={index===2&&!hasResult}><span aria-hidden="true">{index+1}</span>{step.name}</button></li>)}
  </ol></nav>
}

export function StartComparison({busy,onInput,onSource,onExample}:{busy:boolean;onInput:()=>void;onSource:()=>void;onExample:()=>void}) {
  return <section className="comparison-start" aria-label="Choose comparison inputs">
    <h2>Choose a starting point</h2><p>Start with existing analysis outputs, a public DNA change, or a made-up example.</p>
    <div className="starting-paths">
      <article><FileJson size={22}/><div><h3>I have two analysis outputs</h3><p>Import supported files or copy the values reported by each analysis.</p></div><button className="button primary" onClick={onInput}>Enter my results <ArrowRight size={16}/></button></article>
      <article><Globe2 size={22}/><div><h3>I want to look up a public DNA change</h3><p>Capture public predictions for a supported GRCh38 single-letter change.</p></div><button className="button secondary" onClick={onSource}>Explore public data <ArrowRight size={16}/></button></article>
      <article><FlaskConical size={22}/><div><h3>Show me how it works</h3><p>A short synthetic comparison explains the inputs and the findings.</p></div><button className="button secondary" onClick={onExample} disabled={busy}>Try an example <ArrowRight size={16}/></button></article>
    </div>
  </section>
}

export function WorkspaceFooter({hosted,engineState,engineVersion,onData}:{hosted:boolean;engineState:EngineState;engineVersion:string;onData:()=>void}) {
  return <footer className="workspace-footer">
    <div><span>GenomeDebugger · Research and bioinformatics QA</span><small>For research; not a diagnosis</small></div>
    <div className="workspace-utilities"><button className="text-button" onClick={onData}>{hosted?'Workspace data':'Local data'} and settings</button><details><summary>GenomeDebugger v{appVersion}</summary><p>Comparison engine {engineVersion?`v${engineVersion}`:'version unavailable'}</p><p>{hosted?'Public preview':'Local application'} · {engineState==='online'?'Connected':engineState==='offline'?'Unavailable':'Checking connection'}</p></details></div>
  </footer>
}
