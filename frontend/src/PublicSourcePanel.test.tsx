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
  const check = {id:'check1',status:'agree',checked_at:'2026-10-11T00:00:00Z',
    assembly_report_uri:'https://ftp.ncbi.nlm.nih.gov/example',assembly_report_sha256:'b'.repeat(64),
    refseq_assembly_accession:'GCF_000001405.40',refseq_accession:'NC_000001.11',
    reference_uri:'https://eutils.ncbi.nlm.nih.gov/example',contextual_uri:'https://api.ncbi.nlm.nih.gov/contextual',hgvs_uri:'https://api.ncbi.nlm.nih.gov/hgvs',
    expected_reference:'C',observed_reference:'C',expected_spdi:'NC_000001.11:6524704:C:T',observed_spdi:'NC_000001.11:6524704:C:T',
    expected_hgvs:'NC_000001.11:g.6524705C>T',observed_hgvs:'NC_000001.11:g.6524705C>T',
    reference_matches:true,representation_checked:true,spdi_matches:true,hgvs_matches:true}
  const fetchMock = vi.fn().mockImplementation(async (url: string) => ({ok:true,json:async()=>url.endsWith('/reference-check')?{check,access:'cache'}:{record,access:'cache'}}))
  vi.stubGlobal('fetch',fetchMock)
  render(<PublicSourcePanel onCompare={vi.fn()}/>)
  expect(fetchMock).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'Load cached'}))
  expect(await screen.findByText(/Loaded from local cache/)).toBeInTheDocument()
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).mode).toBe('cache_only')
  fireEvent.change(screen.getByLabelText('Filter transcripts'),{target:{value:'ENST2'}})
  expect(screen.queryByRole('button',{name:'Use ENST1 as analysis A'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Use ENST2 as analysis A'}))
  expect(screen.getByRole('button',{name:'Compare'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'Load saved check'}))
  expect(await screen.findByText('NC_000001.11:6524704:C:T ✓')).toBeInTheDocument()
  expect(JSON.parse(fetchMock.mock.calls[1][1].body).mode).toBe('cache_only')
  fireEvent.click(screen.getByRole('button',{name:'Fetch current from Ensembl'}))
  expect(JSON.parse(fetchMock.mock.calls[2][1].body).mode).toBe('fetch')
})
