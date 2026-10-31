import {openWorkspaceAdvanced,openWorkspaceInputs,openWorkspaceSources} from './workspace-helpers'
import {openSourceTools,prepareGuided} from './workspace-helpers'
import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import path from 'node:path'

const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
async function sourcePage(page:Page) {
  const bundle=JSON.parse(execFileSync(python,['e2e/reference-bundle.py'],{encoding:'utf8'}))
  expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
  const source=bundle.entries.source_record
  await page.route('**/api/sources/ensembl/lookup',route=>route.fulfill({json:{record:source,access:'cache'}}))
  await page.goto('/')
  await openWorkspaceSources(page)
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await openSourceTools(page,'snpeff')
  await page.getByLabel('SnpEff annotated VCF').waitFor()
  return source
}
function newer(source:any) {
  const code=`
import sys,json,hashlib,tempfile
from pathlib import Path
sys.path.insert(0,'../backend')
from app.ensembl import SourceRecord,comparison_input,CompareTranscripts
from app.engine import compare
from app.storage import save_source_record
from app.bundle import create_bundle
source=SourceRecord.model_validate_json(sys.argv[1])
source.retrieved_at='2026-10-21T12:00:00+00:00'
source.id=hashlib.sha256(json.dumps({'query':source.query.model_dump(),'release':source.releases,'assembly':source.assembly_accession,'raw':source.source_response_sha256,'retrieved_at':source.retrieved_at},sort_keys=True).encode()).hexdigest()[:20]
payload=comparison_input(source,CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,transcript_b=source.transcripts[1].transcript_id))
with tempfile.TemporaryDirectory() as folder:
 db=Path(folder)/'probe.db'
 save_source_record(db,source)
 print(json.dumps(create_bundle(db,compare(payload))))
`
  return JSON.parse(execFileSync(python,['-c',code,JSON.stringify(source)],{encoding:'utf8'}))
}

