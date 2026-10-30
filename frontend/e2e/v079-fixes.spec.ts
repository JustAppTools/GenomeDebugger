import {openSourceTools} from './workspace-helpers'
import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import path from 'node:path'

const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')

async function openUnsavedBaseline(page:Page) {
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title=`0.7.9 baseline ${Date.now()} ${Math.random()}`
  const response=await page.request.post('/api/investigations',{data:input})
  expect(response.ok()).toBe(true)
  const result=await response.json()
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill(result.id)
  await page.locator('.library-row').filter({hasText:result.id}).getByRole('button',{name:'Open',exact:true}).click()
  await page.getByRole('heading',{name:'Compared analyses',exact:true}).waitFor()
  await page.getByRole('button',{name:'Saved tests',exact:true}).first().click()
  await expect(page.getByRole('button',{name:'Save regression case',exact:true})).toBeEnabled()
  return result
}

for(const mode of ['Load cached','Fetch current from Ensembl']) {
  test(`${mode} retains selected checks and drafts for the same capture`,async({page})=>{
    const bundle=JSON.parse(execFileSync(python,['e2e/reference-bundle.py'],{encoding:'utf8'}))
    expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
    const source=bundle.entries.source_record,q=source.query
    const ann=source.transcripts.map((row:any)=>`${q.alt}|${row.consequence_terms.join('&')}|MODIFIER|G|${row.gene_id}|transcript|${row.transcript_id}`).join(',')
    const response=await page.request.post(`/api/sources/ensembl/records/${source.id}/snpeff-check`,{data:{
      vcf_text:`${q.chromosome}\t${q.position}\t.\t${q.ref}\t${q.alt}\t.\tPASS\tANN=${ann}`,
      snpeff_version:'regression',genome_database:'regression',database_sha256:'a'.repeat(64)}})
    expect(response.ok()).toBe(true)
    const checked=await response.json()
    await page.route('**/api/sources/ensembl/lookup',route=>route.fulfill({json:{record:source,access:mode==='Load cached'?'cache':'fetched'}}))
    await page.goto('/')
    await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
    await page.getByRole('button',{name:'Load cached',exact:true}).click()
    const chosen=source.transcripts.at(-1).transcript_id
    await page.getByLabel('Analysis A transcript',{exact:true}).selectOption(chosen)
    await page.getByLabel('Analysis B transcript',{exact:true}).selectOption(source.transcripts[0].transcript_id)
    await openSourceTools(page,'snpeff')
    await page.getByLabel('SnpEff annotated VCF').fill('Retained independent VCF draft')
    await openSourceTools(page,'snpeff')
    await page.getByRole('button',{name:'Load saved comparison',exact:true}).click()
    await expect(page.locator('.snpeff-result strong')).toHaveText('AGREE')
    const referenceLoaded=page.waitForResponse(r=>r.url().endsWith(`/${source.id}/reference-check`))
    await openSourceTools(page,'ncbi')
    await page.getByRole('button',{name:'Load saved check',exact:true}).click()
    const reference=(await(await referenceLoaded).json()).check
    await expect(page.locator('.reference-result')).toBeVisible()
    await expect(page.getByText(`NCBI check ${reference.id} is linked in provenance.`)).toBeVisible()
    const loaded=page.waitForResponse(r=>r.url().endsWith('/ensembl/lookup'))
    await page.getByRole('button',{name:mode,exact:true}).click()
    await loaded
    await expect(page.getByRole('button',{name:mode,exact:true})).toBeEnabled()
    await expect(page.locator('.snpeff-result strong')).toHaveText('AGREE')
    await expect(page.getByText(`Selected SnpEff check: ${checked.id} (agree). This check will be included in the comparison.`)).toBeVisible()
    await openSourceTools(page,'snpeff')
    await expect(page.getByLabel('SnpEff annotated VCF')).toHaveValue('Retained independent VCF draft')
    await expect(page.getByLabel('Analysis A transcript',{exact:true})).toHaveValue(chosen)
    await expect(page.locator('.reference-result')).toBeVisible()
    const compared=page.waitForResponse(r=>r.url().endsWith(`/${source.id}/compare`))
    await page.getByRole('button',{name:'Compare',exact:true}).click()
    const result=await(await compared).json()
    expect(result.input.annotation_check.id).toBe(checked.id)
    expect(result.input.reference_check.id).toBe(reference.id)
    expect(result.input.snapshots[0].annotation.transcript_id).toBe(chosen)
  })
}

test('initial load makes no external resource requests',async({page})=>{
  const external:string[]=[]
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url())
    if(['http:','https:'].includes(url.protocol)&&!['127.0.0.1','localhost','[::1]'].includes(url.hostname)) {
      external.push(url.href);await route.abort()
    } else await route.continue()
  })
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await expect(page.locator('.local-badge')).toHaveText('Local engine connected')
  expect(external).toEqual([])
  await expect(page.locator('link[href*="fonts.googleapis"],link[href*="fonts.gstatic"]')).toHaveCount(0)
})

for(const succeeds of [true,false]) {
  test(`test name is locked during saving and ${succeeds?'retained on success':'editable after failure'}`,async({page})=>{
    await openUnsavedBaseline(page)
    let release:()=>void=()=>{},waiting=false,submitted:any
    await page.route('**/api/investigations/*/regression-cases',async route=>{
      if(route.request().method()!=='POST'){await route.continue();return}
      submitted=route.request().postDataJSON()
      const response=succeeds?await route.fetch():null
      waiting=true
      await new Promise<void>(resolve=>{release=resolve})
      if(response)await route.fulfill({response})
      else await route.fulfill({status:503,json:{detail:'Temporary save failure'}})
    })
    const name='Original immutable baseline name'
    await page.getByLabel('Test name').fill(name)
    await page.getByRole('button',{name:'Save regression case',exact:true}).click()
    await expect.poll(()=>waiting).toBe(true)
    await expect(page.getByLabel('Test name')).toBeDisabled()
    await expect(page.getByLabel('Test name')).toHaveValue(name)
    expect(submitted.name).toBe(name)
    release()
    if(succeeds)await expect(page.locator('.case-record strong')).toHaveText(name)
    else {
      await expect(page.getByRole('alert')).toContainText('Temporary save failure')
      await expect(page.getByLabel('Test name')).toBeEnabled()
      await expect(page.getByLabel('Test name')).toHaveValue(name)
      await page.getByLabel('Test name').fill('A new editable name')
      await expect(page.getByLabel('Test name')).toHaveValue('A new editable name')
    }
  })
}

for(const character of ['W','🧬']) {
  test(`a 200-character ${character==='W'?'ASCII':'Unicode'} name fits phone and desktop layouts`,async({page},testInfo)=>{
    await openUnsavedBaseline(page)
    const name=character.repeat(200)
    await page.getByLabel('Test name').fill(name)
    await page.getByRole('button',{name:'Save regression case',exact:true}).click()
    await expect(page.locator('.case-record strong')).toHaveText(name)
    for(const width of [375,320,1280]) {
      await page.setViewportSize({width,height:900})
      await expect(page.locator('.case-record strong')).toHaveText(name)
      await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
      const box=await page.locator('.case-record strong').boundingBox()
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.x+box!.width).toBeLessThanOrEqual(width)
      await expect(page.getByRole('button',{name:'Run pinned baseline',exact:true})).toBeVisible()
      if(width===375&&character==='W')await page.locator('.regression-intro').screenshot({path:testInfo.outputPath('baseline-phone.png')})
    }
  })
}
