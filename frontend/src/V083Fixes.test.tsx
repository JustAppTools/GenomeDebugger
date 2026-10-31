// Corrected-behavior regressions for the 0.8.2 audit.
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import App from './App'
import WorkspaceLibrary,{type LibraryEditDraft} from './WorkspaceLibrary'
import GuidedInput from './GuidedInput'
import ResultsSummary from './ResultsSummary'
import DraftTools,{DRAFT_KEY,readSavedDraft} from './DraftTools'
import LocalDataPanel from './LocalDataPanel'
import {useState} from 'react'
import type {Result} from './types'
import fixtures from '../audit/v082-fixtures.json'

const result=fixtures.result as unknown as Result
const ok=(value:unknown)=>({ok:true,json:async()=>value})
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
function appFetch(){vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
  if(url.endsWith('/health'))return ok({version:'0.6.6'})
  if(url.includes('/demos/'))return ok(result.input)
  if(url.includes('/regression-cases'))return ok([])
  if(url.endsWith('/investigations'))return ok(options?.method==='POST'?result:[])
  return ok({})
}))}

test('a custom unrelated row policy retains the verified transcript explanation',()=>{
  const value=fixtures.manual_policy_result as unknown as Result
  expect(value.findings.some(f=>f.cause==='transcript selection'&&f.status==='verified')).toBe(true)
  render(<ResultsSummary result={value} onChanges={vi.fn()} onEvidence={vi.fn()}/> )
  expect(screen.queryByText(/No preferred transcript was declared by these files/)).not.toBeInTheDocument();expect(screen.getByText(/The selected transcripts also differ/)).toBeInTheDocument()
})

test('reference letters require an explicitly supplied context start',()=>{
  const input=structuredClone(result.input)
  input.snapshots[0].variant={assembly:'GRCh38',sequence_id:'NC_000001.11',position:102,ref:'C',alt:'T'}
  const changed=vi.fn()
  render(<GuidedInput value={input} onChange={changed} onRun={vi.fn()} busy={false}/> )
  fireEvent.click(screen.getByRole('button',{name:'Show all fields (experienced users)'}))
  fireEvent.change(screen.getByLabelText('Analysis 1 reference sequence',{exact:true}),{target:{value:'CAGT'}})
  const submitted=changed.mock.calls.at(-1)![0]
  expect(submitted.snapshots[0].variant.reference_context).toEqual({start:0,sequence:'CAGT'})
})

test('near-limit browser drafts remain readable after JSON escaping',()=>{
  const text=JSON.stringify('\\'.repeat(999990))
  expect(new TextEncoder().encode(text).length).toBeLessThanOrEqual(2_000_000)
  render(<DraftTools text={text} onRestore={vi.fn()} onUndo={vi.fn()} onRedo={vi.fn()} canUndo={false} canRedo={false}/> )
  fireEvent.click(screen.getByRole('button',{name:'Save draft locally'}))
  expect(screen.getByText('Draft saved in this browser. It is editable and separate from completed comparisons.')).toBeInTheDocument()
  expect(localStorage.getItem(DRAFT_KEY)!.length).toBeGreaterThan(4_000_000)
  expect(readSavedDraft()?.text).toBe(text)
})

test('opening Help retains an unsaved public-source query',async()=>{
  appFetch();render(<App/> )
  fireEvent.click(screen.getByRole('button',{name:'Explore public data'}))
  fireEvent.change(screen.getByLabelText('Position',{exact:true}),{target:{value:'12345'}})
  fireEvent.click(screen.getByRole('link',{name:'Guide'}))
  fireEvent.click(screen.getByRole('button',{name:'Explore a public DNA change'}))
  expect(screen.getByLabelText('Position',{exact:true})).toHaveValue(12345)
})

