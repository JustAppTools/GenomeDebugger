import {useEffect,useRef,useState} from 'react'
import {readUtf8} from './readUtf8'
import type {InvestigationInput} from './types'

interface Preview {input:InvestigationInput;files:{file:string;rows:number;variants:number;original_sha256:string}[];warnings:string[]}
export default function ImportWorkspace({onUse,onSources}:{onUse:(input:InvestigationInput)=>void;onSources:()=>void}) {
  const [files,setFiles]=useState<(File|null)[]>([null,null]),[preview,setPreview]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const revision=useRef(0),live=useRef(true)
  useEffect(()=>{live.current=true;return()=>{live.current=false;revision.current++}},[])
  async function inspect() {
    const token=++revision.current;setBusy(true);setError('');setPreview(null)
    try {
      const pair=await Promise.all(files.map(async(file)=>{
        if(!file)throw new Error('Choose one file for each analysis.')
        if(file.size>600000)throw new Error(`${file.name}: this tabular importer accepts up to 600 KB per file.`)
        if(Array.from(file.name).length>255)throw new Error('Use a tabular filename of at most 255 characters. The original filename is preserved separately from the display label.')
        return {name:file.name,text:await readUtf8(file,true),delimiter:file.name.toLowerCase().endsWith('.tsv')?'\t':','}
      }))
      if(token!==revision.current||!live.current)return
      const response=await fetch('/api/imports/tabular/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:Array.from(`${pair[0].name} compared with ${pair[1].name}`).slice(0,200).join(''),files:pair})})
      const body=await response.json()
      if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:Array.isArray(body.detail)?body.detail.map((item:{loc?:unknown[];msg?:string})=>`${item.loc?.filter(part=>part!=='body').join('.')??'File'}: ${item.msg??'Invalid value'}`).join('; '):'File values do not match the supported tabular format. Check the documented columns and metadata.')
      if(token===revision.current&&live.current)setPreview(body)
    } catch(e){if(token===revision.current&&live.current)setError(e instanceof Error?e.message:'Import preview failed')}
    finally{if(token===revision.current&&live.current)setBusy(false)}
  }
  return <details className="import-workspace" open><summary>Import analysis files</summary><p>Start with existing analysis outputs. Choose the path that matches your files.</p><div className="import-options"><article><h3>GenomeDebugger comparison JSON</h3><p>Use <strong>Import JSON</strong> below for the documented two-analysis input schema. A portable saved bundle is imported from Saved work.</p></article><article><h3>Original VEP or SnpEff output</h3><p>Preserve original VEP JSON with its run metadata, or compare supported SnpEff ANN output against a captured public source.</p><button className="button secondary" onClick={onSources}>Open source import tools</button></article></div><details><summary>Import two annotated CSV/TSV files</summary><p>GenomeDebugger tabular format v1: one annotation per row. Every row must explicitly supply <code>assembly, sequence_id, position, ref, alt, gene_id, transcript_id, consequence, tool, tool_version, source_name, source_release</code>. Positions are one-based. Optional columns: <code>protein_consequence, context_start, reference_sequence</code>. Metadata must agree within each file. This is an explicit export format, not an arbitrary CSV or unannotated VCF importer.</p><div className="readable-pair">{files.map((file,i)=><label className="guide-field" key={i}>Analysis {'AB'[i]} file<input type="file" aria-label={`Analysis ${i+1} tabular file`} accept=".csv,.tsv,text/csv,text/tab-separated-values" onChange={e=>{revision.current++;setBusy(false);setPreview(null);setError('');setFiles(previous=>previous.map((old,j)=>j===i?e.target.files?.[0]??null:old))}}/>{file?.name}</label>)}</div><button className="button secondary" disabled={busy||files.some(f=>!f)} onClick={()=>void inspect()}>{busy?'Reading and validating files…':'Preview imported rows'}</button>{error&&<p role="alert" className="error">{error}</p>}{preview&&<section className="readiness-review"><h3>Import preview — no comparison saved yet</h3>{preview.files.map((file,i)=><article key={i}><h4>{file.file}</h4><p>{file.rows} annotation rows · {file.variants} variants · all rows accepted</p><details><summary>Original file fingerprint</summary><code>{file.original_sha256}</code></details></article>)}<ul>{preview.warnings.map(w=><li key={w}>{w}</li>)}</ul><button className="button primary" onClick={()=>onUse(preview.input)}>Review these two analyses</button></section>}</details></details>
}
