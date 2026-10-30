import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Database, ExternalLink, Globe2 } from 'lucide-react'
import type { Result } from './types'
import SnpEffPanel, {type SnpEffCheckView} from './SnpEffPanel'
import HistoricalPanel from './HistoricalPanel'
import {describeEffect} from './explanations'
import IdentifierLookup from './IdentifierLookup'
import OperationStatus from './OperationStatus'

interface SourceRecord {
  id: string
  query: { chromosome: string; position: number; ref: string; alt: string }
  retrieved_at: string
  source_uri: string
  sequence_uri: string
  release_uri: string
  assembly_uri: string
  releases: number[]
  assembly_name: string
  assembly_accession: string
  source_response_sha256: string
  source_response?: {transcript_consequences?: Record<string,unknown>[]}
  transcripts: { transcript_id: string; gene_id: string; consequence_terms: string[]; protein_consequence?: string | null; biotype?: string | null }[]
}
interface LookupResult { record: SourceRecord; access: 'cache' | 'fetched' | 'cached_after_error'; warning?: string | null }
interface ReferenceCheck {
  id: string; status: 'agree' | 'disagree'; checked_at: string
  assembly_report_uri: string; assembly_report_sha256: string
  refseq_assembly_accession: string; refseq_accession: string
  reference_uri: string; contextual_uri: string; hgvs_uri: string
  expected_reference: string; observed_reference: string
  expected_spdi: string; observed_spdi?: string | null
  expected_hgvs: string; observed_hgvs?: string | null
  reference_matches: boolean; representation_checked: boolean; spdi_matches: boolean; hgvs_matches: boolean
}
interface ReferenceCheckResult { check: ReferenceCheck; access: 'cache' | 'fetched' | 'cached_after_error'; warning?: string | null }

