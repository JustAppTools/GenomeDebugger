import {openSourceTools,prepareGuided} from './workspace-helpers'
import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import path from 'node:path'

function referenceBundle() {
  const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
  return JSON.parse(execFileSync(python,['e2e/reference-bundle.py'],{encoding:'utf8'}))
}
async function sourcePage(page:Page) {
  const bundle=referenceBundle()
  expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
  await page.goto('/')
  await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
  return bundle.entries.source_record
}

for(const preserved of [false,true]) {
  test(`leaving a pending ${preserved?'preserved':'current'} source comparison keeps a newer draft`,async({page})=>{
    const source=await sourcePage(page)
    const url=preserved?'/api/sources/compare':`/api/sources/ensembl/records/${source.id}/compare`
    if(preserved) {
      await openSourceTools(page,'history')
      await page.getByRole('button',{name:'Load preserved sources',exact:true}).click()
      await openSourceTools(page,'history')
      for(const side of [1,2])await page.getByLabel(`Preserved analysis ${side} source`,{exact:true}).selectOption(source.id)
      await openSourceTools(page,'history')
      await page.getByLabel('Preserved analysis 2 transcript',{exact:true}).selectOption(source.transcripts[1].transcript_id)
    } else {
      await page.getByRole('button',{name:'Load cached',exact:true}).click()
      await openSourceTools(page,'snpeff')
      await page.getByRole('heading',{name:'SnpEff ANN comparison',exact:true}).waitFor()
    }
    let release:()=>void=()=>{}
    let waiting=false
    await page.route(`**${url}`,async route=>{
      const response=await route.fetch()
      waiting=true
      await new Promise<void>(resolve=>{release=resolve})
      await route.fulfill({response})
    })
    await page.getByRole('button',{name:preserved?'Compare preserved sources':'Compare',exact:true}).click()
    await expect.poll(()=>waiting).toBe(true)
    await page.getByRole('complementary').getByRole('button',{name:'Enter results',exact:true}).click()
    await prepareGuided(page)
    await page.getByLabel('Investigation title',{exact:true}).fill('Keep my newer draft')
    const completed=page.waitForResponse(r=>r.url().endsWith(url))
    release()
    const response=await completed
    await response.finished()
    const result=await response.json()
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))))
    await expect(page.getByLabel('Investigation title',{exact:true})).toHaveValue('Keep my newer draft')
    await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toHaveCount(0)
    // The completed operation remains recoverable from storage.
    expect((await page.request.get(`/api/investigations/${result.id}`)).ok()).toBe(true)
  })
}

test('reopening the source screen does not reactivate the previous screen callback',async({page})=>{
  const source=await sourcePage(page)
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await openSourceTools(page,'snpeff')
  await page.getByRole('heading',{name:'SnpEff ANN comparison',exact:true}).waitFor()
  const url=`/api/sources/ensembl/records/${source.id}/compare`
  let release:()=>void=()=>{}
  let waiting=false
  await page.route(`**${url}`,async route=>{
    const response=await route.fetch();waiting=true
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  await expect.poll(()=>waiting).toBe(true)
  await page.getByRole('button',{name:'Enter results',exact:true}).click()
  await prepareGuided(page)
  await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
  await page.getByLabel('Position',{exact:true}).fill('12345')
  const completed=page.waitForResponse(r=>r.url().endsWith(url))
  release();await(await completed).finished()
  await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))))
  await expect(page.getByLabel('Position',{exact:true})).toHaveValue('12345')
  await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toHaveCount(0)
})

test('foreign browser Blob posts are rejected without saving a record',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title='Rejected foreign-origin mutation'
  await page.route('http://127.0.0.1:5199/',route=>route.fulfill({contentType:'text/html',body:'<h1>Unapproved local origin</h1>'}))
  await page.goto('http://127.0.0.1:5199/')
  const outcome=await page.evaluate(async data=>{
    try {
      await fetch('http://127.0.0.1:8001/api/investigations',{method:'POST',body:new Blob([JSON.stringify(data)])})
      return 'response read'
    } catch {return 'response blocked'}
  },input)
  expect(outcome).toBe('response blocked')
  const saved=await(await page.request.get('http://127.0.0.1:8001/api/investigations',{params:{q:input.title}})).json()
  expect(saved).toHaveLength(0)
})

test('technical cards show the actual SnpEff summary even when legacy flags are missing',async({page})=>{
  const source=await sourcePage(page)
  const annotations=source.transcripts.map((row:any)=>`T|${row.consequence_terms.join('&')}|MODERATE|G|${row.gene_id}|transcript|${row.transcript_id}`).join(',')
  const checked=await page.request.post(`/api/sources/ensembl/records/${source.id}/snpeff-check`,{data:{
    vcf_text:`1\t6524705\t.\tC\tT\t.\t.\tANN=${annotations}`,snpeff_version:'test',genome_database:'test',database_sha256:'a'.repeat(64)}})
  expect(checked.ok()).toBe(true)
  const check=await checked.json()
  const compared=await page.request.post(`/api/sources/ensembl/records/${source.id}/compare`,{data:{
    transcript_a:source.transcripts[0].transcript_id,transcript_b:source.transcripts[1].transcript_id,
    reference_check_id:null,annotation_check_id:check.id}})
  const input=(await compared.json()).input
  for(const snapshot of input.snapshots)for(const key of ['annotation_check_id','annotation_check_status','annotation_check_origin'])delete snapshot.provenance.configuration[key]
  input.title='Legacy SnpEff flags omitted'
  const created=await page.request.post('/api/investigations',{data:input})
  expect(created.ok()).toBe(true)
  const result=await created.json()
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill(input.title)
  await page.locator('.library-row').filter({hasText:result.id}).getByRole('button',{name:'Open',exact:true}).click()
  await page.getByText('Show technical details',{exact:true}).click()
  await expect(page.locator('.snapshot-card').first()).toContainText(`SnpEff check ${check.id} (agree)`)
})
