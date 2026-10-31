import {openWorkspaceInputs,openWorkspaceSources} from './workspace-helpers'
import {openSourceTools,prepareGuided} from './workspace-helpers'
import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import path from 'node:path'

async function sourcePage(page:Page) {
  const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
  const bundle=JSON.parse(execFileSync(python,['e2e/reference-bundle.py'],{encoding:'utf8'}))
  expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
  // Other workflows intentionally add newer captures for the same coordinates.
  // Select this preserved fixture explicitly so the delayed URL matches its ID.
  await page.route('**/api/sources/ensembl/lookup',route=>route.fulfill({json:{record:bundle.entries.source_record,access:'cache'}}))
  await page.goto('/')
  await openWorkspaceSources(page)
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await openSourceTools(page,'snpeff')
  await page.getByLabel('SnpEff annotated VCF').waitFor()
  return bundle.entries.source_record
}

for(const preserved of [false,true]) {
  test(`a pending ${preserved?'preserved':'current'} comparison keeps newer edits in the sibling source form`,async({page})=>{
    const source=await sourcePage(page)
    const url=preserved?'/api/sources/compare':`/api/sources/ensembl/records/${source.id}/compare`
    if(preserved){
      await openSourceTools(page,'history')
      await page.getByRole('button',{name:'Load preserved sources',exact:true}).click()
      await openSourceTools(page,'history')
      for(const side of [1,2])await page.getByLabel(`Preserved analysis ${side} source`,{exact:true}).selectOption(source.id)
      await openSourceTools(page,'history')
      await page.getByLabel('Preserved analysis 2 transcript',{exact:true}).selectOption(source.transcripts[1].transcript_id)
    }
    let release:()=>void=()=>{},waiting=false
    await page.route(`**${url}`,async route=>{
      const response=await route.fetch();waiting=true
      await new Promise<void>(resolve=>{release=resolve})
      await route.fulfill({response})
    })
    await page.getByRole('button',{name:preserved?'Compare preserved sources':'Compare',exact:true}).click()
    await expect.poll(()=>waiting).toBe(true)
    await openSourceTools(page,'snpeff')
    if(preserved)await page.getByLabel('SnpEff annotated VCF').fill('Keep this newer sibling VCF')
    else {
      await openSourceTools(page,'history')
      await page.getByText('Import historical VEP output',{exact:true}).click()
      await page.getByLabel('Historical VEP JSON file').setInputFiles({name:'historical.json',mimeType:'application/json',buffer:Buffer.from('[{"saved":"artifact"}]')})
      await page.getByLabel('Historical Ensembl release').fill('100')
      await page.getByLabel('Historical VEP version').fill('Keep this version')
      await page.getByLabel('Historical run time').fill('2024-01-01T12:00')
      await page.getByLabel('Historical artifact source').fill('file:///preserved.json')
      await expect(page.getByRole('button',{name:'Preserve historical output'})).toBeEnabled()
    }
    const complete=page.waitForResponse(r=>r.url().endsWith(url))
    release();await(await complete).finished()
    await expect(page.getByRole('status').filter({hasText:'Source workspace changed'})).toBeVisible()
    await openSourceTools(page,'snpeff')
    if(preserved)await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue('Keep this newer sibling VCF')
    else {
      await expect(page.getByLabel('Historical VEP version')).toHaveValue('Keep this version')
      await expect(page.getByRole('button',{name:'Preserve historical output'})).toBeEnabled()
    }
    await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toHaveCount(0)
  })
}

test('invalid UTF-8 JSON and bundles are rejected before changing the draft or posting',async({page})=>{
  await page.goto('/')
  await openWorkspaceInputs(page)
  await prepareGuided(page)
  await page.getByLabel('Investigation title').fill('Keep my input')
  const malformed=Buffer.concat([Buffer.from('{"title":"'),Buffer.from([0xe9]),Buffer.from('"}')])
  await page.getByLabel('Import input JSON',{exact:true}).setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:malformed})
  await expect(page.getByRole('alert')).toContainText('valid UTF-8')
  await expect(page.getByLabel('Investigation title')).toHaveValue('Keep my input')
  await page.getByRole('link',{name:'Saved work',exact:true}).click()
  let posts=0
  page.on('request',request=>{if(request.url().includes('/api/bundles/')&&request.method()==='POST')posts++})
  await page.getByLabel('Import replay-checked bundle').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:malformed})
  await expect(page.getByRole('alert')).toContainText('valid UTF-8')
  expect(posts).toBe(0)
})

test('invalid UTF-8 VCF keeps the previous draft',async({page})=>{
  await sourcePage(page)
  await openSourceTools(page,'snpeff')
  await page.getByLabel('SnpEff annotated VCF').fill('Keep the previous VCF')
  await page.getByLabel('Import annotated VCF').setInputFiles({name:'invalid.vcf',mimeType:'text/plain',buffer:Buffer.from([0xf1])})
  await expect(page.getByRole('alert')).toContainText('valid UTF-8')
  await openSourceTools(page,'snpeff')
  await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue('Keep the previous VCF')
})
