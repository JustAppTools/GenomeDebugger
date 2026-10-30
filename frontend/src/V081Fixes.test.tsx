// Regressions for the 0.8.0 audit, fixed in 0.8.1.
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import App from './App'
import WorkspaceLibrary from './WorkspaceLibrary'
import ImportWorkspace from './ImportWorkspace'
import EvidenceInspector from './EvidenceInspector'
import type {Result} from './types'
import fixtures from '../audit/fixtures.json'
import {DRAFT_KEY} from './DraftTools'

const result=fixtures.result as unknown as Result
const ok=(value:unknown)=>({ok:true,json:async()=>value})
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
function stubApp(){vi.stubGlobal('fetch',vi.fn(async(url:string)=>ok(url.endsWith('/health')?{version:'0.6.5'}:url.endsWith('/investigations')?[]:{})))}

test('draft availability follows storage changes from another tab',()=>{
  stubApp();render(<App/>)
  expect(screen.queryByRole('button',{name:'Resume saved draft'})).not.toBeInTheDocument()
  act(()=>{localStorage.setItem(DRAFT_KEY,JSON.stringify({text:JSON.stringify(result.input),savedAt:'2026-10-27T00:00:00Z'}));window.dispatchEvent(new StorageEvent('storage',{key:DRAFT_KEY}))})
  expect(screen.getByRole('button',{name:'Resume saved draft'})).toBeInTheDocument()
  act(()=>{localStorage.removeItem(DRAFT_KEY);window.dispatchEvent(new StorageEvent('storage',{key:DRAFT_KEY}))})
  expect(screen.queryByRole('button',{name:'Resume saved draft'})).not.toBeInTheDocument()
})

test('archive sends only the flag and keeps metadata returned by the server',async()=>{
  const item={id:result.id,title:'Comparison',notes:'Old cached notes',display_name:'Old cached name',tags:[],archived:false,favorite:false,label_revision:'a'.repeat(64)}
  let submitted:unknown
  const organized=vi.fn()
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>{
    if(options?.method==='POST'){submitted=JSON.parse(String(options.body));return ok({...item,notes:'Newer saved notes',display_name:'Newer saved name',archived:true})}
    return ok({items:[item],total:1,has_more:false,ceiling:1,next_cursor:null})
  }))
  render(<WorkspaceLibrary onOpen={vi.fn()} onDeleted={vi.fn()} onImport={vi.fn()} onOrganized={organized}/> )
  fireEvent.click(await screen.findByRole('button',{name:'Archive'}))
  await waitFor(()=>expect(organized).toHaveBeenCalled())
  expect(submitted).toEqual({archived:true})
  expect(organized.mock.calls[0][0]).toMatchObject({display_name:'Newer saved name',archived:true})
})

test('a conflicting edit retains the users text and becomes editable again',async()=>{
  const item={id:result.id,title:'Comparison',notes:'Saved notes',tags:[],label_revision:'a'.repeat(64)}
  let submitted:any
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>{
    if(options?.method==='POST'){submitted=JSON.parse(String(options.body));return {ok:false,json:async()=>({detail:'Saved details changed in another tab. Your edits are still here.'})}}
    return ok({items:[item],total:1,has_more:false,ceiling:1,next_cursor:null})
  }))
  render(<WorkspaceLibrary onOpen={vi.fn()} onDeleted={vi.fn()} onImport={vi.fn()}/> )
  fireEvent.click(await screen.findByRole('button',{name:'Edit details'}))
  fireEvent.change(screen.getByLabelText('Notes',{exact:true}),{target:{value:'Keep my unsaved review'}})
  fireEvent.click(screen.getByRole('button',{name:'Save library details'}))
  await screen.findByRole('alert')
  expect(submitted.expected_revision).toBe(item.label_revision)
  expect(screen.getByLabelText('Notes',{exact:true})).toHaveValue('Keep my unsaved review')
  expect(screen.getByLabelText('Notes',{exact:true})).toBeEnabled()
})

