import {openSourceTools} from './workspace-helpers'
import {test,expect,type Page} from '@playwright/test'
import {readFile} from 'node:fs/promises'
import {execFileSync} from 'node:child_process'
import path from 'node:path'

function referenceBundle(agrees=false) {
  const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
  return JSON.parse(execFileSync(python,['e2e/reference-bundle.py',agrees?'agree':'disagree'],{encoding:'utf8'}))
}
async function sourcePage(page:Page) {
  const bundle=referenceBundle()
  expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
  await page.goto('/')
  await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await openSourceTools(page,'snpeff')
  await page.getByRole('heading',{name:'SnpEff ANN comparison',exact:true}).waitFor()
  return bundle
}

test('source comparisons use exactly the checks displayed as selected',async({page})=>{
  const bundle=await sourcePage(page)
  const url=`/api/sources/ensembl/records/${bundle.entries.source_record.id}/compare`
  await expect(page.getByText('No NCBI check is currently linked.',{exact:false})).toBeVisible()
  let response=page.waitForResponse(r=>r.url().endsWith(url))
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  const unchecked=await(await response).json()
  expect(unchecked.input.reference_check).toBeNull()
  expect(unchecked.input.annotation_check).toBeNull()
  await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await openSourceTools(page,'ncbi')
  await page.getByRole('button',{name:'Load saved check',exact:true}).click()
  await expect(page.locator('.reference-result')).toContainText('disagree')
  // Another client saves a newer check; the displayed selection remains pinned.
  expect((await page.request.post('/api/bundles/import',{data:referenceBundle(true)})).ok()).toBe(true)
  response=page.waitForResponse(r=>r.url().endsWith(url))
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  const selected=await(await response).json()
  expect(selected.input.reference_check.id).toBe(bundle.entries.reference_check.id)
  expect(selected.input.reference_check.status).toBe('disagree')
})

test('existing-case discovery prevents a competing baseline save',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title='Discovery loading guard regression'
  const result=await(await page.request.post('/api/investigations',{data:input})).json()
  const existing=await(await page.request.post(`/api/investigations/${result.id}/regression-cases`,{data:{name:'Existing baseline'}})).json()
  const releases:(()=>void)[]=[]
  let released=false
  await page.route(`**/api/regression-cases/${existing.id}/runs`,async route=>{
    const response=await route.fetch()
    if(!released)await new Promise<void>(resolve=>{releases.push(resolve)})
    await route.fulfill({response})
  })
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill(input.title)
  await page.locator('.library-row').filter({hasText:result.id}).getByRole('button',{name:'Open',exact:true}).click()
  await page.getByRole('complementary').getByRole('button',{name:'Saved tests',exact:true}).click()
  await expect.poll(()=>releases.length).toBeGreaterThan(0)
  await expect(page.getByRole('button',{name:'Save regression case',exact:true})).toBeDisabled()
  await expect(page.getByRole('status')).toContainText('Loading saved tests')
  released=true
  releases.forEach(release=>release())
  await expect(page.locator('.case-record')).toContainText('Existing baseline')
  expect(await(await page.request.get(`/api/regression-cases?source_investigation_id=${result.id}`)).json()).toHaveLength(1)
})

test('SnpEff file selection and manual edits supersede earlier pending reads',async({page})=>{
  await sourcePage(page)
  await page.evaluate(()=>{
    const original=File.prototype.arrayBuffer
    File.prototype.arrayBuffer=async function(){
      const content=await original.call(this)
      if(this.name==='old.vcf')await new Promise<void>(resolve=>{(window as any).releaseOldVcf=resolve})
      return content
    }
  })
  const upload=page.getByLabel('Import annotated VCF')
  await upload.setInputFiles({name:'old.vcf',mimeType:'text/plain',buffer:Buffer.from('Earlier output')})
  await expect.poll(()=>page.evaluate(()=>Boolean((window as any).releaseOldVcf))).toBe(true)
  await upload.setInputFiles({name:'new.vcf',mimeType:'text/plain',buffer:Buffer.from('Latest selected output')})
  await openSourceTools(page,'snpeff')
  await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue('Latest selected output')
  await page.evaluate(()=>(window as any).releaseOldVcf())
  await openSourceTools(page,'snpeff')
  await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue('Latest selected output')
  await page.evaluate(()=>(window as any).releaseOldVcf=null)
  await upload.setInputFiles({name:'old.vcf',mimeType:'text/plain',buffer:Buffer.from('Superseded by typing')})
  await expect.poll(()=>page.evaluate(()=>Boolean((window as any).releaseOldVcf))).toBe(true)
  await openSourceTools(page,'snpeff')
  await page.getByLabel('SnpEff annotated VCF').fill('New manual draft')
  await page.evaluate(()=>(window as any).releaseOldVcf())
  await openSourceTools(page,'snpeff')
  await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue('New manual draft')
  await expect(page.getByRole('alert')).toHaveCount(0)
})

