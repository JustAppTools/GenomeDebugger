import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import PublicSourcePanel from './PublicSourcePanel'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})
const record={id:'record',query:{chromosome:'1',position:6524705,ref:'C',alt:'T'},
  retrieved_at:'2026-10-17T00:00:00Z',source_uri:'https://rest.ensembl.org/example',
  sequence_uri:'https://rest.ensembl.org/sequence',release_uri:'https://rest.ensembl.org/info/data',
  assembly_name:'GRCh38.p14',assembly_accession:'GCA_000001405.29',releases:[116],source_response_sha256:'a'.repeat(64),
  transcripts:[{transcript_id:'T1',gene_id:'G',consequence_terms:['intron_variant']},
    {transcript_id:'T2',gene_id:'G',consequence_terms:['missense_variant']}]}

test.each(['reference','compare'])('query changes invalidate an in-flight %s response',async action=>{
  let release:((response:unknown)=>void)|undefined
  const onCompare=vi.fn()
  const pending=new Promise(resolve=>{release=resolve})
  vi.stubGlobal('fetch',vi.fn().mockImplementation((url:string)=>url.endsWith('/lookup')
    ?Promise.resolve({ok:true,json:async()=>({record,access:'cache'})}):pending))
  render(<PublicSourcePanel onCompare={onCompare}/>)
  fireEvent.click(screen.getByRole('button',{name:'Load cached'}))
  await screen.findByRole('heading',{name:'1:6524705 C→T'})
  fireEvent.click(screen.getByRole('button',{name:action==='reference'?'Load saved check':'Compare'}))
  fireEvent.change(screen.getByLabelText('Position'),{target:{value:'999999'}})
  release!({ok:true,json:async()=>action==='reference'?{check:{id:'old-check'},access:'cache'}:{id:'old-result'}})
  await waitFor(()=>expect(screen.getByRole('button',{name:'Load cached'})).toBeEnabled())
  expect(onCompare).not.toHaveBeenCalled()
  expect(screen.queryByRole('heading',{name:'1:6524705 C→T'})).not.toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
