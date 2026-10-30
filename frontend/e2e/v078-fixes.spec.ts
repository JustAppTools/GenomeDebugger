import {openSourceTools,prepareExample} from './workspace-helpers'
import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import {readFile} from 'node:fs/promises'
import path from 'node:path'

const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
async function sourcePage(page:Page) {
  const bundle=JSON.parse(execFileSync(python,['e2e/reference-bundle.py','agree'],{encoding:'utf8'}))
  expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
  const source=bundle.entries.source_record
  await page.route('**/api/sources/ensembl/lookup',route=>route.fulfill({json:{record:source,access:'cache'}}))
  await page.goto('/')
  await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await openSourceTools(page,'snpeff')
  await page.getByLabel('SnpEff annotated VCF').waitFor()
  return source
}
async function openSaved(page:Page,id:string) {
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill(id)
  await page.locator('.library-row').filter({hasText:id}).getByRole('button',{name:'Open',exact:true}).click()
  await page.getByRole('heading',{name:'Compared analyses',exact:true}).waitFor()
}

test('a harmless heading click does not discard a completed source comparison',async({page})=>{
  const source=await sourcePage(page)
  let release:()=>void=()=>{},waiting=false
  await page.route(`**/api/sources/ensembl/records/${source.id}/compare`,async route=>{
    const response=await route.fetch();waiting=true
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  await page.getByRole('heading',{name:'Choose two transcripts',exact:true}).click()
  release()
  await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toBeVisible()
})

test('a harmless heading click permits a pending lookup to finish',async({page})=>{
  const source=await sourcePage(page)
  await page.unroute('**/api/sources/ensembl/lookup')
  let release:()=>void=()=>{},waiting=false
  await page.route('**/api/sources/ensembl/lookup',async route=>{
    waiting=true;await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({json:{record:source,access:'fetched'}})
  })
  await page.getByRole('button',{name:'Fetch current from Ensembl',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  await page.getByRole('heading',{name:'Choose two transcripts',exact:true}).click()
  release()
  await expect(page.getByText(/Fetched and cached · Retrieved/)).toBeVisible()
  await expect(page.getByRole('status').filter({hasText:'source workspace changed'})).toHaveCount(0)
})

test('an asynchronous historical file commit still protects its newer draft',async({page})=>{
  const source=await sourcePage(page)
  await openSourceTools(page,'history')
  await page.getByText('Import historical VEP output',{exact:true}).click()
  await page.getByLabel('Historical Ensembl release').fill('100')
  await page.getByLabel('Historical VEP version').fill('historical-fixture')
  await page.getByLabel('Historical run time').fill('2024-01-01T12:00')
  await page.getByLabel('Historical artifact source').fill('preserved test fixture')
  await page.evaluate(()=>{
    const original=File.prototype.arrayBuffer
    File.prototype.arrayBuffer=async function(){
      const bytes=await original.call(this)
      if(this.name==='pending-history.json')await new Promise<void>(resolve=>{(window as any).finishHistoricalFile=resolve})
      return bytes
    }
  })
  await page.getByLabel('Historical VEP JSON file').setInputFiles({name:'pending-history.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(source.source_response))})
  await expect.poll(()=>page.evaluate(()=>Boolean((window as any).finishHistoricalFile))).toBe(true)
  let release:()=>void=()=>{},waiting=false
  await page.route(`**/api/sources/ensembl/records/${source.id}/compare`,async route=>{
    const response=await route.fetch();waiting=true
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  await page.evaluate(()=>(window as any).finishHistoricalFile())
  await expect(page.getByRole('button',{name:'Preserve historical output',exact:true})).toBeEnabled()
  release()
  await expect(page.getByRole('status').filter({hasText:'Source workspace changed'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Preserve historical output',exact:true})).toBeEnabled()
  await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toHaveCount(0)
})

for(const kind of ['report.md','bundle']) {
  test(`an old failed ${kind} export does not put an error on a newer screen`,async({page})=>{
    await page.goto('/')
    await prepareExample(page)
    await page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/}).first().click()
    await page.getByRole('heading',{name:'Compared analyses',exact:true}).waitFor()
    let release:()=>void=()=>{},waiting=false,completed=false
    await page.route(`**/api/investigations/*/${kind}`,async route=>{
      waiting=true;await new Promise<void>(resolve=>{release=resolve})
      await route.fulfill({status:409,json:{detail:'Earlier export failed'}});completed=true
    })
    if(kind!=='bundle')await page.getByText('Other export formats',{exact:true}).click()
    await page.getByRole('button',{name:kind==='bundle'?'Full bundle':'Text report',exact:true}).click()
    await expect.poll(()=>waiting).toBe(true)
    await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
    release()
    await expect.poll(()=>completed).toBe(true)
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(page.getByRole('heading',{name:'Ensembl VEP · current GRCh38',exact:true})).toBeVisible()
  })
}

test('a completed older bundle still downloads without replacing newer screen feedback',async({page})=>{
  const code=`
import sys,json
from pathlib import Path
sys.path.insert(0,'../backend')
from app.models import InvestigationInput
from app.legacy_engine_v064 import compare
from app.engine import digest
payload=InvestigationInput.model_validate_json(Path('../fixtures/transcript-switch.json').read_text())
result=compare(payload)
entries={'investigation':result.model_dump(mode='json')}
print(json.dumps({'format':'GenomeDebugger bundle','version':2,'engine_version':'0.6.4','entries':entries,'sha256':{'investigation':digest(entries['investigation'])}}))
`
  const bundle=JSON.parse(execFileSync(python,['-c',code],{encoding:'utf8'}))
  expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
  await openSaved(page,bundle.entries.investigation.id)
  let release:()=>void=()=>{},waiting=false
  await page.route('**/api/investigations/*/bundle',async route=>{
    const response=await route.fetch();waiting=true
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.getByRole('button',{name:'Full bundle',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
  const download=page.waitForEvent('download')
  release()
  expect((await download).suggestedFilename()).toContain('-bundle.json')
  await expect(page.getByRole('status').filter({hasText:'This older investigation was replayed'})).toHaveCount(0)
})

test('bundle download and import preserve finite numeric metadata exactly',async({page})=>{
  const fixture=JSON.parse(execFileSync(python,['e2e/reference-bundle.py'],{encoding:'utf8'}))
  const source=fixture.entries.source_record
  const raw=JSON.stringify(source.source_response).slice(0,-1)+',"extension":{"whole":1.0,"large":9007199254740993}}'
  const imported=await page.request.post('/api/sources/historical-vep',{data:{
    query:source.query,raw_json:raw,source_release:110,tool_version:'numeric-browser-fixture',
    generated_at:'2024-01-01T00:00:00Z',assembly_accession:source.assembly_accession,source_uri:'numeric browser fixture'}})
  expect(imported.ok()).toBe(true)
  const id=(await imported.json()).id
  const compared=await page.request.post('/api/sources/compare',{data:{source_a:id,source_b:id,
    transcript_a:source.transcripts[0].transcript_id,transcript_b:source.transcripts[1].transcript_id}})
  expect(compared.ok()).toBe(true)
  const result=await compared.json()
  await openSaved(page,result.id)
  const pending=page.waitForEvent('download')
  await page.getByRole('button',{name:'Full bundle',exact:true}).click()
  const downloaded=await pending
  const content=await readFile((await downloaded.path())!,'utf8')
  const verified=await page.request.post('/api/bundles/verify',{data:content,headers:{'Content-Type':'application/json'}})
  expect(verified.status(),await verified.text()).toBe(200)
  expect(content).toContain('"whole":1.0')
  expect(content).toContain('"large":9007199254740993')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  const completed=page.waitForResponse(r=>r.url().endsWith('/api/bundles/import')&&r.request().method()==='POST')
  await page.getByLabel('Import replay-checked bundle').setInputFiles({name:'numeric-bundle.json',mimeType:'application/json',buffer:Buffer.from(content)})
  expect((await completed).status()).toBe(200)
  await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('guided custom candidates submit valid provenance and retain their baseline',async({page})=>{
  const source=await sourcePage(page),q=source.query
  await openSourceTools(page,'ncbi')
  await page.getByRole('button',{name:'Load saved check',exact:true}).click()
  await expect(page.locator('.reference-result')).toBeVisible()
  const ann=source.transcripts.map((row:any)=>`${q.alt}|${row.consequence_terms.join('&')}|MODIFIER|G|${row.gene_id}|transcript|${row.transcript_id}`).join(',')
  const checked=await page.request.post(`/api/sources/ensembl/records/${source.id}/snpeff-check`,{data:{
    vcf_text:`${q.chromosome}\t${q.position}\t.\t${q.ref}\t${q.alt}\t.\tPASS\tANN=${ann}`,
    snpeff_version:'browser-fixture',genome_database:'browser-fixture',database_sha256:'a'.repeat(64)}})
  expect(checked.ok()).toBe(true)
  await openSourceTools(page,'snpeff')
  await page.getByRole('button',{name:'Load saved comparison',exact:true}).click()
  await expect(page.locator('.snpeff-result strong')).toHaveText('AGREE')
  const completed=page.waitForResponse(r=>r.url().endsWith(`/${source.id}/compare`))
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  const result=await(await completed).json()
  expect(result.input.reference_check).toBeTruthy()
  expect(result.input.annotation_check).toBeTruthy()
  const created=await page.request.post(`/api/investigations/${result.id}/regression-cases`,{data:{name:'Custom candidate browser regression'}})
  const saved=await created.json()
  expect(created.ok()).toBe(true)
  await page.getByRole('button',{name:'Saved tests',exact:true}).first().click()
  await expect(page.getByLabel('Candidate analysis 1 consequence',{exact:true})).toBeDisabled()
  await page.getByRole('button',{name:'Use custom output for analysis A',exact:true}).click()
  await page.getByLabel('Candidate analysis 1 consequence',{exact:true}).fill('missense_variant')
  await page.getByLabel('Candidate analysis 1 tool name',{exact:true}).fill('My candidate pipeline')
  const runResponse=page.waitForResponse(r=>r.url().endsWith(`/${saved.id}/runs`)&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Check candidate',exact:true}).click()
  const response=await runResponse,run=await response.json()
  expect(response.status()).toBe(200)
  expect(run.status).toBe('failed')
  expect(run.checks.some((check:any)=>check.path==='snapshots[0].annotation.consequence'&&!check.passed)).toBe(true)
  expect(run.actual.input.snapshots[0].provenance.tool).toBe('My candidate pipeline')
  expect(run.actual.input.snapshots[0].provenance.configuration.source_record_id).toBe(source.id)
  expect(run.actual.input.snapshots[0].provenance.input_sha256).toBe(source.source_response_sha256)
  expect(run.actual.input.reference_check).toEqual(result.input.reference_check)
  expect(run.actual.input.annotation_check).toBeNull()
  for(const snapshot of run.actual.input.snapshots){
    expect(snapshot.provenance.configuration.annotation_check_id).toBeUndefined()
    expect(snapshot.provenance.configuration.annotation_check_status).toBeUndefined()
    expect(snapshot.provenance.configuration.annotation_check_origin).toBeUndefined()
  }
  const baseline=await(await page.request.get(`/api/regression-cases/${saved.id}`)).json()
  expect(baseline.source_investigation.input).toEqual(result.input)
  await expect(page.getByRole('heading',{name:'Regression failed',exact:true})).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('manual Unicode test names use the same 200-character limit as the API',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title=`Unicode name regression ${Date.now()}`
  const result=await(await page.request.post('/api/investigations',{data:input})).json()
  await openSaved(page,result.id)
  await page.getByRole('button',{name:'Saved tests',exact:true}).first().click()
  await expect(page.getByRole('button',{name:'Save regression case',exact:true})).toBeEnabled()
  const name='🧬'.repeat(110)
  await page.getByLabel('Test name',{exact:true}).fill('')
  await page.getByLabel('Test name',{exact:true}).pressSequentially(name)
  await expect(page.getByLabel('Test name',{exact:true})).toHaveValue(name)
  const created=page.waitForResponse(r=>r.url().endsWith(`/${result.id}/regression-cases`)&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Save regression case',exact:true}).click()
  const response=await created
  expect(response.ok()).toBe(true)
  expect((await response.json()).name).toBe(name)
})

test('library search supports Unicode case pairs and long supplementary text',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  const prefix=`Unicode search regression ${Date.now()} `
  for(const title of [prefix+'Café export',prefix+'CAFÉ export',prefix+'🧬'.repeat(110)]){
    expect((await page.request.post('/api/investigations',{data:{...input,title}})).ok()).toBe(true)
  }
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill(prefix+'café')
  await expect(page.locator('.library-row')).toHaveCount(2)
  await page.getByLabel('Search investigations').fill('')
  const query=prefix+'🧬'.repeat(110)
  await page.getByLabel('Search investigations').pressSequentially(query)
  await expect(page.getByLabel('Search investigations')).toHaveValue(query)
  await expect(page.locator('.library-row')).toHaveCount(1)
  await expect(page.locator('.library-row strong')).toHaveText(query)
})

test('library snapshot excludes inserts after another client deletes the newest record',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  const prefix=`Deletion snapshot regression ${Date.now()} `
  let latest=''
  for(let i=0;i<51;i++){
    const response=await page.request.post('/api/investigations',{data:{...input,title:prefix+i}})
    expect(response.ok()).toBe(true);latest=(await response.json()).id
  }
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill(prefix)
  await expect(page.locator('.library-row')).toHaveCount(50)
  expect((await page.request.delete('/api/investigations/'+latest)).ok()).toBe(true)
  expect((await page.request.post('/api/investigations',{data:{...input,title:prefix+'concurrent'}})).ok()).toBe(true)
  await page.getByRole('button',{name:'Next records',exact:true}).click()
  await expect(page.locator('.library-row strong')).toHaveText(prefix+'0')
  await page.getByRole('button',{name:'Previous records',exact:true}).click()
  await expect(page.locator('.library-row')).toHaveCount(50)
  await expect(page.locator('.library-list')).not.toContainText(prefix+'concurrent')
  await page.getByRole('button',{name:'Refresh records',exact:true}).click()
  await expect(page.locator('.library-row strong').first()).toHaveText(prefix+'concurrent')
})