for(const invalidOldFile of [false,true]) {
  test(`historical import keeps the latest artifact after an earlier ${invalidOldFile?'invalid':'valid'} read`,async({page})=>{
    const fixture=JSON.parse(await readFile('../fixtures/snpeff-mane-public-run.json','utf8'))
    const latest=JSON.stringify([{...fixture.source.source_response,audit_marker:'Latest selected artifact'}])
    await page.goto('/')
    await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
    await openSourceTools(page,'history')
    await page.getByText('Import historical VEP output',{exact:true}).click()
    await page.evaluate(()=>{
      const original=File.prototype.arrayBuffer
      File.prototype.arrayBuffer=async function(){
        const content=await original.call(this)
        if(this.name==='old.json')await new Promise<void>(resolve=>{(window as any).releaseArtifact=resolve})
        return content
      }
    })
    await page.getByLabel('Historical VEP JSON file').setInputFiles({name:'old.json',mimeType:'application/json',buffer:invalidOldFile?Buffer.from([0xff]):Buffer.from(JSON.stringify([fixture.source.source_response]))})
    await expect.poll(()=>page.evaluate(()=>Boolean((window as any).releaseArtifact))).toBe(true)
    await page.getByLabel('Historical VEP JSON file').setInputFiles({name:'latest.json',mimeType:'application/json',buffer:Buffer.from(latest)})
    await page.getByLabel('Historical Ensembl release').fill('110')
    await page.getByLabel('Historical VEP version').fill('110')
    await page.getByLabel('Historical run time').fill('2024-01-01T12:00')
    await page.getByLabel('Historical artifact source').fill('Metadata for latest selected artifact')
    await expect(page.getByRole('button',{name:'Preserve historical output',exact:true})).toBeEnabled()
    await page.evaluate(()=>(window as any).releaseArtifact())
    const pending=page.waitForRequest(r=>r.url().endsWith('/api/sources/historical-vep')&&r.method()==='POST')
    await page.getByRole('button',{name:'Preserve historical output',exact:true}).click()
    expect((await pending).postDataJSON().raw_json).toBe(latest)
    await expect(page.getByRole('status')).toContainText('Historical output preserved')
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
}

test('a default-expanded input can be reopened, rerun and checked as a candidate',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title='Default-expanded saved input regression'
  input.controlled_lookup=null
  for(const snapshot of input.snapshots)snapshot.annotations=Array.from({length:1000},(_,i)=>({gene_id:'G',transcript_id:`T${i}`,consequence:'x'.repeat(420)}))
  const created=await page.request.post('/api/investigations',{data:input})
  expect(created.ok()).toBe(true)
  const result=await created.json()
  expect(Buffer.byteLength(JSON.stringify(result.input))).toBeGreaterThan(1_000_000)
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill(input.title)
  await page.locator('.library-row').filter({hasText:result.id}).getByRole('button',{name:'Open',exact:true}).click()
  await page.getByRole('button',{name:'Run comparison',exact:true}).click()
  await expect(page.getByRole('button',{name:'Run comparison',exact:true})).toBeEnabled()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('complementary').getByRole('button',{name:'Saved tests',exact:true}).click()
  await page.getByRole('button',{name:'Save regression case',exact:true}).click()
  await page.getByRole('button',{name:'Check candidate',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Regression passed',exact:true})).toBeVisible()
})

test('library deletion refills full pages and returns from an emptied last page',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  for(let i=0;i<51;i++) {
    input.title=`Retention regression ${String(i).padStart(3,'0')}`
    expect((await page.request.post('/api/investigations',{data:input})).ok()).toBe(true)
  }
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill('Retention regression')
  await expect(page.locator('.library-row')).toHaveCount(50)
  page.on('dialog',dialog=>dialog.accept())
  await page.locator('.library-row').filter({hasText:'Retention regression 050'}).getByText('Permanent deletion',{exact:true}).click()
  await page.locator('.library-row').filter({hasText:'Retention regression 050'}).getByRole('button',{name:'Delete',exact:true}).click()
  await expect(page.locator('.library-row')).toHaveCount(50)
  await expect(page.locator('.library-row').filter({hasText:'Retention regression 000'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Next records',exact:true})).toBeDisabled()
  input.title='Retention regression 051'
  expect((await page.request.post('/api/investigations',{data:input})).ok()).toBe(true)
  await page.getByLabel('Search investigations').fill('Retention')
  await expect(page.getByRole('button',{name:'Next records',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Next records',exact:true}).click()
  await expect(page.locator('.library-row')).toHaveCount(1)
  await page.locator('.library-row').getByText('Permanent deletion',{exact:true}).click()
  await page.locator('.library-row').getByRole('button',{name:'Delete',exact:true}).click()
  await expect(page.locator('.library-row')).toHaveCount(50)
  await expect(page.getByRole('button',{name:'Previous records',exact:true})).toBeDisabled()
  await expect(page.getByRole('button',{name:'Next records',exact:true})).toBeDisabled()
})