test('Enter results navigation preserves malformed JSON in its editor',async()=>{
  appFetch();render(<App/> )
  fireEvent.click(screen.getByRole('button',{name:'Enter my results'}))
  fireEvent.click(screen.getByRole('button',{name:'JSON editor'}))
  const text='{"title":"Keep this unfinished analysis", "snapshots":['
  fireEvent.change(screen.getByLabelText('Investigation JSON'),{target:{value:text}})
  fireEvent.click(screen.getByRole('link',{name:'Guide'}))
  fireEvent.click(screen.getByRole('link',{name:'Compare'}));fireEvent.click(screen.getByRole('button',{name:'Review inputs'}))
  expect(screen.getByLabelText('Investigation JSON')).toHaveValue(text)
  expect(screen.getByRole('alert')).toHaveTextContent('Repair the JSON')
})

test.each([false,true])('a resumed editor reconciles its pending save (new edits before response: %s)',async(editEarly)=>{
  const drafts=new Map<string,LibraryEditDraft>()
  let label={id:result.id,title:'Audit comparison',display_name:'',notes:'',tags:[],details_revision:'a'.repeat(64)}
  let release!:(value:unknown)=>void
  const pending=new Promise(resolve=>{release=resolve})
  let count=0
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>{
    if(options?.method==='POST'){
      const value=JSON.parse(String(options.body))
      if(value.expected_details_revision!==label.details_revision)return {ok:false,json:async()=>({detail:'Saved details changed in another tab'})}
      label={...label,notes:value.notes,details_revision:'b'.repeat(64)}
      if(count++===0)return pending
      return ok(label)
    }
    return ok({items:[label],total:1,has_more:false,ceiling:1,next_cursor:null})
  }))
  const props={onOpen:vi.fn(),onDeleted:vi.fn(),onImport:vi.fn(),drafts}
  const first=render(<WorkspaceLibrary {...props}/> )
  fireEvent.click(await screen.findByRole('button',{name:'Edit details'}))
  fireEvent.change(screen.getByRole('textbox',{name:'Notes'}),{target:{value:'First saved notes'}})
  fireEvent.click(screen.getByRole('button',{name:'Save library details'}))
  await waitFor(()=>expect(count).toBe(1))
  first.unmount();render(<WorkspaceLibrary {...props}/> )
  if(editEarly)fireEvent.change(screen.getByRole('textbox',{name:'Notes'}),{target:{value:'More notes after returning'}})
  await act(async()=>{release(ok(label));await pending})
  if(!editEarly)fireEvent.change(screen.getByRole('textbox',{name:'Notes'}),{target:{value:'More notes after returning'}})
  expect(screen.getByRole('textbox',{name:'Notes'})).toHaveValue('More notes after returning')
  fireEvent.click(screen.getByRole('button',{name:'Save library details'}))
  await waitFor(()=>expect(label.notes).toBe('More notes after returning'))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('clearing an optional protein field restores the missing value',()=>{
  const start=structuredClone(result.input);start.controlled_lookup=null
  for(const snapshot of start.snapshots)snapshot.annotation.protein_consequence=null
  const changed=vi.fn()
  function Controlled(){const [value,setValue]=useState(start);return <GuidedInput value={value} onChange={next=>{setValue(next);changed(next)}} onRun={vi.fn()} busy={false}/>}
  render(<Controlled/> )
  fireEvent.click(screen.getByRole('button',{name:'Show all fields (experienced users)'}))
  const input=screen.getByLabelText('Analysis 1 protein consequence',{exact:true})
  fireEvent.change(input,{target:{value:'Temporary value'}});fireEvent.change(input,{target:{value:''}})
  expect(input).toHaveValue('')
  expect(screen.getByLabelText('Analysis 2 protein consequence',{exact:true})).toHaveValue('')
  const value=changed.mock.calls.at(-1)![0]
  expect(value.snapshots[0].annotation.protein_consequence).toBe(null)
  expect(value.snapshots[1].annotation.protein_consequence).toBe(null)
})

test('failed storage details stop loading and offer retry',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>{throw new Error('Offline')}))
  render(<LocalDataPanel/> )
  expect(await screen.findByRole('alert')).toHaveTextContent('Offline')
  expect(screen.queryByText('Loading storage details…')).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Retry storage details'})).toBeInTheDocument()
})
