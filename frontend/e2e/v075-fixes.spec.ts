import {openWorkspaceAdvanced,openWorkspaceSources} from './workspace-helpers'
import {openSourceTools,prepareExample} from './workspace-helpers'
import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import path from 'node:path'

const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
async function seed(page:Page) {
  const bundle=JSON.parse(execFileSync(python,['e2e/reference-bundle.py'],{encoding:'utf8'}))
  expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
  return bundle
}
async function settle(page:Page) {
  await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))))
}

for(const action of ['comparison','demo','open','bundle'] as const) {
  test(`a pending root ${action} cannot discard newer source drafts`,async({page})=>{
    const bundle=await seed(page)
    await page.goto('/')
    if(action==='comparison') {
      await prepareExample(page)
      await page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/}).first().click()
      await page.getByRole('heading',{name:'Compared analyses',exact:true}).waitFor()
    }
    let release:()=>void=()=>{},waiting=false
    const url=action==='demo'?'/api/demos/transcript-switch':action==='open'
      ?`/api/investigations/${bundle.entries.investigation.id}`:action==='bundle'?'/api/bundles/import':'/api/investigations'
    await page.route(`**${url}`,async route=>{
      if(action==='comparison'&&route.request().method()!=='POST'){await route.continue();return}
      const response=await route.fetch();waiting=true
      await new Promise<void>(resolve=>{release=resolve})
      await route.fulfill({response})
    })
    if(action==='comparison')await openWorkspaceAdvanced(page,'Run comparison')
    else if(action==='demo'){await prepareExample(page);await page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/}).first().click()}
    else {
      await page.getByRole('link',{name:'Saved work',exact:true}).click()
      if(action==='open') {
        await page.getByLabel('Search investigations').fill(bundle.entries.investigation.id)
        await page.locator('.library-row').filter({hasText:bundle.entries.investigation.id}).getByRole('button',{name:'Open',exact:true}).click()
      }
      else await page.getByLabel('Import replay-checked bundle').setInputFiles({name:'saved.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle))})
    }
    await expect.poll(()=>waiting).toBe(true)
    await openWorkspaceSources(page)
    await page.getByRole('button',{name:'Load cached',exact:true}).click()
    await openSourceTools(page,'snpeff')
    await page.getByLabel('SnpEff annotated VCF').fill('Keep this newer VCF draft')
    const completed=page.waitForResponse(r=>r.url().endsWith(url))
    release();await(await completed).finished();await settle(page)
    await openSourceTools(page,'snpeff')
    await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue('Keep this newer VCF draft')
    await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toHaveCount(0)
    await expect(page.getByRole('button',{name:'Load cached',exact:true})).toBeEnabled()
  })
}

test('a discarded SnpEff request cannot select a check belonging to the previous capture',async({page})=>{
  const bundle=await seed(page)
  const source=bundle.entries.source_record
  const ann=source.transcripts.map((row:any)=>`T|${row.consequence_terms.join('&')}|MODERATE|G|${row.gene_id}|transcript|${row.transcript_id}`).join(',')
  expect((await page.request.post(`/api/sources/ensembl/records/${source.id}/snpeff-check`,{data:{
    vcf_text:`1\t6524705\t.\tC\tT\t.\t.\tANN=${ann}`,snpeff_version:'test',genome_database:'test',database_sha256:'a'.repeat(64)}})).ok()).toBe(true)
  await page.goto('/')
  await openWorkspaceSources(page)
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  const url=`/api/sources/ensembl/records/${source.id}/snpeff-check`
  let release:()=>void=()=>{},waiting=false
  await page.route(`**${url}`,async route=>{
    const response=await route.fetch();waiting=true
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await openSourceTools(page,'snpeff')
  await page.getByRole('button',{name:'Load saved comparison',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  const code=`
import sys,json,hashlib,tempfile
from pathlib import Path
sys.path.insert(0,'../backend')
from app.ensembl import SourceRecord,comparison_input,CompareTranscripts
from app.engine import compare
from app.storage import save_source_record
from app.bundle import create_bundle
source=SourceRecord.model_validate_json(sys.argv[1])
source.retrieved_at='2026-10-19T12:00:00+00:00'
source.id=hashlib.sha256(json.dumps({'query':source.query.model_dump(),'release':source.releases,'assembly':source.assembly_accession,'raw':source.source_response_sha256,'retrieved_at':source.retrieved_at},sort_keys=True).encode()).hexdigest()[:20]
payload=comparison_input(source,CompareTranscripts(transcript_a=source.transcripts[0].transcript_id,transcript_b=source.transcripts[1].transcript_id))
with tempfile.TemporaryDirectory() as folder:
 db=Path(folder)/'probe.db'
 save_source_record(db,source)
 print(json.dumps(create_bundle(db,compare(payload))))
`
  const second=JSON.parse(execFileSync(python,['-c',code,JSON.stringify(source)],{encoding:'utf8'}))
  expect((await page.request.post('/api/bundles/import',{data:second})).ok()).toBe(true)
  await page.getByLabel('Position',{exact:true}).fill('6524706')
  await page.getByLabel('Position',{exact:true}).fill('6524705')
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await expect(page.getByText('No SnpEff check is selected for the comparison.',{exact:true})).toBeVisible()
  const completed=page.waitForResponse(r=>r.url().endsWith(url))
  release();await(await completed).finished();await settle(page)
  await expect(page.getByText('No SnpEff check is selected for the comparison.',{exact:true})).toBeVisible()
  await expect(page.locator('.snpeff-result')).toHaveCount(0)
  const compared=page.waitForResponse(r=>r.url().endsWith(`/api/sources/ensembl/records/${second.entries.source_record.id}/compare`))
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  const response=await compared
  expect(response.ok()).toBe(true)
  expect((await response.json()).input.annotation_check).toBeNull()
})

test('source refresh preserves selections made before and during the request',async({page})=>{
  const bundle=await seed(page)
  const source=bundle.entries.source_record
  await page.goto('/')
  await openWorkspaceSources(page)
  await openSourceTools(page,'history')
  await page.getByRole('button',{name:'Load preserved sources',exact:true}).click()
  await openSourceTools(page,'history')
  await page.getByLabel('Preserved analysis 1 source',{exact:true}).selectOption(source.id)
  await openSourceTools(page,'history')
  await page.getByLabel('Preserved analysis 1 transcript',{exact:true}).selectOption(source.transcripts[1].transcript_id)
  let release:()=>void=()=>{},waiting=false
  await page.route('**/api/sources/records',async route=>{
    const response=await route.fetch();waiting=true
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await openSourceTools(page,'history')
  await page.getByRole('button',{name:'Load preserved sources',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  await openSourceTools(page,'history')
  await page.getByLabel('Preserved analysis 1 transcript',{exact:true}).selectOption(source.transcripts[0].transcript_id)
  const completed=page.waitForResponse(r=>r.url().endsWith('/api/sources/records'))
  release();await(await completed).finished();await settle(page)
  await expect(page.getByLabel('Preserved analysis 1 source',{exact:true})).toHaveValue(source.id)
  await expect(page.getByLabel('Preserved analysis 1 transcript',{exact:true})).toHaveValue(source.transcripts[0].transcript_id)
})