test('a new capture cannot discard a draft typed after the lookup started',async({page})=>{
  const source=await sourcePage(page)
  const second=newer(source)
  expect((await page.request.post('/api/bundles/import',{data:second})).ok()).toBe(true)
  await page.unroute('**/api/sources/ensembl/lookup')
  let release:()=>void=()=>{},waiting=false
  await page.route('**/api/sources/ensembl/lookup',async route=>{
    waiting=true;await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({json:{record:second.entries.source_record,access:'fetched'}})
  })
  await page.getByRole('button',{name:'Fetch current from Ensembl',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  await openSourceTools(page,'snpeff')
  await page.getByLabel('SnpEff annotated VCF').fill('Keep the newer VCF draft')
  release()
  await expect(page.getByRole('status')).toContainText('Your newer draft and selections were kept')
  await openSourceTools(page,'snpeff')
  await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue('Keep the newer VCF draft')
})

test('a cached lookup preserves transcript choices made while it was pending',async({page})=>{
  const source=await sourcePage(page)
  await page.unroute('**/api/sources/ensembl/lookup')
  let release:()=>void=()=>{},waiting=false
  await page.route('**/api/sources/ensembl/lookup',async route=>{
    waiting=true;await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({json:{record:source,access:'cache'}})
  })
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  const choice=source.transcripts.at(-1).transcript_id
  await page.getByLabel('Analysis A transcript',{exact:true}).selectOption(choice)
  release()
  await expect(page.getByRole('status')).toContainText('Your newer draft and selections were kept')
  await expect(page.getByLabel('Analysis A transcript',{exact:true})).toHaveValue(choice)
})

test('VCF replacement invalidates older checks and blocks checking during the read',async({page})=>{
  const source=await sourcePage(page),q=source.query
  const ann=source.transcripts.map((row:any)=>`${q.alt}|${row.consequence_terms.join('&')}|MODERATE|G|${row.gene_id}|transcript|${row.transcript_id}`).join(',')
  const original=`${q.chromosome}\t${q.position}\t.\t${q.ref}\t${q.alt}\t.\tPASS\tANN=${ann}`
  const changed=original.replace(source.transcripts[0].consequence_terms.join('&'),'missense_variant')
  await page.getByLabel('SnpEff version',{exact:true}).fill('regression')
  await page.getByLabel('SnpEff genome database').fill('regression')
  await page.getByLabel('SnpEff database SHA-256').fill('a'.repeat(64))
  await openSourceTools(page,'snpeff')
  await page.getByLabel('SnpEff annotated VCF').fill(original)
  await openSourceTools(page,'snpeff')
  await page.getByRole('button',{name:'Compare SnpEff output',exact:true}).click()
  await expect(page.locator('.snpeff-result strong')).toHaveText('AGREE')
  await page.evaluate(()=>{
    const original=File.prototype.arrayBuffer
    File.prototype.arrayBuffer=async function(){
      const bytes=await original.call(this)
      if(this.name==='slow.vcf')await new Promise<void>(resolve=>{(window as any).releaseNewVcf=resolve})
      return bytes
    }
  })
  await page.getByLabel('Import annotated VCF').setInputFiles({name:'slow.vcf',mimeType:'text/plain',buffer:Buffer.from(changed)})
  await expect.poll(()=>page.evaluate(()=>Boolean((window as any).releaseNewVcf))).toBe(true)
  await openSourceTools(page,'snpeff')
  await expect(page.getByRole('button',{name:'Compare SnpEff output',exact:true})).toBeDisabled()
  await expect(page.getByRole('button',{name:'Load saved comparison',exact:true})).toBeDisabled()
  await expect(page.locator('.snpeff-result')).toHaveCount(0)
  await page.evaluate(()=>(window as any).releaseNewVcf())
  await openSourceTools(page,'snpeff')
  await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue(changed)
  await openSourceTools(page,'snpeff')
  await expect(page.getByRole('button',{name:'Compare SnpEff output',exact:true})).toBeEnabled()
  await expect(page.locator('.snpeff-result')).toHaveCount(0)
  const checked=page.waitForResponse(r=>r.url().endsWith('/snpeff-check')&&r.request().method()==='POST')
  await openSourceTools(page,'snpeff')
  await page.getByRole('button',{name:'Compare SnpEff output',exact:true}).click()
  const saved=await(await checked).json()
  expect(saved.vcf_text).toBe(changed)
  expect(saved.status).toBe('disagree')
  await expect(page.locator('.snpeff-result strong')).toHaveText('DISAGREE')
  const compared=page.waitForResponse(r=>r.url().endsWith(`/${source.id}/compare`))
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  expect((await(await compared).json()).input.annotation_check.id).toBe(saved.id)
})

test('a delayed initial list preserves a newly saved comparison in Recent',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title=`Recent response regression ${Date.now()}`
  const releases:(()=>void)[]=[]
  let completed=0
  await page.route('**/api/investigations',async route=>{
    if(route.request().method()!=='GET'){await route.continue();return}
    const response=await route.fetch()
    await new Promise<void>(resolve=>{releases.push(resolve)})
    await route.fulfill({response});completed++
  })
  await page.goto('/')
  await expect.poll(()=>releases.length).toBeGreaterThan(0)
  await openWorkspaceInputs(page)
  await prepareGuided(page)
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  await page.getByLabel('Investigation JSON').fill(JSON.stringify(input))
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Compared analyses'})).toBeVisible()
  await page.getByRole('button',{name:'GenomeDebugger home'}).click()
  await expect(page.getByRole('region',{name:'Recent comparisons'})).toContainText(input.title)
  releases.forEach(release=>release())
  await expect.poll(()=>completed).toBe(releases.length)
  await expect(page.getByRole('region',{name:'Recent comparisons'})).toContainText(input.title)
})

test('older failed health requests cannot override a newer successful poll',async({page})=>{
  const healthy=await(await page.request.get('/api/health')).json()
  await page.clock.install()
  let hold=true,completed=0
  const releases:(()=>void)[]=[]
  await page.route('**/api/health',async route=>{
    if(hold){
      await new Promise<void>(resolve=>{releases.push(resolve)})
      await route.fulfill({status:503,json:{detail:'Older failure'}}).catch(()=>{})
      completed++
    } else await route.fulfill({json:healthy})
  })
  await page.goto('/')
  await expect.poll(()=>releases.length).toBeGreaterThan(0)
  hold=false
  await page.clock.fastForward(15001)
  await expect(page.locator('.local-badge')).toHaveText('Local engine connected')
  releases.forEach(release=>release())
  await expect.poll(()=>completed).toBe(releases.length)
  await expect(page.locator('.local-badge')).toHaveText('Local engine connected')
})

test('library forward and backward paging stays stable during another client save',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  const prefix=`Stable library regression ${Date.now()} `
  for(let i=0;i<51;i++)expect((await page.request.post('/api/investigations',{data:{...input,title:prefix+i}})).ok()).toBe(true)
  await page.goto('/')
  await page.getByRole('link',{name:'Saved work',exact:true}).click()
  await page.getByLabel('Search investigations').fill(prefix)
  await expect(page.locator('.library-row')).toHaveCount(50)
  await expect(page.locator('.library-row').first()).toContainText(prefix+'50')
  const firstPage=await page.locator('.library-row strong').allTextContents()
  expect((await page.request.post('/api/investigations',{data:{...input,title:prefix+'concurrent'}})).ok()).toBe(true)
  await page.getByRole('button',{name:'Next records',exact:true}).click()
  await expect(page.locator('.library-row')).toHaveCount(1)
  await expect(page.locator('.library-row strong')).toHaveText(prefix+'0')
  await page.getByRole('button',{name:'Previous records',exact:true}).click()
  await expect(page.locator('.library-row')).toHaveCount(50)
  expect(await page.locator('.library-row strong').allTextContents()).toEqual(firstPage)
  await page.getByRole('button',{name:'Refresh records',exact:true}).click()
  await expect(page.locator('.library-row').first().locator('strong')).toHaveText(prefix+'concurrent')
})

