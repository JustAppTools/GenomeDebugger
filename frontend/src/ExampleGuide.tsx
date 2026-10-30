import type {Result} from './types'

export default function ExampleGuide({result,busy,onMatching,onUncertain,onSwitch}:{result:Result;busy:boolean;onMatching:()=>void;onUncertain:()=>void;onSwitch:()=>void}) {
  const [a,b]=result.input.snapshots
  const contexts=result.input.snapshots.filter(snapshot=>snapshot.variant.reference_context).length
  const replay=result.evidence.some(record=>record.kind==='controlled_replay')
  return <section className="example-guide panel"><h2>How to read this example</h2><ol>
    <li>{contexts===2?'The two analyses use made-up transcript labels and supplied reference letters.':contexts===0?'This made-up example omits reference context. Local DNA identity cannot be confirmed from the supplied letters because they are missing.':'Only one analysis supplies reference context. That is not enough for a local identity comparison.'}</li>
    <li>{a.annotation.transcript_id===b.annotation.transcript_id&&a.annotation.consequence===b.annotation.consequence?'The supplied transcripts and predicted effects match. Matching outputs alone do not establish correctness.':'The supplied transcripts or predictions differ. Read the exact changed fields; a difference alone does not prove its cause.'}</li>
    <li>{replay?'The controlled lookup repeats those outputs within this constructed example. It does not test a real annotation system.':result.input.controlled_lookup?'A constructed lookup was supplied, but no controlled replay was recorded for this comparison.':'No controlled lookup was provided or replayed for this example.'}</li>
  </ol><div className="concept-transcripts" aria-label="Conceptual transcript selection diagram"><span>Reported annotations</span><div><span>Analysis A → transcript {a.annotation.transcript_id}</span><span>Analysis B → transcript {b.annotation.transcript_id}</span></div><small>Conceptual explanation only; this does not show exon positions or gene structure.</small></div><details><summary>Try another teaching case</summary><div className="source-actions"><button className="button secondary" onClick={onMatching} disabled={busy}>Matching outputs example</button><button className="button secondary" onClick={onUncertain} disabled={busy}>Missing evidence example</button><button className="button secondary" onClick={onSwitch} disabled={busy}>Try an example</button></div></details></section>
}
