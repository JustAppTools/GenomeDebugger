// Regressions for the thirteen 0.8.1 audit findings, fixed in 0.8.2.
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import WorkspaceLibrary,{type LibraryEditDraft} from './WorkspaceLibrary'
import App from './App'
import {reportHtml} from './ReadableReport'
import type {Result} from './types'
import fixtures from '../audit/fixtures.json'
const result=fixtures.result as unknown as Result
const ok=(value:unknown)=>({ok:true,json:async()=>value})
afterEach(()=>{cleanup();vi.unstubAllGlobals()})

test('favorite cannot advance a stale editor past another tab notes',async()=>{
  let label={id:result.id,title:'Audit comparison',display_name:'',notes:'Original notes',tags:[],favorite:false,archived:false,label_revision:'a'.repeat(64)}
  const posts:any[]=[]
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>{
    if(options?.method==='POST'){
      const body=JSON.parse(String(options.body));posts.push(body)
      if(body.expected_revision&&body.expected_revision!==label.label_revision)return {ok:false,json:async()=>({detail:'Conflict'})}
      const {expected_revision,...patch}=body
      label={...label,...patch,label_revision:body.favorite===true?'c'.repeat(64):'d'.repeat(64)}
      return ok(label)
    }
    return ok({items:[label],total:1,has_more:false,ceiling:1,next_cursor:null})
  }))
  render(<WorkspaceLibrary onOpen={vi.fn()} onDeleted={vi.fn()} onImport={vi.fn()}/> )
  fireEvent.click(await screen.findByRole('button',{name:'Edit details'}))
  fireEvent.change(screen.getByRole('textbox',{name:'Notes'}),{target:{value:'My pending notes'}})
  // Simulate another browser tab completing its save.
  label={...label,notes:'Another tab saved these notes',label_revision:'b'.repeat(64)}
  fireEvent.click(screen.getByRole('button',{name:'Favorite'}))
  await screen.findByRole('button',{name:'Unfavorite'})
  expect(screen.getByRole('textbox',{name:'Notes'})).toHaveValue('My pending notes')
  fireEvent.click(screen.getByRole('button',{name:'Save library details'}))
  await waitFor(()=>expect(posts).toHaveLength(2))
  expect(posts[1].expected_revision).toBe('a'.repeat(64))
  expect(label.notes).toBe('Another tab saved these notes')
  expect(await screen.findByRole('alert')).toHaveTextContent('Conflict')
})

test('switching editors keeps a recoverable draft for each record',async()=>{
  const items=[{id:'one',title:'First',notes:'',tags:[]},{id:'two',title:'Second',notes:'',tags:[]}]
  vi.stubGlobal('fetch',vi.fn(async()=>ok({items,total:2,ceiling:2,has_more:false,next_cursor:null})))
  render(<WorkspaceLibrary onOpen={vi.fn()} onDeleted={vi.fn()} onImport={vi.fn()}/> )
  const buttons=await screen.findAllByRole('button',{name:'Edit details'})
  fireEvent.click(buttons[0]);fireEvent.change(screen.getByRole('textbox',{name:'Notes'}),{target:{value:'Unsaved review of first record'}})
  fireEvent.click(buttons[1])
  expect(screen.getByRole('textbox',{name:'Notes'})).toHaveValue('')
  fireEvent.click(buttons[0])
  expect(screen.getByRole('textbox',{name:'Notes'})).toHaveValue('Unsaved review of first record')
})

test('undoing to the compared input clears its stale-result warning',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>ok(url.endsWith('/health')?{version:'0.6.5'}:url.includes('/demos/')?result.input:options?.method==='POST'?result:url.endsWith('/investigations')?[]:{})))
  render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Try an example'}))
  await screen.findByRole('heading',{name:'What this comparison tells you'})
  fireEvent.click(screen.getByRole('button',{name:'Input JSON'}))
  const editor=screen.getByLabelText('Investigation JSON')
  const original=(editor as HTMLTextAreaElement).value
  fireEvent.change(editor,{target:{value:original+' '}})
  fireEvent.click(screen.getByRole('button',{name:'Undo edit'}))
  expect(editor).toHaveValue(original)
  fireEvent.click(screen.getByRole('button',{name:'Results'}))
  expect(screen.queryByText(/Your input has changed\. The displayed comparison/)).not.toBeInTheDocument()
})

test('readable report includes unchanged additional annotations and complete variant rows',()=>{
  const next=structuredClone(result)
  for(const s of next.input.snapshots){s.annotations=[{gene_id:'UNIQUE-ADDITIONAL-GENE',transcript_id:'UNIQUE-ADDITIONAL-TX',consequence:'synonymous_variant'}];s.variant_records=[{variant:{assembly:'GRCh38',sequence_id:'NC_000001.11',position:104,ref:'T',alt:'G'},annotations:[{gene_id:'UNIQUE-EXTRA-GENE',transcript_id:'UNIQUE-EXTRA-TX',consequence:'intron_variant'}]}]}
  expect(reportHtml(next)).toContain('UNIQUE-ADDITIONAL-TX')
  expect(reportHtml(next)).toContain('UNIQUE-EXTRA-TX')
  next.input.snapshots[0].annotations![0].gene_id='<script>alert(1)</script>'
  expect(reportHtml(next)).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  expect(reportHtml(next)).not.toContain('<script>')
})

test('unsaved library details survive leaving and reopening the section',async()=>{
  const drafts=new Map<string,LibraryEditDraft>()
  const item={id:result.id,title:'Comparison',notes:'',tags:[]}
  vi.stubGlobal('fetch',vi.fn(async()=>ok({items:[item],total:1,ceiling:1,has_more:false,next_cursor:null})))
  const props={onOpen:vi.fn(),onDeleted:vi.fn(),onImport:vi.fn(),drafts}
  const first=render(<WorkspaceLibrary {...props}/> )
  fireEvent.click(await screen.findByRole('button',{name:'Edit details'}))
  fireEvent.change(screen.getByRole('textbox',{name:'Notes'}),{target:{value:'Keep this while I read help'}})
  first.unmount();render(<WorkspaceLibrary {...props}/> )
  expect(screen.getByRole('textbox',{name:'Notes'})).toHaveValue('Keep this while I read help')
  fireEvent.click(screen.getByRole('button',{name:'Cancel editing'}))
  expect(drafts.size).toBe(0)
})

test('detail saves guard editable text and leave archive and favorite flags to their own actions',async()=>{
  const item={id:result.id,title:'Comparison',notes:'',display_name:'',tags:[],favorite:false,archived:false,details_revision:'a'.repeat(64)}
  let submitted:any
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options?:RequestInit)=>{
    if(options?.method==='POST'){submitted=JSON.parse(String(options.body));return ok({...item,...submitted})}
    return ok({items:[item],total:1,has_more:false,ceiling:1,next_cursor:null})
  }))
  render(<WorkspaceLibrary onOpen={vi.fn()} onDeleted={vi.fn()} onImport={vi.fn()}/> )
  fireEvent.click(await screen.findByRole('button',{name:'Edit details'}))
  fireEvent.change(screen.getByRole('textbox',{name:'Notes'}),{target:{value:'Review'}})
  fireEvent.click(screen.getByRole('button',{name:'Save library details'}))
  await waitFor(()=>expect(submitted).toBeDefined())
  expect(submitted).toEqual({display_name:'',notes:'Review',tags:[],expected_details_revision:'a'.repeat(64)})
})
