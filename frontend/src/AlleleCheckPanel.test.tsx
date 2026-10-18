import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach,expect,test,vi } from 'vitest'
import AlleleCheckPanel from './AlleleCheckPanel'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})
test('shows reference-backed contextual identity and requests explicit fetch',async()=>{
  const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>({id:'check',status:'agree',checked_at:'2026-10-17T00:00:00Z',
    explanation:'Both normalized alleles match.',observations:[{accession:'NC_000001.11',reference_matches:true,
      contextual_uri:'https://api.ncbi.nlm.nih.gov/variation/v0/spdi/NC_000001.11:10003:CCC:CC/contextual',
      contextual_sha256:'hash',hgvs:'NC_000001.11:g.10006del',normalized:{seq_id:'NC_000001.11',position:10003,deleted_sequence:'CCC',inserted_sequence:'CC'}}]})})
  vi.stubGlobal('fetch',fetchMock)
  render(<AlleleCheckPanel id="investigation" synthetic={false}/>)
  fireEvent.click(screen.getByRole('button',{name:'Check allele identity with NCBI'}))
  expect(await screen.findByText('NC_000001.11:10003:CCC:CC')).toBeInTheDocument()
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).mode).toBe('fetch')
})

test('blocks synthetic input from external reference checks',()=>{
  render(<AlleleCheckPanel id="fixture" synthetic/>)
  expect(screen.getByRole('button',{name:'Check allele identity with NCBI'})).toBeDisabled()
})
