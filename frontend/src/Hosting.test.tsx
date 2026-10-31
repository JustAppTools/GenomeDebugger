import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import App from './App'
import LocalDataPanel from './LocalDataPanel'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})
const ok=(body:unknown)=>({ok:true,json:async()=>body})

test('public preview clearly describes server processing and temporary per-browser storage',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>ok(url.endsWith('/health')?{version:'0.6.7',hosted:true}:[])))
  render(<App/> )
  expect(await screen.findByLabelText('Public preview storage')).toHaveTextContent('Free hosting can clear saved work')
  expect(screen.getByLabelText('Public preview storage')).toHaveTextContent('This browser has its own workspace')
  expect(screen.getByText('Preview engine connected')).toBeInTheDocument()
  expect(screen.queryByText('Works locally. Public-source requests are made only when you choose Fetch, Check, or Resolve.')).not.toBeInTheDocument()
})

test('hosted data view offers bundle transfer instead of desktop shutdown or restore controls',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>ok({hosted:true,desktop_mode:false,database_path:'Temporary workspace for this browser',used_bytes:100,file_bytes:100,max_db_bytes:16000000,app_version:'0.9.0',engine_version:'0.6.7',schema_version:3,counts:{investigations:0}})))
  render(<LocalDataPanel/> )
  expect(await screen.findByRole('heading',{name:'Your temporary browser workspace'})).toBeInTheDocument()
  expect(screen.getByRole('heading',{name:'Keep and transfer your comparisons'})).toBeInTheDocument()
  expect(screen.queryByRole('heading',{name:'Restore a backup'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Stop application'})).not.toBeInTheDocument()
  expect(screen.getByText(/Inputs and file previews are processed on this server/)).toBeInTheDocument()
})

test('public help describes browser-scoped links rather than localhost links',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>ok(url.endsWith('/health')?{version:'0.6.7',hosted:true}:[])))
  render(<App/> )
  await screen.findByLabelText('Public preview storage')
  fireEvent.click(screen.getByRole('link',{name:'Guide'}))
  await waitFor(()=>expect(screen.getByText(/A workspace link opens only with this browser/)).toBeInTheDocument())
})
