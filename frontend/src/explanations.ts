import type {Evidence, Result} from './types'

export const fieldNames:Record<string,string> = {assembly:'Reference genome (assembly)',sequence_id:'Sequence accession',position:'Position',ref:'Original DNA letters',alt:'Changed DNA letters',gene_id:'Gene',transcript_id:'Transcript',consequence:'Predicted effect',protein_consequence:'Predicted protein change',source_name:'Source name',source_release:'Source release',tool:'Analysis tool',tool_version:'Tool version',reference_context:'Supplied reference context',configuration:'Analysis settings',input_sha256:'Original input fingerprint',source_uri:'Source location',start:'Start position',sequence:'Reference letters',a:'Analysis A',b:'Analysis B',before:'Analysis A',after:'Analysis B',matches:'Replay matches observations',computed:'Reproduced outputs',observed:'Supplied outputs',held_constant:'Kept the same',meaningful_override:'Comparison priority override'}
export const categoryNames:Record<string,string> = {identity:'DNA identity',representation:'How the change is written',annotation:'Predicted effects',provenance:'Tool and source',configuration:'Analysis settings',clinical:'Clinical assertions',clinical_context:'Assertion context',clinical_metadata:'Assertion dates',variant:'DNA changes'}
export function fieldLabel(key:string) {return fieldNames[key] ?? key.replaceAll('_',' ')}
export function displayValue(value:unknown):string {
  if(value==null)return 'Not provided'
  if(value==='')return 'Empty text'
  if(typeof value==='string'&&!value.trim())return 'Whitespace only'
  if(typeof value==='boolean')return value?'Yes':'No'
  return typeof value==='object'?JSON.stringify(value):String(value)
}
export const effectDescriptions:Record<string,string> = {
  missense_variant:'A predicted change to an amino acid in a protein.',
  intron_variant:'A change within an intron of this transcript.',
  synonymous_variant:'A coding change predicted to keep the same amino acid.',
  stop_gained:'A change predicted to introduce a stop signal in this transcript.',
  stop_lost:'A change predicted to remove a stop signal in this transcript.',
  frameshift_variant:'A change predicted to shift how the coding sequence is read.',
  splice_region_variant:'A change near a transcript splice region.',
  splice_acceptor_variant:'A change at a predicted splice acceptor site.',
  splice_donor_variant:'A change at a predicted splice donor site.',
  '3_prime_UTR_variant':'A change in the noncoding region after this transcript’s protein-coding sequence.',
  '5_prime_UTR_variant':'A change in the noncoding region before this transcript’s protein-coding sequence.',
  upstream_gene_variant:'A change reported upstream of a gene.',
  downstream_gene_variant:'A change reported downstream of a gene.',
  intergenic_variant:'A change reported between annotated genes.',
  non_coding_transcript_variant:'A change within a transcript that does not code for a protein.',
  non_coding_transcript_exon_variant:'A change in an exon of a noncoding transcript.',
}
export function describeEffect(value:string|null|undefined) {
  if(!value)return 'No predicted effect was supplied.'
  return value.split(/[&,;]/).map(term=>effectDescriptions[term.trim()] ?? `Tool term: ${term.trim()}. Consult the producing tool’s definition.`).join(' ')
}
export function evidenceTitle(e:Evidence) {
  if(e.kind==='field_comparison')return `${fieldLabel(String(e.data.field??'Value'))} changed`
  if(e.id==='identity-inputs')return 'DNA change comparison'
  if(e.kind==='controlled_replay')return 'Reproducing the example’s outputs'
  if(e.kind==='external_reference_observation')return 'External reference check'
  if(e.kind==='independent_annotation_output')return 'Independent annotation output'
  return e.description
}
export function comparisonStory(result:Result) {
  const [a,b]=result.input.snapshots
  if(!a||!b)return 'Review the recorded changes and the evidence behind each conclusion.'
  if(isCollectionInput(result.input)){
    const outputs=result.differences.filter(d=>d.category==='annotation'||d.category==='variant')
    if(!outputs.length)return result.differences.length?'No reported annotation rows changed. File or source metadata differs.':'No reported annotation rows changed. Matching outputs alone do not establish correctness.'
    const added=outputs.filter(d=>d.field.endsWith('.presence')&&d.before===null).length
    const removed=outputs.filter(d=>d.field.endsWith('.presence')&&d.after===null).length
    const changed=outputs.filter(d=>!d.field.endsWith('.presence')).length
    return `The imported collections contain ${added} added and ${removed} removed variant or annotation rows, and ${changed} changed output values on matching rows. No preferred transcript was declared by these files; their overview rows do not establish a transcript-selection cause.`
  }
  const effect=result.differences.find(d=>d.field==='consequence')
  const transcript=result.differences.find(d=>d.field==='transcript_id')
  const tools=a.provenance.tool!==b.provenance.tool||a.provenance.tool_version!==b.provenance.tool_version
  if(!result.differences.length)return 'No compared values changed. Matching outputs alone do not establish that either analysis is correct.'
  const parts:string[]=[]
  if(effect)parts.push(`${a.label} reports ${displayValue(effect.before)}; ${b.label} reports ${displayValue(effect.after)}.`)
  if(transcript)parts.push(`The selected transcripts also differ (${displayValue(transcript.before)} and ${displayValue(transcript.after)}).`)
  if(tools)parts.push('The analysis tools or their versions differ too.')
  if(!parts.length)parts.push(`The recorded changes concern ${[...new Set(result.differences.map(d=>categoryNames[d.category]??d.category))].join(', ').toLowerCase()}.`)
  parts.push(result.input.synthetic?'This is a made-up teaching example.':'These are observations about supplied outputs; a difference alone does not establish its cause.')
  return parts.join(' ')
}
export const glossary = [
  ['DNA change (variant)','A difference in DNA letters at a particular location.'],
  ['Assembly','The version of the reference genome used by the analysis. Obtain it from the producing tool or file header; do not guess it.'],
  ['Sequence accession','A versioned identifier for the reference sequence, such as a chromosome. Obtain the exact identifier from the analysis and its reference.'],
  ['Position','The location of the original DNA letters. GenomeDebugger uses one-based positions; confirm the coordinate convention of your source.'],
  ['Reference and alternate','The original reference letters and the changed letters reported by an analysis. They describe a variant, not a gene.'],
  ['Reference context','A stretch of reference DNA around the variant, with its start position. Supplied text supports a local comparison; it is not an independent reference check.'],
  ['Transcript','One RNA version produced from a gene. Different versions can receive different predictions.'],
  ['Predicted effect (consequence)','What an analysis tool predicts a DNA change might affect. A prediction is not a diagnosis.'],
  ['Source version','The release of a database or reference used by an analysis.'],
  ['Provenance','The recorded tool, version, source, settings, and origin of an analysis. Imported declarations are not independently authenticated.'],
  ['Supporting details (evidence)','The saved inputs and comparisons behind a conclusion. They help you check how it was reached.'],
  ['Controlled replay','A repeatable calculation with specified inputs. Replaying a synthetic table only establishes what happens within that example.'],
] as const
import {isCollectionInput} from './comparisonMode'
