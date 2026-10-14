import { useState } from 'react'
import { ArrowRight, Database, ExternalLink, Globe2 } from 'lucide-react'
import type { Result } from './types'

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

export default function PublicSourcePanel({ onCompare }: { onCompare: (result: Result) => void }) {
  const [chromosome, setChromosome] = useState('1')
  const [position, setPosition] = useState('6524705')
  const [ref, setRef] = useState('C')
  const [alt, setAlt] = useState('T')
  const [record, setRecord] = useState<SourceRecord | null>(null)
  const [access, setAccess] = useState('')
  const [warning, setWarning] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [transcriptA, setTranscriptA] = useState('')
  const [transcriptB, setTranscriptB] = useState('')
  const [check, setCheck] = useState<ReferenceCheck | null>(null)
  const [checkAccess, setCheckAccess] = useState('')
  const [checkWarning, setCheckWarning] = useState('')
  const query = { chromosome: chromosome.trim().toUpperCase(), position: Number(position), ref: ref.trim().toUpperCase(), alt: alt.trim().toUpperCase() }
  const valid = /^(?:[1-9]|1\d|2[0-2]|X|Y|MT)$/.test(query.chromosome) && Number.isInteger(query.position) && query.position > 0 && /^[ACGT]$/.test(query.ref) && /^[ACGT]$/.test(query.alt) && query.ref !== query.alt

  function change(setter: (s: string) => void, value: string) { setter(value); setRecord(null); setCheck(null); setError(''); setWarning(''); setCheckWarning('') }
  function useSecondExample() {
    setChromosome('9'); setPosition('133256042'); setRef('C'); setAlt('A')
    setRecord(null); setCheck(null); setError(''); setWarning(''); setCheckWarning('')
  }

  async function lookup(mode: 'cache_only' | 'fetch') {
    setBusy(true); setError(''); setWarning('')
    try {
      const response = await fetch('/api/sources/ensembl/lookup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, mode }) })
      const body = await response.json().catch(() => ({ detail: `Source lookup returned a non-JSON response (${response.status})` }))
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Lookup failed (${response.status})`)
      const found = body as LookupResult
      setRecord(found.record); setAccess(found.access); setWarning(found.warning ?? ''); setCheck(null); setCheckWarning('')
      const first = found.record.transcripts[0]
      const contrasting = found.record.transcripts.find(row => row.gene_id === first?.gene_id && row.consequence_terms.length > 1 && row.consequence_terms.join(';') !== first.consequence_terms.join(';'))
        ?? found.record.transcripts.find(row => row.gene_id === first?.gene_id && row.consequence_terms.join(';') !== first.consequence_terms.join(';'))
      setTranscriptA(first?.transcript_id ?? '')
      setTranscriptB((contrasting ?? found.record.transcripts[1])?.transcript_id ?? '')
    } catch (e) { setRecord(null); setError(e instanceof Error ? e.message : 'Lookup failed') }
    finally { setBusy(false) }
  }

  async function referenceCheck(mode: 'cache_only' | 'fetch') {
    if (!record) return
    setBusy(true); setError(''); setCheckWarning('')
    try {
      const response = await fetch(`/api/sources/ensembl/records/${record.id}/reference-check`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) })
      const body = await response.json().catch(() => ({ detail: `NCBI check returned a non-JSON response (${response.status})` }))
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `NCBI check failed (${response.status})`)
      const found = body as ReferenceCheckResult
      setCheck(found.check); setCheckAccess(found.access); setCheckWarning(found.warning ?? '')
    } catch (e) { setCheck(null); setError(e instanceof Error ? e.message : 'NCBI check failed') }
    finally { setBusy(false) }
  }

  async function compare() {
    if (!record || !transcriptA || !transcriptB || transcriptA === transcriptB) return
    setBusy(true); setError('')
    try {
      const response = await fetch(`/api/sources/ensembl/records/${record.id}/compare`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ transcript_a: transcriptA, transcript_b: transcriptB }) })
      const body = await response.json().catch(() => ({ detail: `Comparison returned a non-JSON response (${response.status})` }))
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Comparison failed (${response.status})`)
      onCompare(body as Result)
    } catch (e) { setError(e instanceof Error ? e.message : 'Comparison failed') }
    finally { setBusy(false) }
  }

  return <div className="source-stack">
    <section className="panel source-panel"><div className="panel-heading"><div><span className="eyebrow">PUBLIC DATA ADAPTER</span><h2>Ensembl VEP · current GRCh38</h2><p>Inspect transcript consequences for one single nucleotide variant. The default C→T example is from the Ensembl VEP API documentation.</p></div><Globe2 size={25}/></div>
      <div className="source-fields"><label>Chromosome<input aria-label="Chromosome" value={chromosome} onChange={e=>change(setChromosome,e.target.value)}/></label><label>Position, 1-based<input aria-label="Position" type="number" value={position} onChange={e=>change(setPosition,e.target.value)}/></label><label>Reference<input aria-label="Reference allele" maxLength={1} value={ref} onChange={e=>change(setRef,e.target.value)}/></label><label>Alternate<input aria-label="Alternate allele" maxLength={1} value={alt} onChange={e=>change(setAlt,e.target.value)}/></label></div><button className="text-button source-example" onClick={useSecondExample}>Use rs56116432 example with multiple consequence terms <ArrowRight size={13}/></button>
      <p className="source-notice">Fetch current sends only these coordinates and alleles to <b>rest.ensembl.org</b>. Reference base, assembly, release metadata, and VEP results are saved in the local SQLite cache. Load cached makes no external request.</p>
      <div className="source-actions"><button className="button secondary" disabled={!valid||busy} onClick={()=>lookup('cache_only')}><Database size={16}/> Load cached</button><button className="button primary" disabled={!valid||busy} onClick={()=>lookup('fetch')}><Globe2 size={16}/>{busy?'Working…':'Fetch current from Ensembl'}</button></div>
      {error&&<div className="source-error" role="alert">{error}</div>}
    </section>
    {record&&<><section className="panel source-panel"><div className="panel-heading"><div><span className="eyebrow">PRESERVED SOURCE RECORD</span><h2>{record.query.chromosome}:{record.query.position} {record.query.ref}→{record.query.alt}</h2><p>{access === 'fetched' ? 'Fetched and cached' : access === 'cache' ? 'Loaded from local cache' : 'Cached record after live request failed'} · Retrieved {new Date(record.retrieved_at).toLocaleString()}</p></div><span className="count-badge">{record.transcripts.length} transcripts</span></div>
      {warning&&<div className="source-error" role="alert">{warning}</div>}
      <div className="source-meta"><div><span>Reported release</span><strong>{record.releases.join(', ')}</strong></div><div><span>Assembly</span><strong>{record.assembly_name} · {record.assembly_accession}</strong></div><div><span>Record SHA-256</span><code>{record.source_response_sha256}</code></div></div>
      <div className="source-links"><a href={record.source_uri} target="_blank" rel="noreferrer">VEP response <ExternalLink size={13}/></a><a href={record.sequence_uri} target="_blank" rel="noreferrer">Reference base <ExternalLink size={13}/></a><a href={record.release_uri} target="_blank" rel="noreferrer">Release metadata <ExternalLink size={13}/></a></div>
      <p className="source-caveat">Release metadata was queried during retrieval; it is not a historical snapshot of Ensembl. VEP consequences are predictions, not clinical classifications.</p>
      <div className="table-scroll"><table><thead><tr><th>TRANSCRIPT</th><th>GENE</th><th>CONSEQUENCE TERMS</th><th>BIOTYPE</th></tr></thead><tbody>{record.transcripts.map(row=><tr key={row.transcript_id}><td className="mono">{row.transcript_id}</td><td className="mono">{row.gene_id}</td><td>{row.consequence_terms.join(', ')}</td><td>{row.biotype ?? '—'}</td></tr>)}</tbody></table></div>
    </section><section className="panel source-panel"><span className="eyebrow">INDEPENDENT ALLELE CHECK</span><h2>NCBI reference and notation</h2><p className="source-caveat">Check with NCBI sends the accession, coordinate, and selected single nucleotide substitution to NCBI EFetch and Variation Services. The accession comes from a pinned GRCh38.p14 assembly report. Load saved check stays offline. This checks the reference allele and SPDI/HGVS representation; it does not validate VEP transcript consequences. Mitochondrial HGVS is outside this check's scope. <a href="https://www.ncbi.nlm.nih.gov/home/about/policies/" target="_blank" rel="noreferrer">NCBI disclaimer and copyright</a>.</p><div className="source-actions"><button className="button secondary" disabled={busy||record.query.chromosome==='MT'} onClick={()=>referenceCheck('cache_only')}><Database size={16}/> Load saved check</button><button className="button primary" disabled={busy||record.query.chromosome==='MT'} onClick={()=>referenceCheck('fetch')}><Globe2 size={16}/> Check with NCBI</button></div>
      {checkWarning&&<div className="source-error" role="alert">{checkWarning}</div>}
      {check&&<div className="reference-result"><div className="reference-title"><span className={`pill ${check.status==='agree'?'pill-verified':'pill-rejected'}`}>{check.status}</span><span>{checkAccess==='cache'?'Loaded from local cache':checkAccess==='fetched'?'Checked and saved':'Previous check after live failure'} · {new Date(check.checked_at).toLocaleString()}</span></div><div className="source-meta"><div><span>Reference base</span><strong>{check.observed_reference} {check.reference_matches?'✓':'≠'} {check.expected_reference}</strong></div><div><span>SPDI</span><code>{check.representation_checked?`${check.observed_spdi ?? 'No result'} ${check.spdi_matches?'✓':'≠'}`:'Skipped after reference mismatch'}</code></div><div><span>HGVS</span><code>{check.representation_checked?`${check.observed_hgvs ?? 'No result'} ${check.hgvs_matches?'✓':'≠'}`:'Skipped after reference mismatch'}</code></div></div><p className="source-caveat">Pinned RefSeq {check.refseq_accession} · Assembly {check.refseq_assembly_accession} · Report SHA-256 <code>{check.assembly_report_sha256}</code></p><div className="source-links"><a href={check.assembly_report_uri} target="_blank" rel="noreferrer">Assembly report <ExternalLink size={13}/></a><a href={check.reference_uri} target="_blank" rel="noreferrer">NCBI reference <ExternalLink size={13}/></a>{check.representation_checked&&<><a href={check.contextual_uri} target="_blank" rel="noreferrer">SPDI response <ExternalLink size={13}/></a><a href={check.hgvs_uri} target="_blank" rel="noreferrer">HGVS response <ExternalLink size={13}/></a></>}</div>{check.status==='disagree'&&<p className="source-error">At least one NCBI observation disagrees with the preserved Ensembl record. Investigate the reference and representation before interpreting the variant.</p>}</div>}
    </section><section className="panel source-panel"><span className="eyebrow">COMPARE CURRENT ANNOTATIONS</span><h2>Choose two transcripts</h2><p className="source-caveat">Both rows come from this one preserved VEP response. The comparison can show their differences; it does not reconstruct a historical pipeline change or verify causation. The latest saved NCBI check ID is linked in comparison provenance when available.</p><div className="source-compare"><label>Analysis A<select aria-label="Analysis A transcript" value={transcriptA} onChange={e=>setTranscriptA(e.target.value)}>{record.transcripts.map(row=><option key={row.transcript_id} value={row.transcript_id}>{row.transcript_id} · {row.consequence_terms.join(', ')}</option>)}</select></label><label>Analysis B<select aria-label="Analysis B transcript" value={transcriptB} onChange={e=>setTranscriptB(e.target.value)}>{record.transcripts.map(row=><option key={row.transcript_id} value={row.transcript_id}>{row.transcript_id} · {row.consequence_terms.join(', ')}</option>)}</select></label><button className="button primary" disabled={busy||!transcriptA||!transcriptB||transcriptA===transcriptB} onClick={compare}>Compare <ArrowRight size={16}/></button></div></section></>}
  </div>
}
