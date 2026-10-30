import {cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import EvidenceInspector from './EvidenceInspector'
import DraftTools from './DraftTools'
import {reportHtml} from './ReadableReport'
import {readRoute} from './routing'
import type {Result} from './types'

const result={id:'example',engine_version:'0.6.5',input:{title:'Comparison',synthetic:true,snapshots:[]},identity:{status:'verified',explanation:'Supplied contexts match',evidence_ids:['diff-1']},differences:[],findings:[],evidence:[{id:'diff-1',kind:'field_comparison',description:'Observed effect',data:{field:'consequence',a:'missense_variant',b:'intron_variant'}}],input_sha256:'a'.repeat(64)} as Result
afterEach(cleanup)

test('evidence explains the recorded values with raw data optional',()=>{
  render(<EvidenceInspector result={result} selected={null} onSelect={vi.fn()}/> )
  expect(screen.getByRole('heading',{name:'Predicted effect changed'})).toBeInTheDocument()
  expect(screen.getByText(/A predicted change to an amino acid/)).toBeInTheDocument()
  const summary=screen.getByText('Original record (JSON and technical ID)')
  expect(summary.parentElement).not.toHaveAttribute('open')
})

test('draft persistence happens only on an explicit save and can be discarded',()=>{
  const restore=vi.fn()
  render(<DraftTools text='{"title":"draft"}' onRestore={restore} onUndo={vi.fn()} onRedo={vi.fn()} canUndo={false} canRedo={false}/> )
  expect(localStorage.length).toBe(0)
  fireEvent.click(screen.getByRole('button',{name:'Save draft locally'}))
  expect(localStorage.length).toBe(1)
  fireEvent.click(screen.getByRole('button',{name:'Resume saved draft'}))
  expect(restore).toHaveBeenCalledWith('{"title":"draft"}')
  fireEvent.click(screen.getByRole('button',{name:'Discard saved draft'}))
  expect(localStorage.length).toBe(0)
})

test('readable reports escape all supplied markup and remain self contained',()=>{
  const html=reportHtml({...result,input:{...result.input,title:'<script>alert(1)</script>'}})
  expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  expect(html).not.toContain('<script>')
  expect(html).toContain('Technical appendix')
})

test('routes resolve local saved comparisons without accepting arbitrary identifiers',()=>{
  expect(readRoute('#/comparison/abc123/evidence')).toEqual({id:'abc123',tab:'evidence'})
  expect(readRoute('#/library')).toEqual({id:null,tab:'library'})
  expect(readRoute('#/comparison/<script>/overview')).toEqual({id:null,tab:'overview'})
  expect(readRoute('#/comparison/abc123/unknown')).toEqual({id:'abc123',tab:'overview'})
})