test('saving a draft updates the home Resume offer',async()=>{
  stubApp();render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Enter my results'}))
  fireEvent.change(screen.getByLabelText('Investigation title'),{target:{value:'Explicitly saved draft'}})
  fireEvent.click(screen.getByRole('button',{name:'Save draft locally'}))
  expect(localStorage.getItem('genomedebugger-explicit-draft-v1')).toContain('Explicitly saved draft')
  fireEvent.click(screen.getByRole('button',{name:'Results'}))
  expect(screen.getByRole('button',{name:'Resume saved draft'})).toBeInTheDocument()
})

test('discarding a draft removes the home Resume offer',async()=>{
  localStorage.setItem('genomedebugger-explicit-draft-v1',JSON.stringify({text:JSON.stringify(result.input),savedAt:'2026-10-27T00:00:00Z'}))
  stubApp();render(<App/>);expect(screen.getByRole('button',{name:'Resume saved draft'})).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Enter my results'}))
  fireEvent.click(screen.getByRole('button',{name:'Discard saved draft'}))
  expect(localStorage.getItem('genomedebugger-explicit-draft-v1')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'Results'}))
  expect(screen.queryByRole('button',{name:'Resume saved draft'})).not.toBeInTheDocument()
})

test('metadata editing is locked while the submitted notes are saving',async()=>{
  let release!:(value:unknown)=>void;const pending=new Promise(resolve=>{release=resolve})
  const item={id:result.id,title:'Saved comparison',notes:'',tags:[],display_name:'',favorite:false,archived:false}
  vi.stubGlobal('fetch',vi.fn((_url:string,options?:RequestInit)=>options?.method==='POST'?pending:Promise.resolve(ok({items:[item],total:1,ceiling:1,next_cursor:null,has_more:false}))))
  render(<WorkspaceLibrary onOpen={vi.fn()} onDeleted={vi.fn()} onImport={vi.fn()}/> )
  fireEvent.click(await screen.findByRole('button',{name:'Edit details'}))
  fireEvent.change(screen.getByLabelText('Notes',{exact:true}),{target:{value:'Submitted notes'}})
  fireEvent.click(screen.getByRole('button',{name:'Save library details'}))
  expect(screen.getByLabelText('Notes',{exact:true})).toBeDisabled()
  expect(screen.getByLabelText('Display name')).toBeDisabled()
  expect(screen.getByLabelText('Tags (comma separated)')).toBeDisabled()
  await act(async()=>release(ok({...item,notes:'Submitted notes'})))
  await waitFor(()=>expect(screen.queryByRole('region',{name:'Edit comparison details'})).not.toBeInTheDocument())
})

test('CSV preview retains the original UTF-8 BOM before hashing',async()=>{
  let submitted:any
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options:RequestInit)=>{submitted=JSON.parse(String(options.body));return ok({input:result.input,files:[],warnings:[]})}))
  render(<ImportWorkspace onUse={vi.fn()} onSources={vi.fn()}/> )
  const raw='\ufeffassembly,sequence_id,position,ref,alt,gene_id,transcript_id,consequence,tool,tool_version,source_name,source_release\r\nGRCh38,NC_000001.11,102,C,T,G,T1,missense_variant,Tool,1,Source,1\r\n'
  const bytes=new TextEncoder().encode(raw)
  for(const side of [1,2]){
    const file=new File([bytes],`analysis-${side}.csv`)
    Object.defineProperty(file,'arrayBuffer',{value:async()=>bytes.buffer})
    fireEvent.change(screen.getByLabelText(`Analysis ${side} tabular file`),{target:{files:[file]}})
  }
  fireEvent.click(screen.getByRole('button',{name:'Preview imported rows'}))
  await waitFor(()=>expect(submitted).toBeDefined())
  expect(submitted.files[0].text).toBe(raw)
  expect(new TextEncoder().encode(submitted.files[0].text).length).toBe(bytes.length)
})

