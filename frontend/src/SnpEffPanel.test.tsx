import { act,cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react'
import { afterEach,expect,test,vi } from 'vitest'
import SnpEffPanel from './SnpEffPanel'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})

test('editing a draft discards a pending saved check instead of selecting stale evidence',async()=>{
  let release:((response:unknown)=>void)|undefined
  vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(resolve=>{release=resolve})))
  const onCheck=vi.fn()
  render(<SnpEffPanel recordId="source" onCheck={onCheck}/>)
  fireEvent.click(screen.getByRole('button',{name:'Load saved comparison'}))
  fireEvent.change(screen.getByLabelText('SnpEff annotated VCF'),{target:{value:'Newer draft'}})
  await act(async()=>{release!({ok:true,json:async()=>({id:'stale',status:'agree',matches:[],unmatched_ensembl:[],unmatched_snpeff:[]})})})
  await waitFor(()=>expect(screen.getByRole('button',{name:'Load saved comparison'})).toBeEnabled())
  expect(document.querySelector('.snpeff-result')).toBeNull()
  expect(onCheck).not.toHaveBeenCalledWith(expect.objectContaining({id:'stale'}))
  expect(onCheck).toHaveBeenLastCalledWith(null)
})

test('a failed superseded file read leaves the latest VCF intact',async()=>{
  let fail:((reason:unknown)=>void)|undefined
  const old=new File(['old'],'old.vcf')
  Object.defineProperty(old,'arrayBuffer',{value:()=>new Promise((_,reject)=>{fail=reject})})
  const latest=new File(['latest'],'latest.vcf')
  Object.defineProperty(latest,'arrayBuffer',{value:async()=>new TextEncoder().encode('Latest selected VCF').buffer})
  render(<SnpEffPanel recordId="source" onCheck={vi.fn()}/>)
  fireEvent.change(screen.getByLabelText('Import annotated VCF'),{target:{files:[old]}})
  fireEvent.change(screen.getByLabelText('Import annotated VCF'),{target:{files:[latest]}})
  await waitFor(()=>expect(screen.getByLabelText('SnpEff annotated VCF')).toHaveValue('Latest selected VCF'))
  await act(async()=>{fail!(new Error('Old read failed'))})
  expect(screen.getByLabelText('SnpEff annotated VCF')).toHaveValue('Latest selected VCF')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
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
  expect(screen.getByText('Legacy text capture; the original output bytes were not retained.')).toBeInTheDocument()
  expect(fetchMock.mock.calls[1][0]).toContain('/source/snpeff-run')
  expect(onCheck).toHaveBeenNthCalledWith(1,null)
  expect(onCheck).toHaveBeenLastCalledWith(expect.objectContaining({id:'run'}))
})

test('new byte captures identify their preserved output format',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({id:'exact',status:'agree',explanation:'Matching annotations',matches:[],unmatched_ensembl:[],unmatched_snpeff:[],vcf_sha256:'hash',
    execution:{capture_format:'utf8_bytes',software_version:'SnpEff 5.4c',jar_sha256:'jarhash',database_sha256:'dbhash',elapsed_seconds:1}})}))
  render(<SnpEffPanel recordId="source" onCheck={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button',{name:'Load saved comparison'}))
  expect(await screen.findByText('Output and diagnostics were captured as exact UTF-8 bytes.')).toBeInTheDocument()
  expect(screen.queryByText(/Legacy text capture/)).not.toBeInTheDocument()
})

for(const mode of ['saved','supplied','local'] as const) {
  test(`an unmounted ${mode} request cannot select a stale check`,async()=>{
    let release:((response:unknown)=>void)|undefined
    vi.stubGlobal('fetch',vi.fn().mockImplementation((url:string)=>url==='/api/tools/snpeff'
      ?Promise.resolve({ok:true,json:async()=>({configured:true,detail:'Ready'})})
      :new Promise(resolve=>{release=resolve})))
    const onCheck=vi.fn()
    const view=render(<SnpEffPanel recordId="old-source" onCheck={onCheck}/>)
    if(mode==='local') {
      fireEvent.click(screen.getByRole('button',{name:'Inspect local SnpEff setup'}))
      await waitFor(()=>expect(screen.getByRole('button',{name:'Run local SnpEff'})).toBeEnabled())
      fireEvent.click(screen.getByRole('button',{name:'Run local SnpEff'}))
    } else if(mode==='saved')fireEvent.click(screen.getByRole('button',{name:'Load saved comparison'}))
    else {
      for(const [label,value] of [['SnpEff version','5.4'],['SnpEff genome database','db'],['SnpEff database SHA-256','a'.repeat(64)],['SnpEff annotated VCF','VCF draft']])
        fireEvent.change(screen.getByLabelText(label),{target:{value}})
      fireEvent.click(screen.getByRole('button',{name:'Compare SnpEff output'}))
    }
    expect(release).toBeDefined()
    view.unmount();onCheck.mockClear()
    await act(async()=>{release!({ok:true,json:async()=>({id:'discarded',status:'agree'})})})
    expect(onCheck).not.toHaveBeenCalled()
  })
}
