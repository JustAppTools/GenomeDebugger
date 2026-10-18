import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

test('loads a demo, compares snapshots, and opens replay evidence', async () => {
  const demo = {title:'Synthetic test',synthetic:true,snapshots:[
    {id:'A',label:'Analysis A',variant:{assembly:'GRCh38',sequence_id:'NC_1',position:1,ref:'A',alt:'T'},annotation:{gene_id:'G',transcript_id:'TX1',consequence:'missense_variant'},provenance:{tool:'fixture',tool_version:'1',source_name:'fixture',source_release:'1',configuration:{}}},
    {id:'B',label:'Analysis B',variant:{assembly:'GRCh38',sequence_id:'NC_1',position:1,ref:'A',alt:'T'},annotation:{gene_id:'G',transcript_id:'TX2',consequence:'intron_variant'},provenance:{tool:'fixture',tool_version:'1',source_name:'fixture',source_release:'1',configuration:{}}}
  ]}
  const result = {id:'abc123',input:demo,identity:{status:'verified',explanation:'Alleles match',normalized_a:'A>T',normalized_b:'A>T',evidence_ids:['identity-inputs']},differences:[{field:'consequence',category:'annotation',before:'missense_variant',after:'intron_variant',meaningful:true,evidence_ids:['diff-1']}],findings:[{status:'verified',cause:'transcript selection',explanation:'Controlled replay matches.',affected_fields:['consequence'],evidence_ids:['controlled-lookup']}],evidence:[{id:'identity-inputs',kind:'input',description:'Alleles',data:{}},{id:'controlled-lookup',kind:'controlled_replay',description:'Deterministic lookup replay',data:{matches:true}}],input_sha256:'abc'}
  const fetchMock = vi.fn().mockImplementation(async (url: string, options?: {method?: string}) => {
    if (url === '/api/investigations' && options?.method !== 'POST') return {ok:true,json:async()=>[]}
    if (url === '/api/demos/transcript-switch') return {ok:true,json:async()=>demo}
    return {ok:true,json:async()=>result}
  })
  vi.stubGlobal('fetch',fetchMock)
  render(<App />)
  fireEvent.click(screen.getAllByRole('button',{name:/load synthetic demo/i})[0])
  expect(await screen.findByText('Controlled replay matches.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Snapshot JSON'}))
  expect(screen.getByLabelText('Investigation JSON')).toHaveValue(JSON.stringify(demo,null,2))
  fireEvent.change(screen.getByLabelText('Investigation JSON'), {target:{value:'{'}})
  expect(screen.getByRole('status')).toHaveTextContent('The snapshot JSON has changed')
  expect(screen.getByRole('button',{name:'Compare'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'Run demo'}))
  expect(await screen.findByText('Controlled replay matches.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:/view test/i}))
  expect(await screen.findByText('Deterministic lookup replay')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(6)
})

test('shows a useful error and leaves demo input editable if comparison fails', async () => {
  const demo = {title:'Synthetic test',synthetic:true,snapshots:[]}
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string, options?: {method?: string}) => {
    if (url === '/api/investigations' && options?.method !== 'POST') return {ok:true,json:async()=>[]}
    if (url === '/api/demos/transcript-switch') return {ok:true,json:async()=>demo}
    return {ok:false,status:503}
  }))
  render(<App />)
  fireEvent.click(screen.getAllByRole('button',{name:/load synthetic demo/i})[0])
  expect(await screen.findByRole('alert')).toHaveTextContent('Demo comparison failed (503)')
  expect(screen.getByLabelText('Investigation JSON')).toHaveValue(JSON.stringify(demo,null,2))
})

test('reopens a persisted investigation from the recent list', async () => {
  const result = {id:'saved1',input:{title:'Saved discrepancy',synthetic:true,snapshots:[
    {id:'A',label:'A',variant:{assembly:'GRCh38',sequence_id:'NC_1',position:1,ref:'A',alt:'T'},annotation:{gene_id:'G',transcript_id:'TX1',consequence:'missense_variant'},provenance:{tool:'fixture',tool_version:'1',source_name:'fixture',source_release:'1',configuration:{}}},
    {id:'B',label:'B',variant:{assembly:'GRCh38',sequence_id:'NC_1',position:1,ref:'A',alt:'T'},annotation:{gene_id:'G',transcript_id:'TX2',consequence:'intron_variant'},provenance:{tool:'fixture',tool_version:'1',source_name:'fixture',source_release:'1',configuration:{}}}
  ]},identity:{status:'verified',explanation:'Alleles match',evidence_ids:['identity-inputs']},differences:[],findings:[],evidence:[],input_sha256:'hash'}
  const fetchMock = vi.fn().mockImplementation(async (url: string) => url === '/api/investigations'
    ? {ok:true,json:async()=>[{id:'saved1',title:'Saved discrepancy'}]}
    : {ok:true,json:async()=>result})
  vi.stubGlobal('fetch',fetchMock)
  render(<App />)
  fireEvent.click(await screen.findByRole('button',{name:/saved discrepancy saved1/i}))
  expect(await screen.findByText('Alleles match')).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledTimes(3)
})
