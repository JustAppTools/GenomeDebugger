import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import App from './App'
import WorkspaceLibrary from './WorkspaceLibrary'
import DraftTools from './DraftTools'
import fixture from '../audit/fixtures.json'
import extra from '../audit/v0101-fixtures.json'
import GuidedInput from './GuidedInput'
import ReadableReport,{reportHtml} from './ReadableReport'
import LocalDataPanel from './LocalDataPanel'
import type {Result,InvestigationInput} from './types'

const ok=(body:unknown)=>({ok:true,json:async()=>body})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})

test('hosted data lookup failure preserves accurate server-processing and transfer instructions',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.endsWith('/health')?ok({hosted:true,version:'0.6.7',app_version:'0.10.0'}):url==='/api/workspace/data'?{ok:false,status:503}:ok([])))
  render(<App/> )
  await screen.findByLabelText('Public preview storage')
  fireEvent.click(screen.getByRole('button',{name:'Workspace data and settings'}))
  await screen.findByRole('alert')
  expect(screen.queryByRole('heading',{name:'Restore a backup'})).not.toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'Keep and transfer your comparisons'})).toBeInTheDocument()
  expect(screen.queryByText(/The workspace runs locally\./)).not.toBeInTheDocument()
  expect(screen.getByLabelText('Public preview storage')).toHaveTextContent('Inputs are processed on this server')
})

test('successful deletion after leaving the library updates the parent cache',async()=>{
  let release!:(value:unknown)=>void
  const pending=new Promise(resolve=>{release=resolve})
  const onDeleted=vi.fn()
  vi.spyOn(window,'confirm').mockReturnValue(true)
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>options?.method==='DELETE'?pending:ok({items:[{id:'audit-disposable',title:'Disposable synthetic audit record'}],total:1,has_more:false,ceiling:1,next_cursor:null})))
  const view=render(<WorkspaceLibrary onOpen={vi.fn()} onDeleted={onDeleted} onImport={vi.fn()}/> )
  await screen.findByRole('button',{name:'Open'})
  fireEvent.click(screen.getByText('Permanent deletion'))
  fireEvent.click(screen.getByRole('button',{name:'Delete'}))
  view.unmount()
  await act(async()=>{release({ok:true});await pending})
  expect(onDeleted).toHaveBeenCalledExactlyOnceWith('audit-disposable')
  expect(vi.mocked(fetch).mock.calls.some(([,options])=>options?.method==='DELETE')).toBe(true)
})

test('a failed example comparison routes to its retained input editor',async()=>{
  window.history.replaceState(null,'','/#/overview')
  vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>url.endsWith('/health')?ok({version:'0.6.7'}):url.includes('/demos/')?ok(fixture.result.input):options?.method==='POST'?{ok:false,status:503}:ok([])))
  render(<App/> )
  fireEvent.click(screen.getByRole('button',{name:'Try an example'}))
  await screen.findByRole('alert')
  expect(screen.getByRole('heading',{name:'Review your inputs'})).toBeInTheDocument()
  expect(screen.getByLabelText('Investigation JSON')).toBeInTheDocument()
  expect(window.location.hash).toBe('#/input')
})

test.each(['differences','evidence','regression'])('a result-only route without a record offers recovery for %s',async(tab)=>{
  window.history.replaceState(null,'',`/#/${tab}`)
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>ok(url.endsWith('/health')?{version:'0.6.7'}:[])))
  render(<App/> )
  await waitFor(()=>expect(screen.getByText('Local engine connected')).toBeInTheDocument())
  expect(screen.queryByRole('heading',{name:'Choose a starting point'})).not.toBeInTheDocument()
  expect(screen.queryByRole('heading',{name:'Evidence inspector'})).not.toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'Choose a comparison first'})).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Open saved work'})).toBeInTheDocument()
  const current=screen.getByRole('button',{name:'Understand'})
  expect(current).toBeDisabled()
  expect(current).not.toHaveAttribute('aria-current')
  expect(screen.getByRole('navigation',{name:'Comparison steps'}).querySelector('[aria-current=step]')).toHaveTextContent('Choose inputs')
})

test('draft save feedback uses a persistent live region',()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>ok([])))
  render(<DraftTools text='{"title":"Synthetic draft"}' onRestore={vi.fn()} onUndo={vi.fn()} onRedo={vi.fn()} canUndo={false} canRedo={false}/> )
  fireEvent.click(screen.getByRole('button',{name:'Save draft locally'}))
  const feedback=screen.getByText('Draft saved in this browser. It is editable and separate from completed comparisons.')
  expect(feedback.closest('[aria-live]')).toHaveAttribute('aria-live','polite')
  expect(screen.getByRole('status')).toHaveTextContent('Draft saved in this browser')
})

