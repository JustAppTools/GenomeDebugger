import type {Result} from './types'
import {describeEffect,displayValue,evidenceTitle,fieldLabel} from './explanations'

function ReadableValue({value,depth=0}:{value:unknown;depth?:number}) {
  if(value===null||typeof value!=='object'){const text=displayValue(value);return text.length>600?<details><summary>Long recorded value ({text.length} characters)</summary><pre>{text}</pre></details>:<span>{text}</span>}
  if(depth>=5)return <span>Nested data is available in the original record below.</span>
  if(Array.isArray(value))return value.length?<ul>{value.map((item,i)=><li key={i}><ReadableValue value={item} depth={depth+1}/></li>)}</ul>:<span>No entries</span>
  return <dl className="evidence-facts">{Object.entries(value).map(([key,item])=><div key={key}><dt>{fieldLabel(key)}</dt><dd><ReadableValue value={item} depth={depth+1}/></dd></div>)}</dl>
}
function EditView({value,side}:{value:unknown;side:string}) {
  const v=value as {position?:number;ref?:string;alt?:string;reference_context?:{start:number;sequence:string}}|null
  const context=v?.reference_context
  const offset=context&&v?.position!==undefined?v.position-context.start:-1
  const canDraw=!!context&&context.sequence.length<=120&&offset>=0&&offset+(v?.ref?.length??0)<=context.sequence.length
  return <article><h4>{side}</h4>{canDraw&&context&&<figure className="dna-view"><figcaption>Supplied reference letters, starting at {context.start}</figcaption><code>{context.sequence.slice(0,offset)}<mark>{context.sequence.slice(offset,offset+(v?.ref?.length??0))}</mark>{context.sequence.slice(offset+(v?.ref?.length??0))}</code><p>At position {v?.position}: replace <strong>{v?.ref}</strong> with <strong>{v?.alt}</strong>.</p><figcaption>After the edit in this supplied text</figcaption><code>{context.sequence.slice(0,offset)}<mark>{v?.alt}</mark>{context.sequence.slice(offset+(v?.ref?.length??0))}</code></figure>}<ReadableValue value={value}/></article>
}
export default function EvidenceInspector({result,selected,onSelect}:{result:Result;selected:string|null;onSelect:(id:string)=>void}) {
  const active=result.evidence.find(e=>e.id===selected)??result.evidence[0]
  const linked=active?result.findings.filter(f=>f.evidence_ids.includes(active.id)):[]
  return <section className="panel evidence-panel"><div className="panel-heading"><div><span className="eyebrow">Supporting details</span><h2>Evidence inspector</h2><p>See what was compared, what was checked, and which conclusions use this record.</p></div></div><div className="evidence-layout"><nav className="evidence-list" aria-label="Evidence records">{result.evidence.map(e=><button key={e.id} className={`evidence-item ${active?.id===e.id?'selected':''}`} aria-current={active?.id===e.id?'true':undefined} onClick={()=>onSelect(e.id)}><span>{evidenceTitle(e)}</span><small>{e.kind.replaceAll('_',' ')}</small></button>)}</nav><div className="evidence-detail">{active?<>
    <h3>{evidenceTitle(active)}</h3><p>{active.description}</p>
    {active.kind==='input'&&'a' in active.data&&'b' in active.data?<><p>These values were supplied with the analyses. Matching their reference text alone does not verify an external reference genome.</p><ReadableValue value={Object.fromEntries(Object.entries(active.data).filter(([key])=>key!=='a'&&key!=='b'))}/><div className="readable-pair"><EditView side="Analysis A" value={active.data.a}/><EditView side="Analysis B" value={active.data.b}/></div></>:<><ReadableValue value={active.data}/>{active.kind==='field_comparison'&&(active.data.field==='consequence'||String(active.data.field).endsWith('.consequence'))&&<p className="help-copy">A: {describeEffect(active.data.a as string)} B: {describeEffect(active.data.b as string)}</p>}</>}
    {active.kind==='controlled_replay'&&<p className="source-caveat">This replay uses the supplied synthetic lookup table. It does not establish a cause in an external annotation system.</p>}
    <section className="evidence-conclusions"><h4>Conclusions using this record</h4>{linked.length?linked.map((f,i)=><p key={i}><strong>{f.status}: {f.cause}.</strong> {f.explanation}</p>):<p>This record supports a field or DNA identity comparison; no additional causal conclusion is attached to it.</p>}</section>
    <details className="raw-record"><summary>Original record (JSON and technical ID)</summary><code>{active.id}</code><pre>{JSON.stringify(active.data,null,2)}</pre></details>
  </>:<p>No evidence recorded.</p>}</div></div></section>
}
