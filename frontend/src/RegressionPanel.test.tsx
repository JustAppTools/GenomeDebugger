import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import RegressionPanel from './RegressionPanel'
import type { Result } from './types'

afterEach(() => {cleanup();vi.unstubAllGlobals()})

test('saves a case, passes pinned replay, then shows a candidate failure', async () => {
  const input = {title:'Synthetic case',synthetic:true,snapshots:[
    {id:'A',label:'A',variant:{assembly:'GRCh38',sequence_id:'NC_1',position:1,ref:'A',alt:'T'},annotation:{gene_id:'G',transcript_id:'TX1',consequence:'missense_variant'},provenance:{tool:'fixture',tool_version:'1',source_name:'fixture',source_release:'1',configuration:{}}},
    {id:'B',label:'B',variant:{assembly:'GRCh38',sequence_id:'NC_1',position:1,ref:'A',alt:'T'},annotation:{gene_id:'G',transcript_id:'TX2',consequence:'intron_variant'},provenance:{tool:'fixture',tool_version:'1',source_name:'fixture',source_release:'1',configuration:{}}}
  ]}
  const result = {id:'investigation1',input,identity:{status:'verified',explanation:'match',evidence_ids:[]},differences:[],findings:[],evidence:[],input_sha256:'baselinehash'} as Result
  const regressionCase = {id:'case1',name:'Regression: Synthetic case',schema_version:1,created_at:'2026-10-11T00:00:00Z',source_investigation:result}
  const passed = {id:'run1',case_id:'case1',created_at:'2026-10-11T00:00:00Z',mode:'pinned',status:'passed',baseline_input_sha256:'baselinehash',candidate_input_sha256:'baselinehash',checks:[{path:'identity.status',expected:'verified',actual:'verified',passed:true,required:true}],input_changes:[],actual:result}
  const failed = {id:'run2',case_id:'case1',created_at:'2026-10-11T00:01:00Z',mode:'candidate',status:'failed',baseline_input_sha256:'baselinehash',candidate_input_sha256:'candidatehash',checks:[{path:'snapshots[1].annotation.consequence',expected:'intron_variant',actual:'synonymous_variant',passed:false,required:true}],input_changes:['snapshots[1].annotation.consequence'],actual:result}
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ok:true,json:async()=>[]})
    .mockResolvedValueOnce({ok:true,json:async()=>regressionCase})
    .mockResolvedValueOnce({ok:true,json:async()=>passed})
    .mockResolvedValueOnce({ok:true,json:async()=>failed})
  vi.stubGlobal('fetch',fetchMock)
  render(<RegressionPanel result={result}/>)
  await waitFor(()=>expect(screen.getByRole('button',{name:'Save regression case'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'Save regression case'}))
  expect(await screen.findByText('SAVED CASE')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Run pinned baseline'}))
  expect(await screen.findByText('Regression passed')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Candidate analysis 2 consequence'), {target:{value:'synonymous_variant'}})
  fireEvent.click(screen.getByRole('button',{name:'Check candidate'}))
  expect(await screen.findByText('Regression failed')).toBeInTheDocument()
  expect(screen.getAllByText('snapshots[1].annotation.consequence').length).toBeGreaterThan(0)
  expect(fetchMock).toHaveBeenCalledTimes(4)
  expect(fetchMock.mock.calls[0][0]).toBe('/api/regression-cases?source_investigation_id=investigation1')
})

test.each([{label:'ASCII',title:'A'.repeat(200)},{label:'Unicode',title:'🧬'.repeat(200)}])('bounds the default $label name without splitting characters', async ({title}) => {
  const result = {id:'long-title',input:{title,synthetic:true,snapshots:[]},input_sha256:'hash'} as unknown as Result
  const fetchMock=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>[]})
    .mockResolvedValueOnce({ok:false,status:422,json:async()=>({detail:[{loc:['body','name'],msg:'Specific name validation error'}]})})
  vi.stubGlobal('fetch',fetchMock)
  render(<RegressionPanel result={result}/> )
  const name=screen.getByLabelText('Test name') as HTMLInputElement
  expect(Array.from(name.value)).toHaveLength(200)
  expect(name.value).toBe(Array.from(`Regression: ${title}`).slice(0,200).join(''))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Save regression case'})).toBeEnabled())
  fireEvent.click(screen.getByRole('button',{name:'Save regression case'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('name: Specific name validation error')
  expect(JSON.parse(fetchMock.mock.calls[1][1].body).name).toBe(name.value)
  fireEvent.change(name,{target:{value:' '.repeat(10)}})
  expect(screen.getByRole('button',{name:'Save regression case'})).toBeDisabled()
  fireEvent.change(name,{target:{value:'A'.repeat(201)}})
  expect(screen.getByRole('button',{name:'Save regression case'})).toBeDisabled()
})

test('older history uses a stable run anchor and deduplicates overlapping responses',async()=>{
  const result={id:'investigation',input:{title:'History',snapshots:[]},identity:{status:'verified'},differences:[],findings:[],input_sha256:'hash'} as unknown as Result
  const regressionCase={id:'case',name:'History',source_investigation:result}
  const row=(i:number)=>({id:`run-${i}`,mode:'pinned',status:'passed',created_at:'2026-10-20T00:00:00Z'})
  const fetchMock=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>[{id:'case',source_investigation_id:'investigation'}]})
    .mockResolvedValueOnce({ok:true,json:async()=>regressionCase})
    .mockResolvedValueOnce({ok:true,json:async()=>Array.from({length:100},(_,i)=>row(100-i))})
    .mockResolvedValueOnce({ok:true,json:async()=>[row(1),row(0)]})
  vi.stubGlobal('fetch',fetchMock)
  render(<RegressionPanel result={result}/>)
  fireEvent.click(await screen.findByRole('button',{name:'Load older runs'}))
  await screen.findByText('run-0')
  expect(fetchMock).toHaveBeenLastCalledWith('/api/regression-cases/case/runs?before=run-1&limit=100')
  expect(document.querySelectorAll('.history-list button')).toHaveLength(101)
  expect(screen.getAllByText('run-1')).toHaveLength(1)
})

test('every baseline remains selectable beyond the first discovery page',async()=>{
  const result={id:'investigation',input:{title:'History',snapshots:[]},identity:{status:'verified'},differences:[],findings:[],input_sha256:'hash'} as unknown as Result
  const fetchMock=vi.fn().mockImplementation(async(url:string)=>{
    if(url.includes('?source_investigation_id='))return {ok:true,json:async()=>url.includes('offset=100')
      ?[{id:'oldest',name:'Oldest baseline',source_investigation_id:result.id}]
      :Array.from({length:100},(_,i)=>({id:`case-${i}`,name:`Baseline ${i}`,source_investigation_id:result.id}))}
    if(url.endsWith('/runs'))return {ok:true,json:async()=>[]}
    const id=url.split('/').at(-1)!
    return {ok:true,json:async()=>({id,name:id==='oldest'?'Oldest baseline':id,source_investigation:result})}
  })
  vi.stubGlobal('fetch',fetchMock)
  render(<RegressionPanel result={result}/>)
  await waitFor(()=>expect(screen.getByLabelText('Saved baseline')).toBeEnabled())
  expect(screen.getByLabelText('Saved baseline').querySelectorAll('option')).toHaveLength(101)
  fireEvent.change(screen.getByLabelText('Saved baseline'),{target:{value:'oldest'}})
  await waitFor(()=>expect(document.querySelector('.case-record')).toHaveTextContent('Oldest baseline'))
  expect(screen.getByLabelText('Saved baseline')).toHaveValue('oldest')
})
