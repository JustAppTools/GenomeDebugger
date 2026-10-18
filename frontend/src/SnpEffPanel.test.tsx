import { fireEvent,render,screen } from '@testing-library/react'
import { afterEach,expect,test,vi } from 'vitest'
import SnpEffPanel from './SnpEffPanel'

afterEach(()=>vi.unstubAllGlobals())
test('runs the pinned local tool only after showing its configuration',async()=>{
  const fetchMock=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({configured:true,genome:'GRCh38.mane',software_version:'SnpEff 5.4c',detail:'Pinned artifacts'})})
    .mockResolvedValueOnce({ok:true,json:async()=>({id:'run',status:'unresolved',explanation:'Transcript versions differ',matches:[],unmatched_ensembl:['T1'],unmatched_snpeff:['T1.2'],vcf_sha256:'hash',
      execution:{software_version:'SnpEff 5.4c',jar_sha256:'jarhash',database_sha256:'dbhash',elapsed_seconds:3}})})
  vi.stubGlobal('fetch',fetchMock)
  const onCheck=vi.fn()
  render(<SnpEffPanel recordId="source" onCheck={onCheck}/>)
  expect(screen.getByRole('button',{name:'Run local SnpEff'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'Inspect local SnpEff setup'}))
  await screen.findByText(/Pinned artifacts/)
  fireEvent.click(screen.getByRole('button',{name:'Run local SnpEff'}))
  expect(await screen.findByText(/JAR SHA-256 jarhash/)).toBeInTheDocument()
  expect(fetchMock.mock.calls[1][0]).toContain('/source/snpeff-run')
  expect(onCheck).toHaveBeenCalledTimes(1)
})