test('baselines saved from two tabs both remain accessible with their own histories',async({page,context})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title=`Multiple baseline regression ${Date.now()}`
  const result=await(await page.request.post('/api/investigations',{data:input})).json()
  const second=await context.newPage()
  for(const view of [page,second]){
    await view.goto('/')
    await view.getByRole('link',{name:'Saved work',exact:true}).click()
    await view.getByLabel('Search investigations').fill(result.id)
    await view.locator('.library-row').filter({hasText:result.id}).getByRole('button',{name:'Open',exact:true}).click()
    await view.getByRole('heading',{name:'Compared analyses',exact:true}).waitFor()
    await openWorkspaceAdvanced(view,'Saved tests')
    await expect(view.getByRole('button',{name:'Save regression case',exact:true})).toBeEnabled()
  }
  await page.getByLabel('Test name').fill('First baseline with history')
  const response=page.waitForResponse(r=>r.url().endsWith('/regression-cases')&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Save regression case',exact:true}).click()
  const first=await(await response).json()
  await page.getByRole('button',{name:'Run pinned baseline',exact:true}).click()
  await expect(page.locator('.history-list button')).toHaveCount(1)
  await second.getByLabel('Test name').fill('Second baseline without history')
  await second.getByRole('button',{name:'Save regression case',exact:true}).click()
  await expect(second.locator('.case-record')).toContainText('Second baseline without history')
  await page.getByRole('button',{name:'Refresh baselines',exact:true}).click()
  await expect(page.getByLabel('Saved baseline').locator('option')).toHaveCount(2)
  await expect(page.locator('.case-record')).toContainText('First baseline with history')
  const options=await page.getByLabel('Saved baseline').locator('option').evaluateAll(nodes=>nodes.map(node=>(node as HTMLOptionElement).value))
  const other=options.find(id=>id!==first.id)!
  await page.getByLabel('Saved baseline').selectOption(other)
  await expect(page.locator('.case-record')).toContainText('Second baseline without history')
  await expect(page.locator('.history-list button')).toHaveCount(0)
  await page.getByLabel('Saved baseline').selectOption(first.id)
  await expect(page.locator('.case-record')).toContainText('First baseline with history')
  await expect(page.locator('.history-list button')).toHaveCount(1)
  await second.close()
})
