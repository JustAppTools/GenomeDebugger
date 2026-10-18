import type { InvestigationInput, Snapshot } from './types'

function blankSnapshot(id: string): Snapshot {
  return {id, label:`Analysis ${id}`, variant:{assembly:'GRCh38',sequence_id:'NC_000001.11',position:1,ref:'A',alt:'T'},
    annotation:{gene_id:'',transcript_id:'',consequence:''},
    provenance:{tool:'',tool_version:'',source_name:'',source_release:'',configuration:{}}}
}
export function blankInput(): InvestigationInput {
  return {title:'',synthetic:false,snapshots:[blankSnapshot('A'),blankSnapshot('B')]}
}

export function validateGuidedInput(input: InvestigationInput | null): string[] {
  if (!input || typeof input.title !== 'string' || !Array.isArray(input.snapshots) || input.snapshots.length !== 2 ||
      input.snapshots.some(snapshot => !snapshot?.variant || !snapshot.annotation || !snapshot.provenance ||
        typeof snapshot.variant.ref !== 'string' || typeof snapshot.variant.alt !== 'string' ||
        typeof snapshot.annotation.gene_id !== 'string' || typeof snapshot.annotation.transcript_id !== 'string' ||
        typeof snapshot.annotation.consequence !== 'string' || typeof snapshot.provenance.tool !== 'string' ||
        typeof snapshot.provenance.tool_version !== 'string' || typeof snapshot.provenance.source_name !== 'string' ||
        typeof snapshot.provenance.source_release !== 'string' || typeof snapshot.label !== 'string' ||
        typeof snapshot.variant.assembly !== 'string' || typeof snapshot.variant.sequence_id !== 'string')) {
    return ['Two complete analysis snapshots are required']
  }
  return [!input.title.trim() && 'Title is required',
    ...input.snapshots.flatMap((snapshot,index) => {
      const variant = snapshot.variant
      const context = variant.reference_context
      const offset = context ? variant.position-context.start : -1
      return [
        !snapshot.label.trim() && `Analysis ${index+1}: label is required`,
        !variant.assembly.trim() && `Analysis ${index+1}: assembly is required`,
        !variant.sequence_id.trim() && `Analysis ${index+1}: sequence accession is required`,
        !snapshot.annotation.gene_id.trim() && `Analysis ${index+1}: gene ID is required`,
        !snapshot.annotation.transcript_id.trim() && `Analysis ${index+1}: transcript ID is required`,
        !snapshot.annotation.consequence.trim() && `Analysis ${index+1}: consequence is required`,
        !snapshot.provenance.tool.trim() && `Analysis ${index+1}: tool is required`,
        !snapshot.provenance.tool_version.trim() && `Analysis ${index+1}: tool version is required`,
        !snapshot.provenance.source_name.trim() && `Analysis ${index+1}: source is required`,
        !snapshot.provenance.source_release.trim() && `Analysis ${index+1}: source release is required`,
        (!Number.isInteger(variant.position) || variant.position < 1) && `Analysis ${index+1}: position must be positive`,
        (!/^[ACGT]+$/.test(variant.ref) || !/^[ACGT]+$/.test(variant.alt)) && `Analysis ${index+1}: alleles must use A/C/G/T`,
        variant.ref === variant.alt && `Analysis ${index+1}: reference and alternate must differ`,
        context && (!Number.isInteger(context.start) || context.start < 1) && `Analysis ${index+1}: context start must be positive`,
        context && (!/^[ACGT]+$/.test(context.sequence) || context.sequence.length > 10000) && `Analysis ${index+1}: context needs an A/C/G/T sequence`,
        context && context.sequence && (offset < 0 || offset+variant.ref.length > context.sequence.length || context.sequence.slice(offset,offset+variant.ref.length)!==variant.ref) && `Analysis ${index+1}: reference allele must match the sequence at its position`,
      ]
    })].filter(Boolean) as string[]
}