test('valid Unicode file names produce a valid complete-character preview title',async()=>{
  let submitted:any
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options:RequestInit)=>{submitted=JSON.parse(String(options.body));return ok({input:result.input,files:[],warnings:[]})}))
  render(<ImportWorkspace onUse={vi.fn()} onSources={vi.fn()}/> )
  const names=['a'.repeat(130)+'.csv','b'.repeat(50)+'🧬.csv']
  const bytes=new TextEncoder().encode('file contents')
  for(const index of [0,1]){
    const file=new File([bytes],names[index]);Object.defineProperty(file,'arrayBuffer',{value:async()=>bytes.buffer})
    fireEvent.change(screen.getByLabelText(`Analysis ${index+1} tabular file`),{target:{files:[file]}})
  }
  fireEvent.click(screen.getByRole('button',{name:'Preview imported rows'}))
  await waitFor(()=>expect(submitted).toBeDefined())
  expect(submitted.title).toBe(Array.from(`${names[0]} compared with ${names[1]}`).slice(0,200).join(''))
  expect(Array.from(submitted.title)).toHaveLength(200)
})

test.each(['matching','uncertain'] as const)('%s example explains that no controlled lookup was provided',async kind=>{
  const saved=fixtures[kind] as unknown as Result
  expect(saved.input.controlled_lookup).toBeNull()
  window.history.replaceState(null,'',`/#/comparison/${saved.id}/overview`)
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>ok(url.endsWith('/health')?{version:'0.6.5'}:url.endsWith('/investigations')?[]:saved)))
  render(<App/>);await screen.findByRole('heading',{name:'How to read this example'})
  expect(screen.queryByText('The controlled lookup repeats those outputs within this constructed example. It does not test a real annotation system.')).not.toBeInTheDocument()
  expect(screen.getByText('No controlled lookup was provided or replayed for this example.')).toBeInTheDocument()
  if(kind==='uncertain')expect(screen.getByText(/This made-up example omits reference context/)).toBeInTheDocument()
})

test('re-comparing a renamed saved record preserves its name in Recent',async()=>{
  const saved={...result,input:{...result.input,title:'Original scientific title'}}
  vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>ok(url.endsWith('/health')?{version:'0.6.5'}:url.endsWith('/investigations')&&!options?.method?[{id:saved.id,title:saved.input.title,display_name:'My recognizable name'}]:saved)))
  render(<App/>);const sidebar=screen.getByRole('complementary')
  fireEvent.click(await within(sidebar).findByRole('button',{name:/My recognizable name/}))
  await screen.findByRole('heading',{name:'Compared analyses'})
  fireEvent.click(screen.getByRole('button',{name:'Run comparison'}))
  await waitFor(()=>expect(vi.mocked(fetch).mock.calls.some(([,options])=>options?.method==='POST')).toBe(true))
  await act(async()=>{})
  expect(within(sidebar).getByRole('button',{name:/My recognizable name/})).toBeInTheDocument()
})

test('readable additional-variant identity record shows its status and explanation',()=>{
  const saved=fixtures.additional as unknown as Result
  const evidence=saved.evidence.find(record=>record.id.startsWith('variant-record-'))!
  expect(evidence.data.status).toBe('unresolved')
  render(<EvidenceInspector result={saved} selected={evidence.id} onSelect={vi.fn()}/> )
  const detail=document.querySelector('.evidence-detail')!
  const raw=detail.querySelector('.raw-record')!
  const textWithoutRaw=[...detail.children].filter(child=>child!==raw).map(child=>child.textContent).join(' ')
  expect(textWithoutRaw).toContain(evidence.data.explanation as string)
  expect(textWithoutRaw).toContain('unresolved')
  expect(raw.textContent).toContain(evidence.data.explanation as string)
})
