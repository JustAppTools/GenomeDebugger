import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import PublicSourcePanel from './PublicSourcePanel'

afterEach(() => vi.unstubAllGlobals())

test('the public adapter runs only after an explicit cache or fetch action', async () => {
  const record = { id:'record1', query:{chromosome:'1',position:6524705,ref:'C',alt:'T'},
    retrieved_at:'2026-10-11T00:00:00Z', source_uri:'https://rest.ensembl.org/vep/example',
    sequence_uri:'https://rest.ensembl.org/sequence/example', release_uri:'https://rest.ensembl.org/info/data',
    assembly_uri:'https://rest.ensembl.org/info/assembly/human', releases:[116],
    assembly_name:'GRCh38.p14', assembly_accession:'GCA_000001405.29', source_response_sha256:'a'.repeat(64),
    transcripts:[{transcript_id:'ENST1',gene_id:'ENSG1',consequence_terms:['intron_variant']},
      {transcript_id:'ENST2',gene_id:'ENSG1',consequence_terms:['3_prime_UTR_variant']}] }
  const fetchMock = vi.fn().mockResolvedValue({ok:true,json:async()=>({record,access:'cache'})})
  vi.stubGlobal('fetch',fetchMock)
  render(<PublicSourcePanel onCompare={vi.fn()}/>)
  expect(fetchMock).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'Load cached'}))
  expect(await screen.findByText(/Loaded from local cache/)).toBeInTheDocument()
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).mode).toBe('cache_only')
  fireEvent.click(screen.getByRole('button',{name:'Fetch current from Ensembl'}))
  expect(JSON.parse(fetchMock.mock.calls[1][1].body).mode).toBe('fetch')
})