export default function PublicSourcePanel({ onCompare,active=true }: { onCompare: (result: Result) => void;active?:boolean }) {
  const live = useRef(false)
  const activeView=useRef(active);activeView.current=active
  useEffect(()=>{live.current=true;return()=>{live.current=false}},[])
  function acceptComparison(result:Result) {if(live.current&&activeView.current)onCompare(result)}
  const queryRevision = useRef(0)
  const workspaceRevision = useRef(0)
  function workspaceEdited() { workspaceRevision.current++ }
  function getWorkspaceRevision() { return workspaceRevision.current }
  useEffect(()=>{if(!active)workspaceRevision.current++},[active])
  const selectionRevision = useRef(0)
  const activeRecord = useRef<string|null>(null)
  const [comparisonNotice, setComparisonNotice] = useState('')
  const [chromosome, setChromosome] = useState('1')
  const [position, setPosition] = useState('6524705')
  const [ref, setRef] = useState('C')
  const [alt, setAlt] = useState('T')
  const [record, setRecord] = useState<SourceRecord | null>(null)
  const [access, setAccess] = useState('')
  const [warning, setWarning] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [operation,setOperation]=useState('Reading source data')
  const [transcriptA, setTranscriptA] = useState('')
  const [transcriptB, setTranscriptB] = useState('')
  const [check, setCheck] = useState<ReferenceCheck | null>(null)
  const [annotationCheck, setAnnotationCheck] = useState<SnpEffCheckView | null>(null)
  const [checkAccess, setCheckAccess] = useState('')
  const [checkWarning, setCheckWarning] = useState('')
  const [transcriptQuery, setTranscriptQuery] = useState('')
  const query = { chromosome: chromosome.trim().toUpperCase(), position: Number(position), ref: ref.trim().toUpperCase(), alt: alt.trim().toUpperCase() }
  const valid = /^(?:[1-9]|1\d|2[0-2]|X|Y|MT)$/.test(query.chromosome) && Number.isInteger(query.position) && query.position > 0 && /^[ACGT]$/.test(query.ref) && /^[ACGT]$/.test(query.alt) && query.ref !== query.alt
  function transcriptMeta(id:string,gene:string) {const row=record?.source_response?.transcript_consequences?.find(item=>item.transcript_id===id&&item.gene_id===gene);return {symbol:typeof row?.gene_symbol==='string'?row.gene_symbol:'',canonical:row?.canonical===1,mane:typeof row?.mane_select==='string'?row.mane_select:''}}
  const visibleTranscripts = record?.transcripts.filter(row=>`${row.transcript_id} ${row.gene_id} ${transcriptMeta(row.transcript_id,row.gene_id).symbol} ${row.consequence_terms.join(' ')}`.toLowerCase().includes(transcriptQuery.toLowerCase())) ?? []
  const rowA = record?.transcripts.find(row=>row.transcript_id===transcriptA)
  const rowB = record?.transcripts.find(row=>row.transcript_id===transcriptB)

  function change(setter: (s: string) => void, value: string) { queryRevision.current++;activeRecord.current=null; setter(value); setRecord(null); setCheck(null);setAnnotationCheck(null); setError(''); setWarning(''); setCheckWarning('') }
  function useSecondExample() {
    workspaceEdited()
    queryRevision.current++
    activeRecord.current=null
    setChromosome('9'); setPosition('133256042'); setRef('C'); setAlt('A')
    setRecord(null); setCheck(null);setAnnotationCheck(null); setError(''); setWarning(''); setCheckWarning('')
  }

  async function lookup(mode: 'cache_only' | 'fetch') {
    const revision = queryRevision.current
    const workspace = workspaceRevision.current
    setOperation(mode==='fetch'?'Retrieving current Ensembl data and metadata':'Reading the local source cache');setBusy(true); setError(''); setWarning('')
    try {
      const response = await fetch('/api/sources/ensembl/lookup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, mode }) })
      const body = await response.json().catch(() => ({ detail: `Source lookup returned a non-JSON response (${response.status})` }))
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Lookup failed (${response.status})`)
      if (revision !== queryRevision.current) return
      if (workspace !== workspaceRevision.current) {setComparisonNotice('The lookup finished after your source workspace changed. Your newer draft and selections were kept. Load again to use the returned capture.');return}
      const found = body as LookupResult
      const sameCapture = activeRecord.current === found.record.id
      workspaceEdited()
      activeRecord.current=found.record.id
      setRecord(found.record); setAccess(found.access); setWarning(found.warning ?? '')
      if(sameCapture)return
      setCheck(null);setAnnotationCheck(null);setCheckWarning('')
      const first = found.record.transcripts[0]
      const contrasting = found.record.transcripts.find(row => row.gene_id === first?.gene_id && row.consequence_terms.length > 1 && row.consequence_terms.join(';') !== first.consequence_terms.join(';'))
        ?? found.record.transcripts.find(row => row.gene_id === first?.gene_id && row.consequence_terms.join(';') !== first.consequence_terms.join(';'))
      setTranscriptA(first?.transcript_id ?? '')
      setTranscriptB((contrasting ?? found.record.transcripts[1])?.transcript_id ?? '')
    } catch (e) { if (revision !== queryRevision.current) return; if(workspace!==workspaceRevision.current){setComparisonNotice('The lookup failed after your source workspace changed. Your newer draft and selections were kept.');return};setError(e instanceof Error ? e.message : 'Lookup failed') }
    finally { setBusy(false) }
  }

  async function referenceCheck(mode: 'cache_only' | 'fetch') {
    const revision = queryRevision.current
    if (!record) return
    setOperation(mode==='fetch'?'Requesting NCBI reference and notation observations':'Reading a saved NCBI observation');setBusy(true); setError(''); setCheckWarning('')
    try {
      const response = await fetch(`/api/sources/ensembl/records/${record.id}/reference-check`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) })
      const body = await response.json().catch(() => ({ detail: `NCBI check returned a non-JSON response (${response.status})` }))
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `NCBI check failed (${response.status})`)
      if (revision !== queryRevision.current) return
      const found = body as ReferenceCheckResult
      workspaceEdited();selectionRevision.current++;setCheck(found.check); setCheckAccess(found.access); setCheckWarning(found.warning ?? '')
    } catch (e) { if (revision !== queryRevision.current) return; setCheck(null); setError(e instanceof Error ? e.message : 'NCBI check failed') }
    finally { setBusy(false) }
  }

  async function compare() {
    const workspace = workspaceRevision.current
    const revision = queryRevision.current
    const selected = selectionRevision.current
    if (!record || !transcriptA || !transcriptB || transcriptA === transcriptB) return
    setOperation('Comparing the selected transcript outputs');setBusy(true); setError(''); setComparisonNotice('')
    try {
      const response = await fetch(`/api/sources/ensembl/records/${record.id}/compare`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ transcript_a: transcriptA, transcript_b: transcriptB, reference_check_id: check?.id??null, annotation_check_id: annotationCheck?.id??null }) })
      const body = await response.json().catch(() => ({ detail: `Comparison returned a non-JSON response (${response.status})` }))
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Comparison failed (${response.status})`)
      if (revision !== queryRevision.current) return
      if (selected !== selectionRevision.current) {setComparisonNotice('Transcript selection or supporting checks changed while comparing. Compare again to use the current selection.');return}
      if (workspace !== workspaceRevision.current) {setComparisonNotice('Source workspace changed while comparing. Your newer draft was kept; the completed comparison is in Saved comparisons.');return}
      acceptComparison(body as Result)
    } catch (e) { if (revision !== queryRevision.current) return; if(selected!==selectionRevision.current){setComparisonNotice('Transcript selection or supporting checks changed while comparing. Compare again to use the current selection.');return};setError(e instanceof Error ? e.message : 'Comparison failed') }
    finally { setBusy(false) }
  }

  return <div className="source-stack" onChangeCapture={workspaceEdited}>
    <OperationStatus active={busy} label={operation}/>
    {comparisonNotice&&<div className="input-notice" role="status">{comparisonNotice}</div>}
    <section className="panel source-panel"><div className="panel-heading"><div><span className="eyebrow">Current public lookup</span><h2>Ensembl VEP · current GRCh38</h2><p>Look up one GRCh38 single-letter substitution, then compare two reported transcript outputs. The filled C→T coordinates are a public documentation example, not your personal result.</p></div><Globe2 size={25}/></div>
      <IdentifierLookup onEdit={workspaceEdited} onSelect={q=>{workspaceEdited();queryRevision.current++;selectionRevision.current++;activeRecord.current=null;setChromosome(q.chromosome);setPosition(String(q.position));setRef(q.ref);setAlt(q.alt);setRecord(null);setCheck(null);setAnnotationCheck(null);setError('');setWarning('');setCheckWarning('');setComparisonNotice('Identifier mapping selected. Review these coordinates and alleles, then Load cached or Fetch current to preserve the source used for comparison.')}}/>
      <div className="source-fields"><label>Chromosome<input aria-label="Chromosome" value={chromosome} onChange={e=>change(setChromosome,e.target.value)}/></label><label>Position, 1-based<input aria-label="Position" type="number" value={position} onChange={e=>change(setPosition,e.target.value)}/></label><label>Reference<input aria-label="Reference allele" maxLength={1} value={ref} onChange={e=>change(setRef,e.target.value)}/></label><label>Alternate<input aria-label="Alternate allele" maxLength={1} value={alt} onChange={e=>change(setAlt,e.target.value)}/></label></div><button className="text-button source-example" onClick={useSecondExample}>Use rs56116432 example with multiple consequence terms <ArrowRight size={13}/></button>
      <p className="source-notice">Fetch current sends only these coordinates and alleles to <b>rest.ensembl.org</b>. Reference base, assembly, release metadata, and VEP results are saved in the local SQLite cache. Load cached makes no external request.</p>
      <div className="source-actions"><button className="button secondary" disabled={!valid||busy} onClick={()=>lookup('cache_only')}><Database size={16}/> Load cached</button><button className="button primary" disabled={!valid||busy} onClick={()=>lookup('fetch')}><Globe2 size={16}/>{busy?'Working…':'Fetch current from Ensembl'}</button></div>
      {error&&<div className="source-error" role="alert">{error}</div>}
    </section>
    {record&&<><section className="panel source-panel"><div className="panel-heading"><div><span className="eyebrow">PRESERVED SOURCE RECORD</span><h2>{record.query.chromosome}:{record.query.position} {record.query.ref}→{record.query.alt}</h2><p>{access === 'fetched' ? 'Fetched and cached' : access === 'cache' ? 'Loaded from local cache' : 'Cached record after live request failed'} · Retrieved {new Date(record.retrieved_at).toLocaleString()}</p></div><span className="count-badge">{record.transcripts.length} transcripts</span></div>
      {warning&&<div className="source-error" role="alert">{warning}</div>}
      <div className="source-meta"><div><span>Reported release</span><strong>{record.releases.join(', ')}</strong></div><div><span>Assembly</span><strong>{record.assembly_name} · {record.assembly_accession}</strong></div><details><summary>Technical fingerprint</summary><code>{record.source_response_sha256}</code></details></div>
      <div className="source-links"><a href={record.source_uri} target="_blank" rel="noreferrer">VEP response <ExternalLink size={13}/></a><a href={record.sequence_uri} target="_blank" rel="noreferrer">Reference base <ExternalLink size={13}/></a><a href={record.release_uri} target="_blank" rel="noreferrer">Release metadata <ExternalLink size={13}/></a></div>
      <p className="source-caveat">Release metadata was queried during retrieval; it is not a historical snapshot of Ensembl. VEP consequences are predictions, not clinical classifications.</p>
      <details className="transcript-browser"><summary>Browse all reported transcripts and exact terms</summary><label className="guide-field source-filter">Find a transcript, gene, or consequence<input aria-label="Filter transcripts" value={transcriptQuery} onChange={e=>setTranscriptQuery(e.target.value)}/></label>
      <div className="table-scroll"><table><thead><tr><th>TRANSCRIPT</th><th>GENE</th><th>CONSEQUENCE TERMS</th><th>BIOTYPE</th><th>SELECT</th></tr></thead><tbody>{visibleTranscripts.map(row=><tr key={row.transcript_id}><td className="mono">{row.transcript_id}</td><td className="mono">{transcriptMeta(row.transcript_id,row.gene_id).symbol&&<strong>{transcriptMeta(row.transcript_id,row.gene_id).symbol}<br/></strong>}{row.gene_id}</td><td>{row.consequence_terms.join(', ')}<small className="effect-help">{describeEffect(row.consequence_terms.join(';'))}</small></td><td>{row.biotype ?? '—'}{transcriptMeta(row.transcript_id,row.gene_id).canonical&&<small className="effect-help">Provider canonical flag</small>}{transcriptMeta(row.transcript_id,row.gene_id).mane&&<small className="effect-help">Reported MANE: {transcriptMeta(row.transcript_id,row.gene_id).mane}</small>}</td><td className="row-select"><button onClick={()=>{workspaceEdited();selectionRevision.current++;setTranscriptA(row.transcript_id)}} aria-label={`Use ${row.transcript_id} as analysis A`} aria-pressed={transcriptA===row.transcript_id}>A</button><button onClick={()=>{workspaceEdited();selectionRevision.current++;setTranscriptB(row.transcript_id)}} aria-label={`Use ${row.transcript_id} as analysis B`} aria-pressed={transcriptB===row.transcript_id}>B</button></td></tr>)}</tbody></table>{visibleTranscripts.length===0&&<div className="empty-row">No transcript matches the filter.</div>}</div></details>
    </section><details className="panel source-panel optional-check" open={!!check}><summary>Optional NCBI reference and notation check</summary><span className="eyebrow">INDEPENDENT ALLELE CHECK</span><h2>NCBI reference and notation</h2><p className="source-caveat">Check with NCBI sends the accession, coordinate, and selected single nucleotide substitution to NCBI EFetch and Variation Services. The accession comes from a pinned GRCh38.p14 assembly report. Load saved check stays offline. This checks the reference allele and SPDI/HGVS representation; it does not validate VEP transcript consequences. Mitochondrial HGVS is outside this check's scope. <a href="https://www.ncbi.nlm.nih.gov/home/about/policies/" target="_blank" rel="noreferrer">NCBI disclaimer and copyright</a>.</p><div className="source-actions"><button className="button secondary" disabled={busy||record.query.chromosome==='MT'} onClick={()=>referenceCheck('cache_only')}><Database size={16}/> Load saved check</button><button className="button primary" disabled={busy||record.query.chromosome==='MT'} onClick={()=>referenceCheck('fetch')}><Globe2 size={16}/> Check with NCBI</button></div>
      {checkWarning&&<div className="source-error" role="alert">{checkWarning}</div>}
      {check&&<div className="reference-result"><div className="reference-title"><span className={`pill ${check.status==='agree'?'pill-verified':'pill-rejected'}`}>{check.status}</span><span>{checkAccess==='cache'?'Loaded from local cache':checkAccess==='fetched'?'Checked and saved':'Previous check after live failure'} · {new Date(check.checked_at).toLocaleString()}</span></div><div className="source-meta"><div><span>Reference base</span><strong>{check.observed_reference} {check.reference_matches?'✓':'≠'} {check.expected_reference}</strong></div><div><span>SPDI</span><code>{check.representation_checked?`${check.observed_spdi ?? 'No result'} ${check.spdi_matches?'✓':'≠'}`:'Skipped after reference mismatch'}</code></div><div><span>HGVS</span><code>{check.representation_checked?`${check.observed_hgvs ?? 'No result'} ${check.hgvs_matches?'✓':'≠'}`:'Skipped after reference mismatch'}</code></div></div><p className="source-caveat">Pinned RefSeq {check.refseq_accession} · Assembly {check.refseq_assembly_accession} · Report SHA-256 <code>{check.assembly_report_sha256}</code></p><div className="source-links"><a href={check.assembly_report_uri} target="_blank" rel="noreferrer">Assembly report <ExternalLink size={13}/></a><a href={check.reference_uri} target="_blank" rel="noreferrer">NCBI reference <ExternalLink size={13}/></a>{check.representation_checked&&<><a href={check.contextual_uri} target="_blank" rel="noreferrer">SPDI response <ExternalLink size={13}/></a><a href={check.hgvs_uri} target="_blank" rel="noreferrer">HGVS response <ExternalLink size={13}/></a></>}</div>{check.status==='disagree'&&<p className="source-error">At least one NCBI observation disagrees with the preserved Ensembl record. Investigate the reference and representation before interpreting the variant.</p>}</div>}
    </details><section className="panel source-panel"><span className="eyebrow">COMPARE CURRENT ANNOTATIONS</span><h2>Choose two transcripts</h2><p>A transcript is one RNA version produced from a gene. These selections compare two predictions from the same preserved response; neither selection is automatically the correct or most relevant one.</p><p className="source-caveat">Both rows come from preserved VEP response <code>{record.id}</code>. {check?<>NCBI check <code>{check.id}</code> is linked in provenance.</>:'No NCBI check is currently linked.'} This compares predictions; it does not verify historical causation.</p><div className="source-compare"><label>Analysis A<select aria-label="Analysis A transcript" value={transcriptA} onChange={e=>{workspaceEdited();selectionRevision.current++;setTranscriptA(e.target.value)}}>{record.transcripts.map(row=><option key={row.transcript_id} value={row.transcript_id}>{row.transcript_id} · {row.consequence_terms.join(', ')}</option>)}</select></label><label>Analysis B<select aria-label="Analysis B transcript" value={transcriptB} onChange={e=>{workspaceEdited();selectionRevision.current++;setTranscriptB(e.target.value)}}>{record.transcripts.map(row=><option key={row.transcript_id} value={row.transcript_id}>{row.transcript_id} · {row.consequence_terms.join(', ')}</option>)}</select></label><button className="button primary" disabled={busy||!transcriptA||!transcriptB||transcriptA===transcriptB} onClick={compare}>Compare <ArrowRight size={16}/></button></div>{rowA&&rowB&&<p className="source-caveat">{rowA.gene_id===rowB.gene_id?'Both transcripts belong to the same reported gene.':'These transcripts belong to different reported genes; interpret differences in that context.'} {transcriptA===transcriptB?'Choose two distinct transcripts.':''}</p>}</section></>}
    {record&&<><p className="source-caveat">{annotationCheck?`Selected SnpEff check: ${annotationCheck.id} (${annotationCheck.status}). This check will be included in the comparison.`:'No SnpEff check is selected for the comparison.'}</p><details className="panel optional-check"><summary>Advanced annotation output: SnpEff</summary><SnpEffPanel key={record.id} recordId={record.id} onCheck={value=>{if(!live.current||activeRecord.current!==record.id)return;workspaceEdited();selectionRevision.current++;setAnnotationCheck(value)}}/></details></>}
    <details className="advanced-sources"><summary>Import original VEP output or compare preserved sources (advanced)</summary><HistoricalPanel onCompare={acceptComparison} getWorkspaceRevision={getWorkspaceRevision} onWorkspaceChange={workspaceEdited}/></details>
  </div>
}
