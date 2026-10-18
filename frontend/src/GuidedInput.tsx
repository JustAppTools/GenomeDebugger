import type { Annotation, InvestigationInput, Snapshot, Variant } from './types'

const blankAnnotation = (): Annotation => ({gene_id:'', transcript_id:'', consequence:''})
const blankVariant = (): Variant => ({assembly:'GRCh38', sequence_id:'NC_000001.11', position:1, ref:'A', alt:'T'})
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
    else if (value.length > max) errors.push(`${path} exceeds ${max} characters`)
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

function VariantFields({value,prefix,onChange}:{value:Variant;prefix:string;onChange:(value:Variant)=>void}) {
  const setContext = (key:'start'|'sequence',text:string) => onChange({...value,reference_context:{
    start:value.reference_context?.start ?? value.position, sequence:value.reference_context?.sequence ?? '',
    [key]:key==='start'?Number(text):text.toUpperCase(),
  }})
  return <>
    <div className="guide-pair">{(['assembly','sequence_id'] as const).map((key,i)=><label className="guide-field" key={key}>{i?'Sequence accession':'Assembly'}<input aria-label={`${prefix} ${i?'sequence accession':'assembly'}`} value={value[key]} onChange={e=>onChange({...value,[key]:e.target.value})}/></label>)}</div>
    <div className="guide-triplet"><label className="guide-field">Position<input aria-label={`${prefix} position`} type="number" min="1" value={value.position} onChange={e=>onChange({...value,position:Number(e.target.value)})}/></label>{(['ref','alt'] as const).map((key,i)=><label className="guide-field" key={key}>{i?'Alternate':'Reference'}<input aria-label={`${prefix} ${i?'alternate':'reference'}`} value={value[key]} onChange={e=>onChange({...value,[key]:e.target.value.toUpperCase()})}/></label>)}</div>
    <div className="guide-pair"><label className="guide-field">Context start<input aria-label={`${prefix} context start`} type="number" min="1" value={value.reference_context?.start ?? ''} onChange={e=>setContext('start',e.target.value)}/></label><label className="guide-field">Reference sequence<input aria-label={`${prefix} reference sequence`} value={value.reference_context?.sequence ?? ''} onChange={e=>setContext('sequence',e.target.value)}/></label></div>
    {value.reference_context&&<button className="text-button" onClick={()=>onChange({...value,reference_context:null})}>Remove reference context for {prefix}</button>}
  </>
}

function AnnotationFields({value,prefix,onChange}:{value:Annotation;prefix:string;onChange:(value:Annotation)=>void}) {
  return <div className="guide-pair">{([
    ['gene_id','Gene ID'],['transcript_id','Transcript ID'],['consequence','Consequence'],['protein_consequence','Protein consequence'],
  ] as const).map(([key,label])=><label className="guide-field" key={key}>{label}<input aria-label={`${prefix} ${label.toLowerCase()}`} value={value[key] ?? ''} onChange={e=>onChange({...value,[key]:e.target.value})}/></label>)}</div>
}

