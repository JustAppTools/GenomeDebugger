import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import InvestigationLibrary from './InvestigationLibrary'
import HistoricalPanel from './HistoricalPanel'

afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})

test('a list request crossing deletion cannot restore the removed record',async()=>{
  let release:((response:unknown)=>void)|undefined
  const pending=new Promise(resolve=>{release=resolve})
  const deleted=vi.fn()
  const victim={id:'victim',title:'Victim record'}
  const other={id:'other',title:'Other record'}
  let gets=0
  vi.spyOn(window,'confirm').mockReturnValue(true)
  vi.stubGlobal('fetch',vi.fn().mockImplementation((_:string,options?:RequestInit)=>{
    if(options?.method==='DELETE')return Promise.resolve({ok:true})
    gets++
    if(gets===2)return pending
    return Promise.resolve({ok:true,json:async()=>({items:gets===1?[victim,other]:[other],total:2,ceiling:2,has_more:false,next_cursor:null})})
  }))
  render(<InvestigationLibrary onOpen={vi.fn()} onDeleted={deleted} onImport={vi.fn()}/>)
  await screen.findByText(victim.title)
  fireEvent.change(screen.getByLabelText('Search investigations'),{target:{value:'record'}})
  fireEvent.click(within(screen.getByText(victim.title).closest('.library-row') as HTMLElement).getByText('Permanent deletion'))
  fireEvent.click(within(screen.getByText(victim.title).closest('.library-row') as HTMLElement).getByRole('button',{name:'Delete'}))
  await waitFor(()=>expect(screen.queryByText(victim.title)).not.toBeInTheDocument())
  await act(async()=>{release!({ok:true,json:async()=>({items:[victim,other],total:2,ceiling:2,has_more:false,next_cursor:null})})})
  expect(screen.queryByText(victim.title)).not.toBeInTheDocument()
  expect(screen.getByText(other.title)).toBeInTheDocument()
  expect(deleted).toHaveBeenCalledWith(victim.id)
})

test('older investigations remain reachable and searching resets the page',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>{
    const query=new URL(url,'http://localhost').searchParams
    const offset=Number(query.get('offset')??0)
    const count=query.get('q')?1:offset?1:50
    return {ok:true,json:async()=>({items:Array.from({length:count},(_,i)=>({id:`id-${offset+i}`,title:`Record ${offset+i}`})),total:query.get('q')?1:51,ceiling:101,has_more:count===50,next_cursor:count===50?'next':null})}
  }))
  render(<InvestigationLibrary onOpen={vi.fn()} onDeleted={vi.fn()} onImport={vi.fn()}/>)
  await screen.findByText('Record 0')
  fireEvent.click(screen.getByRole('button',{name:'Next records'}))
  await screen.findByText('Record 50')
  expect(screen.queryByText('Record 0')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Search investigations'),{target:{value:'Record 0'}})
  await screen.findByText('Record 0')
  expect(screen.getByRole('button',{name:'Previous records'})).toBeDisabled()
})

test('loading older preserved sources keeps current selections',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>{
    const more=url.includes('offset=200')
    return {ok:true,json:async()=>Array.from({length:more?1:200},(_,i)=>({
      id:`source-${(more?200:0)+i}`,origin:'current_api',releases:[116],retrieved_at:'2026-10-18T00:00:00Z',
      query:{chromosome:'1',position:6524705,ref:'C',alt:'T'},
      transcripts:[{transcript_id:'T1',consequence_terms:['intron_variant']}],
    }))}
  }))
  render(<HistoricalPanel onCompare={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button',{name:'Load preserved sources'}))
  await screen.findByRole('button',{name:'Load older sources'})
  fireEvent.click(screen.getByRole('button',{name:'Load older sources'}))
  await waitFor(()=>expect(screen.getByLabelText('Preserved analysis 1 source').querySelectorAll('option')).toHaveLength(201))
  expect(screen.getByLabelText('Preserved analysis 1 source')).toHaveValue('source-0')
  expect(screen.getByLabelText('Preserved analysis 2 source')).toHaveValue('source-1')
  fireEvent.change(screen.getByLabelText('Preserved analysis 2 source'),{target:{value:'source-200'}})
  expect(screen.getByRole('button',{name:'Compare preserved sources'})).toBeEnabled()
})

