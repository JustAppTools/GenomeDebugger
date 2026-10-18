import { useState } from 'react'

export interface SnpEffCheckView {id:string;status:'agree'|'disagree'|'unresolved';snpeff_version:string;genome_database:string;database_sha256:string;vcf_sha256:string;explanation:string;matches:{transcript_id:string;ensembl_terms:string[];snpeff_terms:string[];agrees:boolean}[];unmatched_ensembl:string[];unmatched_snpeff:string[];execution?:{jar_sha256:string;database_sha256:string;software_version:string;elapsed_seconds:number}|null}

export default function SnpEffPanel({recordId,onCheck}:{recordId:string;onCheck:(value:SnpEffCheckView)=>void}) {
  const [vcf,setVcf] = useState('')
  const [version,setVersion] = useState('')
  const [database,setDatabase] = useState('')
  const [hash,setHash] = useState('')
  const [check,setCheck] = useState<SnpEffCheckView|null>(null)
  const [error,setError] = useState('')
  const [busy,setBusy] = useState(false)
  const [runtime,setRuntime] = useState<{configured:boolean;detail:string;genome?:string;software_version?:string}|null>(null)
  async function localRun(inspect:boolean) {
    setBusy(true);setError('')
    try {
      const response=await fetch(inspect?'/api/tools/snpeff':`/api/sources/ensembl/records/${recordId}/snpeff-run`,inspect?undefined:{method:'POST'})
      const body=await response.json()
      if(!response.ok) throw new Error(typeof body.detail==='string'?body.detail:`Local SnpEff failed (${response.status})`)
      if(inspect)setRuntime(body)
      else {setCheck(body);onCheck(body)}
    } catch(e) {setError(e instanceof Error?e.message:'Local SnpEff failed')}
    finally {setBusy(false)}
  }
  async function request(saved:boolean) {
    setBusy(true);setError('')
    try {
      const response = await fetch(`/api/sources/ensembl/records/${recordId}/snpeff-check`,saved?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vcf_text:vcf,snpeff_version:version,genome_database:database,database_sha256:hash})})
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail==='string'?body.detail:`SnpEff comparison failed (${response.status})`)
      setCheck(body);onCheck(body)
    } catch(e) {setError(e instanceof Error?e.message:'SnpEff comparison failed')}
    finally {setBusy(false)}
  }
  return <section className="panel source-panel"><span className="eyebrow">SECOND ANNOTATION OUTPUT</span><h2>SnpEff ANN comparison</h2><p className="source-caveat">Paste a single-variant SnpEff annotated VCF. Exact transcript IDs and consequence terms are compared with the preserved Ensembl record. This checks an independently generated output only if its declared version and database hash are genuine; the app cannot authenticate them. It does not establish why either engine differs. <a href="https://pcingola.github.io/SnpEff/snpeff/inputoutput/" target="_blank" rel="noreferrer">ANN format</a>.</p>
    <h3>Run the pinned local installation</h3><p>The local runner verifies the installed Java, SnpEff JAR, configuration, and database hashes before and after execution. It makes no downloads or external requests during annotation.</p><div className="source-actions"><button className="button secondary" disabled={busy} onClick={()=>localRun(true)}>Inspect local SnpEff setup</button><button className="button primary" disabled={busy||!runtime?.configured} onClick={()=>localRun(false)}>Run local SnpEff</button></div>{runtime&&<p>{runtime.configured?`${runtime.software_version} · ${runtime.genome}. `:''}{runtime.detail}</p>}
    <div className="source-fields"><label>SnpEff version<input aria-label="SnpEff version" value={version} onChange={e=>setVersion(e.target.value)}/></label><label>Genome database<input aria-label="SnpEff genome database" value={database} onChange={e=>setDatabase(e.target.value)}/></label><label>Database SHA-256<input aria-label="SnpEff database SHA-256" value={hash} onChange={e=>setHash(e.target.value.toLowerCase())}/></label></div>
    <label className="guide-field snpeff-vcf">Annotated VCF<input aria-label="Import annotated VCF" type="file" accept=".vcf,text/plain" onChange={e=>{const file=e.target.files?.[0];if(file&&file.size<=500000)void file.text().then(setVcf);else if(file)setError('VCF exceeds 500 KB');e.target.value=''}}/><textarea aria-label="SnpEff annotated VCF" spellCheck={false} value={vcf} onChange={e=>setVcf(e.target.value)} placeholder="##SnpEffVersion=...&#10;#CHROM ...&#10;1 6524705 . C T . PASS ANN=..."/></label>
    <div className="source-actions"><button className="button secondary" onClick={()=>request(true)} disabled={busy}>Load saved comparison</button><button className="button primary" onClick={()=>request(false)} disabled={busy||!vcf||!version||!database||!(/^[0-9a-f]{64}$/.test(hash))}>Compare SnpEff output</button></div>
    {error&&<div className="source-error" role="alert">{error}</div>}
    {check&&<div className="snpeff-result"><p><strong>{check.status.toUpperCase()}</strong> · {check.explanation}</p><p>{check.matches.length} exact transcript matches; {check.unmatched_ensembl.length} Ensembl-only; {check.unmatched_snpeff.length} SnpEff-only.</p>{check.execution&&<p className="record-hash">Local execution: {check.execution.software_version} · {check.execution.elapsed_seconds}s · JAR SHA-256 {check.execution.jar_sha256} · Database SHA-256 {check.execution.database_sha256}</p>}<code>Check {check.id} · VCF SHA-256 {check.vcf_sha256}</code><div className="table-scroll"><table><thead><tr><th>TRANSCRIPT</th><th>ENSEMBL</th><th>SNPEFF</th><th>AGREES</th></tr></thead><tbody>{check.matches.map(item=><tr key={item.transcript_id}><td className="mono">{item.transcript_id}</td><td>{item.ensembl_terms.join(', ')}</td><td>{item.snpeff_terms.join(', ')}</td><td>{item.agrees?'Yes':'No'}</td></tr>)}</tbody></table></div></div>}
  </section>
}