test('human-facing comparison shows the condition and framework when classification changed',async()=>{
  const clinical=extra.clinical as unknown as Result
  vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>ok(url.endsWith('/health')?{version:'0.6.7'}:url.includes('/demos/')?clinical.input:options?.method==='POST'?clinical:[])))
  render(<App/> )
  fireEvent.click(screen.getByRole('button',{name:'Try an example'}))
  await screen.findByRole('heading',{name:'What this comparison tells you'})
  fireEvent.click(screen.getByText('Show technical details'))
  expect(screen.getByLabelText('Supplied clinical assertions')).toHaveTextContent('AUDIT_CONDITION_42')
  expect(screen.getByLabelText('Supplied clinical assertions')).toHaveTextContent('AUDIT_FRAMEWORK')
  expect(reportHtml(clinical)).toContain('AUDIT_CONDITION_42')
})

test('duplicate-annotation validation link focuses the duplicate row',()=>{
  const value=structuredClone(extra.whitespace.input as InvestigationInput)
  value.snapshots[0].annotations=[structuredClone(value.snapshots[0].annotation)]
  let frame:FrameRequestCallback|undefined
  vi.spyOn(window,'requestAnimationFrame').mockImplementation(fn=>{frame=fn;return 1})
  render(<GuidedInput value={value} onChange={vi.fn()} onRun={vi.fn()} busy={false}/> )
  fireEvent.click(screen.getByRole('button',{name:'4. Review'}))
  const error=screen.getByRole('button',{name:'Analysis 1: annotation rows must have unique gene, transcript, and clinical context'})
  error.focus();fireEvent.click(error)
  act(()=>{frame?.(0)})
  expect(screen.getByLabelText('Analysis 1 gene id')).toBeInTheDocument()
  expect(screen.getByLabelText('Analysis 1 additional annotation 1 gene id')).toHaveFocus()
})

test.each(['null','false','0','""'])('syntax indicator distinguishes valid JSON %s from comparison schema',value=>{
  expect(()=>JSON.parse(value)).not.toThrow()
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>ok(url.endsWith('/health')?{version:'0.6.7'}:[])))
  render(<App/> )
  fireEvent.click(screen.getByRole('button',{name:'Enter my results'}))
  fireEvent.click(screen.getByRole('button',{name:'JSON editor'}))
  fireEvent.change(screen.getByLabelText('Investigation JSON'),{target:{value}})
  expect(screen.getByText('Valid JSON · enter a two-analysis object',{exact:true})).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Compare'})).toBeDisabled()
})


test('unknown processing mode never claims local storage after metadata failure',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:503})))
  render(<LocalDataPanel/> )
  await screen.findByRole('alert')
  expect(screen.queryByRole('heading',{name:'Restore a backup'})).not.toBeInTheDocument()
  expect(screen.queryByText(/The workspace runs locally/)).not.toBeInTheDocument()
  expect(screen.getByText(/could not yet be verified/)).toBeInTheDocument()
})

test('report preview takes focus, scrolls into view, and returns focus on close',()=>{
  const trigger=document.createElement('button');document.body.append(trigger);trigger.focus()
  const scroll=vi.fn();HTMLElement.prototype.scrollIntoView=scroll
  const view=render(<ReadableReport result={fixture.result as unknown as Result} onClose={vi.fn()} onDownload={vi.fn()}/> )
  expect(screen.getByLabelText('Readable report preview')).toHaveFocus()
  expect(scroll).toHaveBeenCalledWith({block:'start'})
  view.unmount();expect(trigger).toHaveFocus();trigger.remove()
})

test('duplicate variant link focuses the duplicate DNA description',()=>{
  const value=structuredClone(extra.whitespace.input as InvestigationInput)
  value.snapshots[0].variant_records=[{variant:structuredClone(value.snapshots[0].variant),annotations:[structuredClone(value.snapshots[0].annotation)]}]
  let frame:FrameRequestCallback|undefined
  vi.spyOn(window,'requestAnimationFrame').mockImplementation(fn=>{frame=fn;return 1})
  render(<GuidedInput value={value} onChange={vi.fn()} onRun={vi.fn()} busy={false}/> )
  fireEvent.click(screen.getByRole('button',{name:'4. Review'}))
  fireEvent.click(screen.getByRole('button',{name:'Analysis 1: variant representations must be unique'}))
  act(()=>{frame?.(0)})
  expect(screen.getByLabelText('Analysis 1 variant 2 sequence accession')).toHaveFocus()
})
