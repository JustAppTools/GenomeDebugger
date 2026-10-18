import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import InvestigationLibrary from './InvestigationLibrary'
import HistoricalPanel from './HistoricalPanel'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})

test('older investigations remain reachable and searching resets the page',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>{
    const query=new URL(url,'http://localhost').searchParams
    const offset=Number(query.get('offset'))
    const count=query.get('q')?1:offset?1:101
    return {ok:true,json:async()=>Array.from({length:count},(_,i)=>({id:`id-${offset+i}`,title:`Record ${offset+i}`}))}
  }))
  render(<InvestigationLibrary onOpen={vi.fn()} onDeleted={vi.fn()} onImport={vi.fn()}/>)
  await screen.findByText('Record 0')
  fireEvent.click(screen.getByRole('button',{name:'Next records'}))
  await screen.findByText('Record 100')
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
