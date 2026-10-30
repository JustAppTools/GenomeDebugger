import {useId,useState} from 'react'
import type { Annotation, InvestigationInput, Snapshot, Variant } from './types'
import {describeEffect} from './explanations'

const blankAnnotation = (): Annotation => ({gene_id:'', transcript_id:'', consequence:''})
const blankVariant = (): Variant => ({assembly:'', sequence_id:'', position:0, ref:'', alt:''})
function blankSnapshot(id: string): Snapshot {
  return {id, label:`Analysis ${id}`, variant:blankVariant(), annotation:blankAnnotation(),
    provenance:{tool:'',tool_version:'',source_name:'',source_release:'',configuration:{}}}
}
export function blankInput(): InvestigationInput {
  return {title:'',synthetic:false,snapshots:[blankSnapshot('A'),blankSnapshot('B')]}
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

export function normalizeGuidedInput(value: unknown): unknown {
  return object(value) && value.synthetic === undefined ? {...value, synthetic:false} : value
}

// Check types before accessing any nested imported value. Semantic checks below
// can then use strings and arrays safely while keeping incomplete drafts editable.
function structureErrors(value: unknown): string[] {
  const errors: string[] = []
  function stringFields(value: Record<string,unknown>, fields: string[], path: string) {
    for (const key of fields) if (typeof value[key] !== 'string') errors.push(`${path}.${key} must be text`)
  }
  function variant(value: unknown, path: string) {
    if (!object(value)) {errors.push(`${path} must be an object`);return}
    stringFields(value,['assembly','sequence_id','ref','alt'],path)
    if (typeof value.position !== 'number') errors.push(`${path}.position must be a number`)
    if (value.reference_context !== undefined && value.reference_context !== null) {
      const context = value.reference_context
      if (!object(context)) errors.push(`${path}.reference_context must be an object`)
      else {
        if (typeof context.start !== 'number') errors.push(`${path}.reference_context.start must be a number`)
        if (typeof context.sequence !== 'string') errors.push(`${path}.reference_context.sequence must be text`)
      }
    }
  }
  function annotation(value: unknown, path: string) {
    if (!object(value)) {errors.push(`${path} must be an object`);return}
    stringFields(value,['gene_id','transcript_id','consequence'],path)
    if (value.protein_consequence != null && typeof value.protein_consequence !== 'string') errors.push(`${path}.protein_consequence must be text`)
    if (value.clinical != null) {
      if (!object(value.clinical)) errors.push(`${path}.clinical must be an object`)
      else {
        stringFields(value.clinical,['framework','condition_id','classification'],`${path}.clinical`)
        for (const key of ['review_status','assertion_date']) if (value.clinical[key] != null && typeof value.clinical[key] !== 'string') errors.push(`${path}.clinical.${key} must be text`)
      }
    }
  }
  function annotations(value: unknown, path: string) {
    if (!Array.isArray(value)) errors.push(`${path} must be an array`)
    else value.forEach((row,index)=>annotation(row,`${path}[${index}]`))
  }
  if (!object(value)) return ['Investigation must be an object']
  stringFields(value,['title'],'Investigation')
  if (typeof value.synthetic !== 'boolean') errors.push('Investigation.synthetic must be true or false')
  if (!Array.isArray(value.snapshots) || value.snapshots.length !== 2) return [...errors,'Two analysis snapshots are required']
  value.snapshots.forEach((snapshot,index)=>{
    const path = `Analysis ${index+1}`
    if (!object(snapshot)) {errors.push(`${path} must be an object`);return}
    stringFields(snapshot,['id','label'],path)
    variant(snapshot.variant,`${path}.variant`)
    annotation(snapshot.annotation,`${path}.annotation`)
    if (snapshot.annotations !== undefined) annotations(snapshot.annotations,`${path}.annotations`)
    if (!object(snapshot.provenance)) errors.push(`${path}.provenance must be an object`)
    else stringFields(snapshot.provenance,['tool','tool_version','source_name','source_release'],`${path}.provenance`)
    if (snapshot.variant_records !== undefined) {
      if (!Array.isArray(snapshot.variant_records)) errors.push(`${path}.variant_records must be an array`)
      else snapshot.variant_records.forEach((record,recordIndex)=>{
        const prefix = `${path}.variant_records[${recordIndex}]`
        if (!object(record)) {errors.push(`${prefix} must be an object`);return}
        variant(record.variant,`${prefix}.variant`)
        annotations(record.annotations,`${prefix}.annotations`)
      })
    }
  })
  return errors
}

export function isGuidedInput(value: unknown): value is InvestigationInput {return structureErrors(value).length === 0}

export function validateGuidedInput(value: unknown): string[] {
  const normalized = normalizeGuidedInput(value)
  const errors = structureErrors(normalized)
  if (errors.length) return errors
  const input = normalized as InvestigationInput
  function text(value: string, max: number, path: string) {
    if (!value.trim()) errors.push(`${path} is required`)
    else if (Array.from(value).length > max) errors.push(`${path} exceeds ${max} characters`)
  }
  function variant(v: Variant, path: string) {
    text(v.assembly,50,`${path}: assembly`);text(v.sequence_id,100,`${path}: sequence accession`)
    if (!Number.isInteger(v.position) || v.position < 1) errors.push(`${path}: position must be positive`)
    if (![v.ref,v.alt].every(allele=>/^[ACGT]{1,100}$/.test(allele))) errors.push(`${path}: alleles must contain 1–100 A/C/G/T bases`)
    if (v.ref === v.alt) errors.push(`${path}: reference and alternate must differ`)
    const context = v.reference_context
    if (context) {
      if (!Number.isInteger(context.start) || context.start < 1) errors.push(`${path}: context start must be positive`)
      if (!/^[ACGT]{1,10000}$/.test(context.sequence)) errors.push(`${path}: context needs an A/C/G/T sequence`)
      else {
        const offset = v.position-context.start
        if (offset < 0 || context.sequence.slice(offset,offset+v.ref.length)!==v.ref) errors.push(`${path}: reference allele must match the sequence at its position`)
      }
    }
  }
  function annotation(row: Annotation, path: string) {
    text(row.gene_id,100,`${path}: gene ID`);text(row.transcript_id,100,`${path}: transcript ID`)
    text(row.consequence,500,`${path}: consequence`)
    if (row.clinical) for (const key of ['framework','condition_id','classification'] as const) text(row.clinical[key],100,`${path}: clinical ${key}`)
  }
  function uniqueAnnotations(rows: Annotation[], path: string) {
    const keys = rows.map(row=>JSON.stringify([row.gene_id,row.transcript_id,row.clinical?.framework ?? '',row.clinical?.condition_id ?? '']))
    if (new Set(keys).size !== keys.length) errors.push(`${path}: annotation rows must have unique gene, transcript, and clinical context`)
  }
  text(input.title,200,'Title')
  if (input.snapshots[0].id === input.snapshots[1].id) errors.push('Analysis IDs must differ')
  input.snapshots.forEach((snapshot,index)=>{
    const path = `Analysis ${index+1}`
    text(snapshot.id,100,`${path}: ID`);text(snapshot.label,150,`${path}: label`)
    variant(snapshot.variant,path);annotation(snapshot.annotation,path)
    for (const key of ['tool','tool_version','source_name','source_release'] as const) text(snapshot.provenance[key],100,`${path}: ${key}`)
    const rows = snapshot.annotations ?? []
    if (rows.length > 1000) errors.push(`${path}: maximum 1000 additional annotations`)
    rows.forEach((row,i)=>annotation(row,`${path}, annotation ${i+2}`))
    uniqueAnnotations([snapshot.annotation,...rows],path)
    const records = snapshot.variant_records ?? []
    if (records.length > 50) errors.push(`${path}: maximum 50 additional variants`)
    const variants = [snapshot.variant,...records.map(record=>record.variant)].map(v=>JSON.stringify([v.assembly,v.sequence_id,v.position,v.ref,v.alt]))
    if (new Set(variants).size !== variants.length) errors.push(`${path}: variant representations must be unique`)
    records.forEach((record,i)=>{
      const prefix = `${path}, variant ${i+2}`
      variant(record.variant,prefix)
      if (!record.annotations.length || record.annotations.length > 100) errors.push(`${prefix}: use 1–100 annotations`)
      record.annotations.forEach((row,j)=>annotation(row,`${prefix}, annotation ${j+1}`))
      uniqueAnnotations(record.annotations,prefix)
    })
  })
  return errors
}

const help:Record<string,string>={
  assembly:'Required. Copy the reference genome version from the analysis settings or file header (for example GRCh38). Do not guess.',
  sequence_id:'Required. Copy the exact versioned reference-sequence accession from the analysis or reference manifest (for example NC_000001.11). A chromosome label is not always an accession.',
  position:'Required. Copy the reported coordinate and confirm it is one-based. Convert a zero-based source explicitly before entry.',
  ref:'Required. The original A/C/G/T letters reported by the analysis at this position.',
  alt:'Required. The replacement A/C/G/T letters reported by the analysis. Must differ from Reference.',
  gene_id:'Required. The gene identifier from the annotation output. Use the producing tool’s identifier; do not invent one.',
  transcript_id:'Required. Copy the selected transcript identifier, including its version if supplied.',
  consequence:'Required. Copy the producing tool’s predicted-effect term, such as missense_variant. This is an annotation, not a diagnosis.',
  protein_consequence:'Optional. Copy the reported protein change if one was supplied. Leave blank if unavailable.',
  tool:'Required. Name of the software that produced this analysis (for example VEP).',
  tool_version:'Required. Obtain the version from the original run log, header, or person who ran the analysis.',
  source_name:'Required. Name of the annotation database or reference used by the analysis.',
  source_release:'Required. Obtain the database/reference release from the original run metadata. A current website release does not identify a past run.',
}
function GuideField({label,name,value,onChange,type='text',optional=false,hint}:{label:string;name:string;value:string|number;onChange:(s:string)=>void;type?:string;optional?:boolean;hint:string}) {
  const id=useId(),[touched,setTouched]=useState(false)
  const invalid=touched&&!optional&&(type==='number'?!(Number(value)>0):!String(value).trim())
  return <label className="guide-field" htmlFor={id}>{label} <span className="requirement">{optional?'Optional':'Required'}</span><input id={id} aria-label={name} aria-describedby={`${id}-help${invalid?` ${id}-error`:''}`} aria-invalid={invalid||undefined} required={!optional} type={type} min={type==='number'?1:undefined} value={value===0&&type==='number'?'':value} onBlur={()=>setTouched(true)} onChange={e=>onChange(e.target.value)}/><small id={`${id}-help`}>{hint}</small>{invalid&&<span className="field-error" id={`${id}-error`}>Enter {label.toLowerCase()} from the original analysis.</span>}</label>
}
function VariantFields({value,prefix,onChange}:{value:Variant;prefix:string;onChange:(value:Variant)=>void}) {
  const setContext = (key:'start'|'sequence',text:string) => onChange({...value,reference_context:{
    start:value.reference_context?.start ?? 0, sequence:value.reference_context?.sequence ?? '',
    [key]:key==='start'?Number(text):text.toUpperCase(),
  }})
  return <>
    <div className="guide-pair">{(['assembly','sequence_id'] as const).map((key,i)=><GuideField key={key} label={i?'Sequence accession':'Assembly'} name={`${prefix} ${i?'sequence accession':'assembly'}`} value={value[key]} hint={help[key]} onChange={text=>onChange({...value,[key]:text})}/>)}</div>
    <div className="guide-triplet"><GuideField label="Position" name={`${prefix} position`} type="number" value={value.position} hint={help.position} onChange={text=>onChange({...value,position:Number(text)})}/>{(['ref','alt'] as const).map((key,i)=><GuideField key={key} label={i?'Alternate':'Reference'} name={`${prefix} ${i?'alternate':'reference'}`} hint={help[key]} value={value[key]} onChange={text=>onChange({...value,[key]:text.toUpperCase()})}/>)}</div>
    <details className="optional-fields" open={!!value.reference_context}><summary>Optional reference context</summary><p>Obtain these letters from the same reference assembly. Leave both absent if unavailable; local allele identity will remain unresolved. Supplying text does not independently verify a reference.</p><div className="guide-pair"><GuideField label="Context start" name={`${prefix} context start`} type="number" optional value={value.reference_context?.start||''} hint="One-based position of the first reference letter in this context." onChange={text=>setContext('start',text)}/><GuideField label="Reference sequence" name={`${prefix} reference sequence`} optional value={value.reference_context?.sequence??''} hint="A/C/G/T letters from the reference at Context start, covering the variant." onChange={text=>setContext('sequence',text)}/></div>
    {value.reference_context&&<button className="text-button" onClick={()=>onChange({...value,reference_context:null})}>Remove reference context for {prefix}</button>}
    </details>
  </>
}

function AnnotationFields({value,prefix,onChange}:{value:Annotation;prefix:string;onChange:(value:Annotation)=>void}) {
  return <div className="guide-pair">{([
    ['gene_id','Gene ID'],['transcript_id','Transcript ID'],['consequence','Consequence'],['protein_consequence','Protein consequence'],
  ] as const).map(([key,label])=><GuideField key={key} label={label} name={`${prefix} ${label.toLowerCase()}`} value={value[key]??''} optional={key==='protein_consequence'} hint={help[key]} onChange={text=>onChange({...value,[key]:key==='protein_consequence'&&text===''?null:text})}/>)}</div>
}

export default function GuidedInput({value,onChange,onRun,busy}:{value:unknown;onChange:(value:InvestigationInput)=>void;onRun:()=>void;busy:boolean}) {
  const [step,setStep]=useState(()=>validateGuidedInput(value).length?0:3),[all,setAll]=useState(false),[attempted,setAttempted]=useState(false)
  const normalized = normalizeGuidedInput(value)
  const input = normalized === null ? blankInput() : isGuidedInput(normalized) ? normalized : null
  if (!input) return <div className="guide-errors" role="alert">This input has invalid field types. Repair them in JSON mode: {validateGuidedInput(value).join('; ')}.</div>
  function edit(change:(next:InvestigationInput)=>void) {
    const next = JSON.parse(JSON.stringify(input)) as InvestigationInput
    change(next)
    next.snapshots.forEach((snapshot,i)=>{if(snapshot.provenance.configuration?.original_utf8&&JSON.stringify(snapshot)!==JSON.stringify(input!.snapshots[i]))snapshot.provenance.configuration.import_output_edited='true'})
    onChange(next)
  }
  const errors = validateGuidedInput(input)
  function focusIssue(message:string){
    setAll(true);setAttempted(true)
    const match=/^Analysis ([12])(?:, variant (\d+))?(?:, annotation (\d+))?: (.+)/.exec(message)
    let name='Investigation title'
    if(match){
      const [,side,variant,annotation,issue]=match
      const field=issue.replace(/ is required.*| exceeds.*| must.*| needs.*/,'').replaceAll('_',' ').toLowerCase()
      const target=field.startsWith('alleles')||field.startsWith('reference and')?'reference':field.startsWith('context')?'context start':field.startsWith('reference allele')?'reference sequence':field
      name=`Analysis ${side}${variant?` variant ${variant}`:''}${annotation?variant?` annotation ${annotation}`:` additional annotation ${Number(annotation)-1}`:''} ${target}`
    }
    window.requestAnimationFrame(()=>{const target=[...document.querySelectorAll<HTMLInputElement>('.guided-input input')].find(field=>field.getAttribute('aria-label')===name);target?.focus();target?.scrollIntoView({block:'center'})})
  }
  return <div className="guided-input">
    <div className="guided-intro"><h3>Build a comparison</h3><p>Copy values from two existing analysis outputs. If you do not have the required metadata, ask the person who produced the analysis or use a supported import. No scientific values are filled in by guessing.</p></div>
    <nav className="input-steps" aria-label="Input steps">{['DNA change','Predictions','Tools and sources','Review'].map((label,i)=><button key={label} className={step===i?'selected':''} aria-current={step===i?'step':undefined} onClick={()=>{setStep(i);setAttempted(false)}}>{i+1}. {label}</button>)}</nav>
    <button className="text-button" onClick={()=>setAll(!all)}>{all?'Use step-by-step entry':'Show all fields (experienced users)'}</button>
    <GuideField label="Investigation title" name="Investigation title" value={input.title} hint="Required. Choose your own name to recognize this comparison; this is a label, not scientific metadata." onChange={text=>edit(next=>{next.title=text})}/>
    {(step<3||all)&&<div className="guide-grid">{input.snapshots.map((snapshot,index)=>{
      const prefix = `Analysis ${index+1}`
      const side = index===0?'A':'B'
      return <section key={index} className="guide-card">
        <h3>Analysis {side}</h3>
        <GuideField label="Label" name={`${prefix} label`} value={snapshot.label} hint="Required. Give this analysis a recognizable name, such as the producing tool and release." onChange={text=>edit(next=>{next.snapshots[index].label=text})}/>
        {(step===0||all)&&<><VariantFields value={snapshot.variant} prefix={prefix} onChange={value=>edit(next=>{next.snapshots[index].variant=value})}/>{index===1&&<button className="button secondary" onClick={()=>edit(next=>{next.snapshots[1].variant=structuredClone(next.snapshots[0].variant)})}>Copy confirmed DNA description from analysis A</button>}</>}
        {(step===1||all)&&<><AnnotationFields value={snapshot.annotation} prefix={prefix} onChange={value=>edit(next=>{next.snapshots[index].annotation=value})}/><p className="help-copy">{describeEffect(snapshot.annotation.consequence)}</p></>}
        {(step===1||all)&&<details className="optional-fields" open={all||!!(snapshot.annotations?.length||snapshot.variant_records?.length)}><summary>Additional annotations and variants (advanced)</summary><p>Additional variants are matched by exact submitted representation. This does not perform cross-assembly mapping.</p>
        {(snapshot.annotations ?? []).map((row,rowIndex)=><div className="guide-extra" key={rowIndex}><h4>Primary variant annotation {rowIndex+2}</h4><AnnotationFields value={row} prefix={`${prefix} additional annotation ${rowIndex+1}`} onChange={value=>edit(next=>{next.snapshots[index].annotations![rowIndex]=value})}/><button className="text-button" onClick={()=>edit(next=>{next.snapshots[index].annotations!.splice(rowIndex,1)})}>Remove annotation {rowIndex+2} from analysis {side}</button></div>)}
        <button className="button secondary" disabled={(snapshot.annotations?.length ?? 0)>=1000} onClick={()=>edit(next=>{(next.snapshots[index].annotations ??= []).push(blankAnnotation())})}>Add annotation to analysis {side}</button>
        {(snapshot.variant_records ?? []).map((record,recordIndex)=><div className="guide-extra" key={recordIndex}><h4>Variant {recordIndex+2}</h4>
          <VariantFields value={record.variant} prefix={`${prefix} variant ${recordIndex+2}`} onChange={value=>edit(next=>{next.snapshots[index].variant_records![recordIndex].variant=value})}/>
          {record.annotations.map((row,rowIndex)=><div key={rowIndex}><AnnotationFields value={row} prefix={`${prefix} variant ${recordIndex+2} annotation ${rowIndex+1}`} onChange={value=>edit(next=>{next.snapshots[index].variant_records![recordIndex].annotations[rowIndex]=value})}/>{record.annotations.length>1&&<button className="text-button" onClick={()=>edit(next=>{next.snapshots[index].variant_records![recordIndex].annotations.splice(rowIndex,1)})}>Remove annotation {rowIndex+1} from analysis {side} variant {recordIndex+2}</button>}</div>)}
          <button className="button secondary" disabled={record.annotations.length>=100} onClick={()=>edit(next=>{next.snapshots[index].variant_records![recordIndex].annotations.push(blankAnnotation())})}>Add annotation to analysis {side} variant {recordIndex+2}</button>
          <button className="text-button" onClick={()=>edit(next=>{next.snapshots[index].variant_records!.splice(recordIndex,1)})}>Remove variant {recordIndex+2} from analysis {side}</button>
        </div>)}
        <button className="button secondary" disabled={(snapshot.variant_records?.length ?? 0)>=50} onClick={()=>edit(next=>{(next.snapshots[index].variant_records ??= []).push({variant:blankVariant(),annotations:[blankAnnotation()]})})}>Add variant to analysis {side}</button></details>}
        {(step===2||all)&&<><h4>Analysis provenance</h4><p>These details are declarations from the original run. An imported file or a saved hash does not authenticate them.</p><div className="guide-pair">{(['tool','tool_version','source_name','source_release'] as const).map(key=><GuideField key={key} label={key.replaceAll('_',' ')} name={`${prefix} ${key.replaceAll('_',' ')}`} value={snapshot.provenance[key]} hint={help[key]} onChange={text=>edit(next=>{next.snapshots[index].provenance[key]=text})}/>)}</div></>}
      </section>
    })}</div>}
    {(step===3||all)&&<section className="readiness-review"><h3>Review before comparing</h3><div className="readable-pair">{input.snapshots.map((s,i)=><article key={s.id}><h4>Analysis {'AB'[i]} · {s.label}</h4><p>{s.variant.assembly||'Assembly missing'} · {s.variant.sequence_id||'Accession missing'}:{s.variant.position||'Position missing'} {s.variant.ref||'?'} → {s.variant.alt||'?'}</p><p>{s.annotation.transcript_id||'Transcript missing'} · {s.annotation.consequence||'Prediction missing'}</p><p>{s.provenance.tool||'Tool missing'} {s.provenance.tool_version} · {s.provenance.source_name||'Source missing'} {s.provenance.source_release}</p><p>{s.variant.reference_context?'Supplied reference context available; not externally verified.':'No supplied reference context; local DNA identity will remain unresolved.'}</p><p>{1+(s.variant_records?.length??0)} variants · {1+(s.annotations?.length??0)+(s.variant_records??[]).reduce((n,r)=>n+r.annotations.length,0)} annotation rows</p></article>)}</div><p>Comparison checks supplied outputs. Missing independent evidence can limit explanations even when the input is valid.</p></section>}
    {errors.length>0&&(step===3||attempted||all)&&<div className="guide-errors" role="status"><strong>Complete these fields before comparing:</strong><ul>{errors.map((error,i)=><li key={i}><button className="text-button" onClick={()=>focusIssue(error)}>{error}</button></li>)}</ul></div>}
    <div className="step-actions">{step>0&&!all&&<button className="button secondary" onClick={()=>setStep(step-1)}>Back</button>}{step<3&&!all&&<button className="button primary" onClick={()=>{setStep(step+1);setAttempted(false)}}>Continue to {['','predictions','tools and sources','review'][step+1]}</button>}
    <button className="button primary" onClick={onRun} disabled={busy||errors.length>0}>Compare analyses</button>
    </div>
  </div>
}