export default function GuidedInput({value,onChange,onRun,busy}:{value:unknown;onChange:(value:InvestigationInput)=>void;onRun:()=>void;busy:boolean}) {
  const normalized = normalizeGuidedInput(value)
  const input = normalized === null ? blankInput() : isGuidedInput(normalized) ? normalized : null
  if (!input) return <div className="guide-errors" role="alert">This input has invalid field types. Repair them in JSON mode: {validateGuidedInput(value).join('; ')}.</div>
  function edit(change:(next:InvestigationInput)=>void) {
    const next = JSON.parse(JSON.stringify(input)) as InvestigationInput
    change(next);onChange(next)
  }
  const errors = validateGuidedInput(input)
  return <div className="guided-input">
    <div className="guided-intro"><h3>Build a comparison</h3><p>Add variants and annotation rows to each analysis. Reference context is optional; without it, allele identity remains unresolved. Advanced evidence and clinical assertion fields are available in JSON mode.</p></div>
    <label className="guide-field">Investigation title<input aria-label="Investigation title" value={input.title} onChange={e=>edit(next=>{next.title=e.target.value})}/></label>
    <div className="guide-grid">{input.snapshots.map((snapshot,index)=>{
      const prefix = `Analysis ${index+1}`
      const side = index===0?'A':'B'
      return <section key={index} className="guide-card">
        <h3>Analysis {side}</h3>
        <label className="guide-field">Label<input aria-label={`${prefix} label`} value={snapshot.label} onChange={e=>edit(next=>{next.snapshots[index].label=e.target.value})}/></label>
        <VariantFields value={snapshot.variant} prefix={prefix} onChange={value=>edit(next=>{next.snapshots[index].variant=value})}/>
        <AnnotationFields value={snapshot.annotation} prefix={prefix} onChange={value=>edit(next=>{next.snapshots[index].annotation=value})}/>
        {(snapshot.annotations ?? []).map((row,rowIndex)=><div className="guide-extra" key={rowIndex}><h4>Primary variant annotation {rowIndex+2}</h4><AnnotationFields value={row} prefix={`${prefix} additional annotation ${rowIndex+1}`} onChange={value=>edit(next=>{next.snapshots[index].annotations![rowIndex]=value})}/><button className="text-button" onClick={()=>edit(next=>{next.snapshots[index].annotations!.splice(rowIndex,1)})}>Remove annotation {rowIndex+2} from analysis {side}</button></div>)}
        <button className="button secondary" disabled={(snapshot.annotations?.length ?? 0)>=1000} onClick={()=>edit(next=>{(next.snapshots[index].annotations ??= []).push(blankAnnotation())})}>Add annotation to analysis {side}</button>
        {(snapshot.variant_records ?? []).map((record,recordIndex)=><div className="guide-extra" key={recordIndex}><h4>Variant {recordIndex+2}</h4>
          <VariantFields value={record.variant} prefix={`${prefix} variant ${recordIndex+2}`} onChange={value=>edit(next=>{next.snapshots[index].variant_records![recordIndex].variant=value})}/>
          {record.annotations.map((row,rowIndex)=><div key={rowIndex}><AnnotationFields value={row} prefix={`${prefix} variant ${recordIndex+2} annotation ${rowIndex+1}`} onChange={value=>edit(next=>{next.snapshots[index].variant_records![recordIndex].annotations[rowIndex]=value})}/>{record.annotations.length>1&&<button className="text-button" onClick={()=>edit(next=>{next.snapshots[index].variant_records![recordIndex].annotations.splice(rowIndex,1)})}>Remove annotation {rowIndex+1} from analysis {side} variant {recordIndex+2}</button>}</div>)}
          <button className="button secondary" disabled={record.annotations.length>=100} onClick={()=>edit(next=>{next.snapshots[index].variant_records![recordIndex].annotations.push(blankAnnotation())})}>Add annotation to analysis {side} variant {recordIndex+2}</button>
          <button className="text-button" onClick={()=>edit(next=>{next.snapshots[index].variant_records!.splice(recordIndex,1)})}>Remove variant {recordIndex+2} from analysis {side}</button>
        </div>)}
        <button className="button secondary" disabled={(snapshot.variant_records?.length ?? 0)>=50} onClick={()=>edit(next=>{(next.snapshots[index].variant_records ??= []).push({variant:{...blankVariant(),assembly:snapshot.variant.assembly,sequence_id:snapshot.variant.sequence_id,position:snapshot.variant.position+1},annotations:[blankAnnotation()]})})}>Add variant to analysis {side}</button>
        <h4>Analysis provenance</h4><div className="guide-pair">{(['tool','tool_version','source_name','source_release'] as const).map(key=><label className="guide-field" key={key}>{key.replaceAll('_',' ')}<input aria-label={`${prefix} ${key.replaceAll('_',' ')}`} value={snapshot.provenance[key]} onChange={e=>edit(next=>{next.snapshots[index].provenance[key]=e.target.value})}/></label>)}</div>
      </section>
    })}</div>
    {errors.length>0&&<div className="guide-errors" role="status">Complete these fields before comparing: {errors.slice(0,12).join('; ')}{errors.length>12?`; ${errors.length-12} more fields need attention`:''}.</div>}
    <button className="button primary" onClick={onRun} disabled={busy||errors.length>0}>Compare analyses</button>
  </div>
}
