import {act,cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import AnimatedReplay,{replaySteps} from './AnimatedReplay'
import type {Result} from './types'

const snapshot={id:'A',label:'A',variant:{assembly:'GRCh38',sequence_id:'1',position:2,ref:'C',alt:'T'},annotation:{gene_id:'G',transcript_id:'T1',consequence:'intron_variant'},provenance:{tool:'fixture',tool_version:'1',source_name:'fixture',source_release:'1',configuration:{}}}
const result={id:'example',input:{title:'Training',synthetic:true,snapshots:[snapshot,{...snapshot,id:'B',annotation:{...snapshot.annotation,transcript_id:'T2'}}]},identity:{status:'verified',explanation:'Only supplied context was checked.',evidence_ids:['identity-inputs']},differences:[{field:'transcript_id',category:'annotation',before:'T1',after:'T2',meaningful:true,evidence_ids:['diff-1']}],findings:[],evidence:[{id:'identity-inputs',kind:'input',description:'Alleles',data:{}},{id:'diff-1',kind:'field_comparison',description:'Transcripts',data:{}}],input_sha256:'hash'} as Result
afterEach(()=>{cleanup();vi.useRealTimers()})

test('pauses at the first observed difference and continues on demand',()=>{
  vi.useFakeTimers()
  render(<AnimatedReplay result={result} onEvidence={vi.fn()}/> )
  fireEvent.click(screen.getByRole('button',{name:'Play replay'}))
  act(()=>vi.advanceTimersByTime(1600))
  expect(screen.getByRole('heading',{name:'Do the allele descriptions line up?'})).toBeInTheDocument()
  act(()=>vi.advanceTimersByTime(1600))
  expect(screen.getByText('Paused at an observed difference.')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Play replay'})).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Play replay'}))
  act(()=>vi.advanceTimersByTime(1600))
  expect(screen.getByRole('heading',{name:'Where do the predictions diverge?'})).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Restart replay'}))
  expect(screen.getByText('Step 1 of 5')).toBeInTheDocument()
})

test('manual steps link to recorded evidence and clean up playback on unmount',()=>{
  vi.useFakeTimers()
  const inspect=vi.fn()
  const view=render(<AnimatedReplay result={result} onEvidence={inspect}/> )
  fireEvent.click(screen.getByRole('button',{name:'Replay stage 2: Reference'}))
  fireEvent.click(screen.getByRole('button',{name:'Inspect identity-inputs'}))
  expect(inspect).toHaveBeenCalledWith('identity-inputs')
  fireEvent.click(screen.getByRole('button',{name:'Play replay'}))
  view.unmount()
  expect(vi.getTimerCount()).toBe(0)
})

test('missing identity evidence stays unresolved and is not rendered as a tool execution',()=>{
  const steps=replaySteps({...result,identity:{...result.identity,status:'unresolved'}})
  expect(steps[1].signal).toBe('open')
  expect(steps[4].signal).toBe('open')
})
