import {cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import ResultsSummary,{explainResult} from './ResultsSummary'
import type {Result} from './types'

const result={id:'one',input:{title:'Example',synthetic:true,snapshots:[]},identity:{status:'verified',explanation:'Supplied context matches',evidence_ids:['identity']},differences:[{field:'position',category:'representation',before:'1',after:'2',meaningful:false,evidence_ids:['diff']}],findings:[{status:'verified',cause:'transcript selection',explanation:'Example replay',affected_fields:[],evidence_ids:['identity']}],evidence:[{id:'identity',kind:'input',description:'Inputs',data:{}}],input_sha256:'hash'} as Result
afterEach(cleanup)

test('explains a synthetic result without upgrading local identity or medical significance',()=>{
  render(<ResultsSummary result={result} onChanges={vi.fn()} onEvidence={vi.fn()}/> )
  expect(screen.getByText('An explanation was reproduced within this made-up example.')).toBeInTheDocument()
  expect(screen.getByText('Matching supplied text alone does not independently verify a reference genome.')).toBeInTheDocument()
  expect(screen.getByText('1 value changed; 0 marked important by the comparison rules.')).toBeInTheDocument()
  expect(screen.getByText('“Important” describes the comparison settings, not medical significance.')).toBeInTheDocument()
})

test('uncertain findings remain uncertain in the simplified explanation',()=>{
  const open={...result,identity:{...result.identity,status:'unresolved' as const},findings:[{...result.findings[0],status:'possible' as const}]}
  expect(explainResult(open).identity).toContain('not enough information')
  expect(explainResult(open).explanation).toContain('has not been proved')
  expect(explainResult({...open,findings:[]}).explanation).toContain('does not establish why')
})

test('keeps underlying changes and evidence reachable and terms optional',()=>{
  const changes=vi.fn(),evidence=vi.fn()
  render(<ResultsSummary result={result} onChanges={changes} onEvidence={evidence}/> )
  expect(screen.getByText('Explain the terms').parentElement).not.toHaveAttribute('open')
  fireEvent.click(screen.getByRole('button',{name:'See the changes'}))
  fireEvent.click(screen.getByRole('button',{name:'How was this checked?'}))
  expect(changes).toHaveBeenCalledOnce()
  expect(evidence).toHaveBeenCalledWith('identity')
})