test('a refresh keeps valid selections and explains replacements for missing sources',async()=>{
  const source=(id:string)=>({id,origin:'current_api',releases:[116],query:{chromosome:'1',position:1,ref:'C',alt:'T'},
    transcripts:[{transcript_id:'T1',consequence_terms:['intron_variant']},{transcript_id:'T2',consequence_terms:['intron_variant']}]})
  let requests=0
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>url.includes('/records/')?{ok:false,status:404}:{ok:true,json:async()=>++requests<3?[source('A'),source('B')]:[source('B')]}))
  render(<HistoricalPanel onCompare={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button',{name:'Load preserved sources'}))
  await screen.findByLabelText('Preserved analysis 1 source')
  fireEvent.change(screen.getByLabelText('Preserved analysis 1 transcript'),{target:{value:'T2'}})
  fireEvent.click(screen.getByRole('button',{name:'Load preserved sources'}))
  await waitFor(()=>expect(requests).toBe(2))
  expect(screen.getByLabelText('Preserved analysis 1 transcript')).toHaveValue('T2')
  fireEvent.click(screen.getByRole('button',{name:'Load preserved sources'}))
  await screen.findByText(/no longer available/)
  expect(screen.getByLabelText('Preserved analysis 1 source')).toHaveValue('B')
  expect(screen.getByLabelText('Preserved analysis 1 transcript')).toHaveValue('T1')
})

test('refresh retains an older selected source without changing the server page offset',async()=>{
  const source=(i:number)=>({id:`source-${i}`,origin:'current_api',releases:[116],
    query:{chromosome:'1',position:1,ref:'C',alt:'T'},
    transcripts:[{transcript_id:'T1',consequence_terms:['intron_variant']},{transcript_id:'T2',consequence_terms:['intron_variant']}]})
  const fetchMock=vi.fn().mockImplementation(async(url:string)=>{
    if(url.includes('/records/source-200'))return {ok:true,json:async()=>source(200)}
    return {ok:true,json:async()=>url.includes('offset=200')?[source(200)]:Array.from({length:200},(_,i)=>source(i))}
  })
  vi.stubGlobal('fetch',fetchMock)
  render(<HistoricalPanel onCompare={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button',{name:'Load preserved sources'}))
  await screen.findByRole('button',{name:'Load older sources'})
  fireEvent.click(screen.getByRole('button',{name:'Load older sources'}))
  await waitFor(()=>expect(screen.getByLabelText('Preserved analysis 1 source').querySelectorAll('option')).toHaveLength(201))
  fireEvent.change(screen.getByLabelText('Preserved analysis 1 source'),{target:{value:'source-200'}})
  fireEvent.change(screen.getByLabelText('Preserved analysis 1 transcript'),{target:{value:'T2'}})
  fireEvent.click(screen.getByRole('button',{name:'Load preserved sources'}))
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith('/api/sources/ensembl/records/source-200'))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Load older sources'})).toBeEnabled())
  expect(screen.getByLabelText('Preserved analysis 1 source')).toHaveValue('source-200')
  expect(screen.getByLabelText('Preserved analysis 1 transcript')).toHaveValue('T2')
  expect(screen.queryByText(/no longer available/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Load older sources'}))
  await waitFor(()=>expect(fetchMock).toHaveBeenLastCalledWith('/api/sources/records?offset=200&limit=200'))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Load preserved sources'})).toBeEnabled())
  expect(screen.getByLabelText('Preserved analysis 1 source').querySelectorAll('option')).toHaveLength(201)
})
