import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import RegressionPanel from './RegressionPanel'
import type { Result } from './types'

afterEach(() => vi.unstubAllGlobals())

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