export default function GuidedInput({value,onChange,onRun,busy}:{value:InvestigationInput|null;onChange:(value:InvestigationInput)=>void;onRun:()=>void;busy:boolean}) {
  const input = validateGuidedInput(value)[0] === 'Two complete analysis snapshots are required' ? blankInput() : value!
  function edit(change:(next:InvestigationInput)=>void) {
    const next = JSON.parse(JSON.stringify(input)) as InvestigationInput
    change(next); onChange(next)
  }
  function field(index:number,group:'variant'|'annotation'|'provenance',name:string,value:string) {
    edit(next => {
      const target = next.snapshots[index]
      if (group === 'variant') {
        if (name === 'position') target.variant.position = Number(value)
        else (target.variant as unknown as Record<string,unknown>)[name] = value
      } else (target[group] as unknown as Record<string,unknown>)[name] = value
    })
  }
  function context(index:number,key:'start'|'sequence',value:string) {
    edit(next => {
      const variant = next.snapshots[index].variant
      variant.reference_context ??= {start:variant.position,sequence:''}
      if (key === 'start') variant.reference_context.start = Number(value)
      else variant.reference_context.sequence = value.toUpperCase()
    })
  }
  const errors = validateGuidedInput(input)
  return <div className="guided-input">
    <div className="guided-intro"><h3>Build a comparison</h3><p>Enter two primary analysis outputs. Reference context is optional; without it, allele identity remains unresolved. Use JSON mode for additional variants, annotation rows, and advanced evidence.</p></div>
    <label className="guide-field">Investigation title<input aria-label="Investigation title" value={input.title} onChange={e=>edit(next=>{next.title=e.target.value})}/></label>
    <div className="guide-grid">{input.snapshots.map((snapshot,index)=><section key={index} className="guide-card">
      <h3>Analysis {index===0?'A':'B'}</h3>
      <label className="guide-field">Label<input aria-label={`Analysis ${index+1} label`} value={snapshot.label} onChange={e=>edit(next=>{next.snapshots[index].label=e.target.value})}/></label>
      <div className="guide-pair"><label className="guide-field">Assembly<input aria-label={`Analysis ${index+1} assembly`} value={snapshot.variant.assembly} onChange={e=>field(index,'variant','assembly',e.target.value)}/></label><label className="guide-field">Sequence accession<input aria-label={`Analysis ${index+1} sequence accession`} value={snapshot.variant.sequence_id} onChange={e=>field(index,'variant','sequence_id',e.target.value)}/></label></div>
      <div className="guide-triplet"><label className="guide-field">Position<input aria-label={`Analysis ${index+1} position`} type="number" min="1" value={snapshot.variant.position} onChange={e=>field(index,'variant','position',e.target.value)}/></label><label className="guide-field">Reference<input aria-label={`Analysis ${index+1} reference`} value={snapshot.variant.ref} onChange={e=>field(index,'variant','ref',e.target.value.toUpperCase())}/></label><label className="guide-field">Alternate<input aria-label={`Analysis ${index+1} alternate`} value={snapshot.variant.alt} onChange={e=>field(index,'variant','alt',e.target.value.toUpperCase())}/></label></div>
      <div className="guide-pair"><label className="guide-field">Context start<input aria-label={`Analysis ${index+1} context start`} type="number" min="1" value={snapshot.variant.reference_context?.start ?? ''} onChange={e=>context(index,'start',e.target.value)}/></label><label className="guide-field">Reference sequence<input aria-label={`Analysis ${index+1} reference sequence`} value={snapshot.variant.reference_context?.sequence ?? ''} onChange={e=>context(index,'sequence',e.target.value)}/></label></div>
      <div className="guide-pair"><label className="guide-field">Gene ID<input aria-label={`Analysis ${index+1} gene ID`} value={snapshot.annotation.gene_id} onChange={e=>field(index,'annotation','gene_id',e.target.value)}/></label><label className="guide-field">Transcript ID<input aria-label={`Analysis ${index+1} transcript ID`} value={snapshot.annotation.transcript_id} onChange={e=>field(index,'annotation','transcript_id',e.target.value)}/></label></div>
      <div className="guide-pair"><label className="guide-field">Consequence<input aria-label={`Analysis ${index+1} consequence`} value={snapshot.annotation.consequence} onChange={e=>field(index,'annotation','consequence',e.target.value)}/></label><label className="guide-field">Protein consequence<input aria-label={`Analysis ${index+1} protein consequence`} value={snapshot.annotation.protein_consequence ?? ''} onChange={e=>field(index,'annotation','protein_consequence',e.target.value)}/></label></div>
      <div className="guide-pair"><label className="guide-field">Tool<input aria-label={`Analysis ${index+1} tool`} value={snapshot.provenance.tool} onChange={e=>field(index,'provenance','tool',e.target.value)}/></label><label className="guide-field">Tool version<input aria-label={`Analysis ${index+1} tool version`} value={snapshot.provenance.tool_version} onChange={e=>field(index,'provenance','tool_version',e.target.value)}/></label></div>
      <div className="guide-pair"><label className="guide-field">Source<input aria-label={`Analysis ${index+1} source`} value={snapshot.provenance.source_name} onChange={e=>field(index,'provenance','source_name',e.target.value)}/></label><label className="guide-field">Source release<input aria-label={`Analysis ${index+1} source release`} value={snapshot.provenance.source_release} onChange={e=>field(index,'provenance','source_release',e.target.value)}/></label></div>
    </section>)}</div>
    {errors.length > 0 && <div className="guide-errors" role="status">Complete these fields before comparing: {errors.join('; ')}.</div>}
    <button className="button primary" onClick={onRun} disabled={busy||errors.length>0}>Compare analyses</button>
  </div>
}
