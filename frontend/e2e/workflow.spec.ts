import {openSourceTools,prepareExample,prepareGuided} from './workspace-helpers'
import { expect, test } from '@playwright/test'
import { readFile, stat } from 'node:fs/promises'

test('demo, evidence, regression, and portable bundle work through the browser', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Local engine connected')).toBeVisible()
  await prepareExample(page)
  await page.getByRole('button', { name: /^Try (?:an )?example(?: again)?$/ }).first().click()
  await expect(page.getByRole('heading', { name: 'Compared analyses' })).toBeVisible()
  await page.getByText('Show technical details',{exact:true}).click()
  await expect(page.getByText('Changing only the selected transcript reproduces')).toBeVisible()
  await page.getByRole('button', { name: /Changes 6/ }).click()
  await expect(page.getByRole('button', { name: 'Inspect' }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Inspect' }).first().click()
  await expect(page.getByRole('heading', { name: 'Evidence inspector', exact: true })).toBeVisible()
  await expect(page.locator('.evidence-detail h3')).toContainText('changed')
  await expect(page.getByRole('heading', { name: 'Conclusions using this record' })).toBeVisible()

  await page.getByRole('complementary').getByRole('button', { name: 'Saved tests' }).click()
  await page.getByRole('button', { name: 'Save regression case' }).click()
  await page.getByRole('button', { name: 'Run pinned baseline' }).click()
  await expect(page.getByRole('heading', { name: 'Regression passed' })).toBeVisible()
  await page.getByLabel('Candidate analysis 2 consequence').fill('synonymous_variant')
  await page.getByRole('button', { name: 'Check candidate' }).click()
  await expect(page.getByRole('heading', { name: 'Regression failed' })).toBeVisible()

  await page.getByRole('button', { name: 'Results', exact: true }).click()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Full bundle', exact: true }).click()
  const download = await downloadPromise
  const bundlePath = await download.path()
  expect(bundlePath).not.toBeNull()
  await page.getByRole('button', { name: 'Saved comparisons' }).click()
  await page.getByLabel('Import replay-checked bundle').setInputFiles(bundlePath!)
  await expect(page.getByRole('heading', { name: 'Compared analyses' })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: 'Saved comparisons' }).click()
  await page.getByLabel('Search investigations').fill('Synthetic transcript')
  await expect(page.getByRole('button', { name: 'Open' }).first()).toBeVisible()
})

test('mobile guide retains context start and blocks incomplete input', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Enter results' }).click()
  await prepareGuided(page)
  await page.getByLabel('Analysis 1 context start').fill('99')
  await expect(page.getByLabel('Analysis 1 context start')).toHaveValue('99')
  await page.getByLabel('Analysis 1 reference sequence').fill('GACGTACG')
  await expect(page.getByLabel('Analysis 1 context start')).toHaveValue('99')
  await expect(page.getByRole('button', { name: 'Compare analyses' })).toBeDisabled()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)
})

test('offline and empty public cache states explain the failure', async ({ page }) => {
  await page.route('**/api/health', route => route.abort())
  await page.goto('/')
  await expect(page.getByText('Local engine offline', { exact: true })).toBeVisible()
  await page.unroute('**/api/health')
  await page.reload()
  await expect(page.getByText('Local engine connected')).toBeVisible()
  await page.getByRole('button', { name: 'Look up a DNA change' }).click()
  // Use an uncached query: other workflows deliberately preserve the default
  // example in the shared, isolated browser-test database.
  await page.getByLabel('Chromosome',{exact:true}).fill('22')
  await page.getByLabel('Position',{exact:true}).fill('424242')
  await page.getByLabel('Reference allele',{exact:true}).fill('A')
  await page.getByLabel('Alternate allele',{exact:true}).fill('C')
  await page.getByRole('button', { name: 'Load cached' }).click()
  await expect(page.getByRole('alert')).toContainText('No local Ensembl record is cached')
})

test('malformed JSON stays editable and guided input supports multiple variants',async({page})=>{
  const demo = await (await page.request.get('/api/demos/transcript-switch')).json()
  demo.snapshots[0].variant.reference_context.sequence = 123
  await page.goto('/')
  await page.getByRole('button',{name:'Enter results'}).click()
  await prepareGuided(page)
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  const malformed = JSON.stringify(demo)
  await page.getByLabel('Investigation JSON').fill(malformed)
  await page.getByRole('button',{name:'Guided form',exact:true}).click()
  await prepareGuided(page)
  await expect(page.getByRole('alert')).toContainText('sequence must be text')
  await expect(page.getByLabel('Investigation JSON')).toHaveValue(malformed)
  demo.snapshots[0].variant.reference_context.sequence = 'GACGTACG'
  await page.getByLabel('Investigation JSON').fill(JSON.stringify(demo))
  await page.getByRole('button',{name:'Guided form',exact:true}).click()
  await prepareGuided(page)
  for (const [side,index] of [['A',1],['B',2]] as const) {
    await page.getByRole('button',{name:`Add variant to analysis ${side}`,exact:true}).click()
    const prefix = `Analysis ${index} variant 2`
    await page.getByLabel(`${prefix} assembly`,{exact:true}).fill('GRCh38')
    await page.getByLabel(`${prefix} sequence accession`,{exact:true}).fill('NC_000001.11')
    await page.getByLabel(`${prefix} position`,{exact:true}).fill('104')
    await page.getByLabel(`${prefix} reference`,{exact:true}).fill('T')
    await page.getByLabel(`${prefix} alternate`,{exact:true}).fill('G')
    await page.getByLabel(`${prefix} annotation 1 gene id`,{exact:true}).fill('G2')
    await page.getByLabel(`${prefix} annotation 1 transcript id`,{exact:true}).fill('T2')
    await page.getByLabel(`${prefix} annotation 1 consequence`,{exact:true}).fill('intron_variant')
  }
  await expect(page.getByRole('button',{name:'Compare analyses'})).toBeEnabled()
  await page.getByRole('button',{name:'Compare analyses'}).click()
  await expect(page.getByRole('heading',{name:'Compared analyses'})).toBeVisible()
  await page.getByText('Show technical details',{exact:true}).click()
  await expect(page.getByText('0 additional annotations · 1 additional variants',{exact:true})).toHaveCount(2)
})

test('a bundle larger than the input limit downloads and reimports',async({page})=>{
  const input = await (await page.request.get('/api/demos/transcript-switch')).json()
  input.title = 'Large bundle round trip'
  input.snapshots.forEach((snapshot:{annotations:unknown},side:number)=>{
    snapshot.annotations = Array.from({length:500},(_,i)=>({gene_id:'BIG',transcript_id:`T${i}`,consequence:(side?'B':'A').repeat(500)}))
  })
  const created = await page.request.post('/api/investigations',{data:input})
  expect(created.ok()).toBe(true)
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons'}).click()
  await page.getByLabel('Search investigations').fill(input.title)
  await page.locator('.library-row').filter({hasText:input.title}).getByRole('button',{name:'Open',exact:true}).click()
  const promise = page.waitForEvent('download')
  await page.getByRole('button',{name:'Full bundle',exact:true}).click()
  const file = await (await promise).path()
  expect((await stat(file!)).size).toBeGreaterThan(1_000_000)
  await page.getByRole('button',{name:'Saved comparisons'}).click()
  await page.getByLabel('Import replay-checked bundle').setInputFiles(file!)
  await expect(page.getByRole('heading',{name:'Compared analyses'})).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('historical output import compares two preserved artifacts and bundles both',async({page})=>{
  const fixture=JSON.parse(await readFile('../fixtures/snpeff-mane-public-run.json','utf8'))
  const raw=JSON.stringify([fixture.source.source_response])
  await page.goto('/')
  await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
  await openSourceTools(page,'history')
  await page.getByText('Import historical VEP output',{exact:true}).click()
  await page.getByLabel('Historical VEP JSON file').setInputFiles({name:'historical-fixture.json',mimeType:'application/json',buffer:Buffer.from(raw)})
  await page.getByLabel('Historical Ensembl release').fill('110')
  await page.getByLabel('Historical VEP version').fill('110-ui-fixture')
  await page.getByLabel('Historical run time').fill('2024-01-01T12:00')
  await page.getByLabel('Historical artifact source').fill('UI fixture; not a historical biological assertion')
  await page.getByRole('button',{name:'Preserve historical output',exact:true}).click()
  await expect(page.getByRole('status')).toContainText('Historical output preserved')
  const firstHistorical=await page.getByLabel('Preserved analysis 1 source').inputValue()
  const changed=structuredClone(fixture.source.source_response)
  changed.transcript_consequences[0].consequence_terms=['missense_variant']
  const imported=await page.request.post('/api/sources/historical-vep',{data:{query:fixture.source.query,
    raw_json:JSON.stringify([changed]),source_release:111,tool_version:'111-ui-fixture',generated_at:'2025-01-01T12:00:00Z',
    assembly_accession:fixture.source.assembly_accession,source_uri:'UI fixture; changed consequence'}})
  expect(imported.ok()).toBe(true)
  await openSourceTools(page,'history')
  await page.getByRole('button',{name:'Load preserved sources',exact:true}).click()
  const secondHistorical=(await imported.json()).id
  await expect(page.getByLabel('Preserved analysis 1 source').locator(`option[value="${secondHistorical}"]`)).toHaveCount(1)
  await expect(page.getByLabel('Preserved analysis 1 source')).toHaveValue(firstHistorical)
  await openSourceTools(page,'history')
  await page.getByLabel('Preserved analysis 1 source').selectOption(secondHistorical)
  await openSourceTools(page,'history')
  await page.getByLabel('Preserved analysis 2 source').selectOption(firstHistorical)
  await page.getByRole('button',{name:'Compare preserved sources',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Compared analyses'})).toBeVisible()
  const promise=page.waitForEvent('download')
  await page.getByRole('button',{name:'Full bundle',exact:true}).click()
  const file=await (await promise).path()
  const bundle=JSON.parse(await readFile(file!,'utf8'))
  expect(bundle.entries.source_records).toHaveLength(2)
  expect((await page.request.post('/api/bundles/verify',{data:bundle})).ok()).toBe(true)
})

test('editing during a comparison keeps the newer draft visibly stale',async({page})=>{
  await page.goto('/')
  await prepareExample(page)
  await page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/}).first().click()
  await page.getByRole('heading',{name:'Compared analyses'}).waitFor()
  await page.getByRole('button',{name:'Enter results',exact:true}).click()
  await prepareGuided(page)
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  const submitted=JSON.parse(await page.getByLabel('Investigation JSON').inputValue())
  submitted.title='Submitted draft revision'
  await page.getByLabel('Investigation JSON').fill(JSON.stringify(submitted))
  let release:(()=>void)|undefined
  await page.route('**/api/investigations',async route=>{
    if(route.request().method()!=='POST'){await route.continue();return}
    const response=await route.fetch()
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  await expect.poll(()=>Boolean(release)).toBe(true)
  const edited={...submitted,title:'Edited while waiting'}
  await page.getByLabel('Investigation JSON').fill(JSON.stringify(edited))
  release!()
  await page.getByRole('heading',{name:'Compared analyses'}).waitFor()
  await expect(page.getByRole('status')).toContainText('input has changed')
  await page.getByRole('button',{name:'Enter results',exact:true}).click()
  await prepareGuided(page)
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  expect(JSON.parse(await page.getByLabel('Investigation JSON').inputValue()).title).toBe(edited.title)
})

test('changed public query invalidates the pending response',async({page})=>{
  const fixture=JSON.parse(await readFile('../fixtures/snpeff-mane-public-run.json','utf8'))
  let release:(()=>void)|undefined
  let count=0
  await page.route('**/api/sources/ensembl/lookup',async route=>{
    const query=route.request().postDataJSON().query
    const found={...fixture.source,id:`request-${++count}`,query}
    if(count===1)await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({json:{record:found,access:'cache'}})
  })
  await page.goto('/')
  await page.getByRole('button',{name:'Look up a DNA change',exact:true}).click()
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await expect.poll(()=>Boolean(release)).toBe(true)
  await page.getByLabel('Position',{exact:true}).fill('999999')
  release!()
  await expect(page.getByRole('button',{name:'Load cached',exact:true})).toBeEnabled()
  await expect(page.getByRole('heading',{name:'1:6524705 C→T',exact:true})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'Compare',exact:true})).toHaveCount(0)
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  await expect(page.getByRole('heading',{name:'1:999999 C→T',exact:true})).toBeVisible()
})

test('valid omitted defaults work in both JSON and guided modes',async({page})=>{
  const input=await (await page.request.get('/api/demos/transcript-switch')).json()
  delete input.synthetic;delete input.controlled_lookup
  input.title='Defaulted non-synthetic input'
  await page.goto('/')
  await page.getByRole('button',{name:'Enter results',exact:true}).click()
  await prepareGuided(page)
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  await page.getByLabel('Investigation JSON').fill(JSON.stringify(input))
  await page.getByRole('button',{name:'Guided form',exact:true}).click()
  await prepareGuided(page)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('button',{name:'Compare analyses',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Compared analyses'})).toBeVisible()
})

for(const oldFailure of [false,true]) {
  test(`latest library selection wins over an older ${oldFailure?'failed':'successful'} response`,async({page})=>{
    const input=await (await page.request.get('/api/demos/transcript-switch')).json()
    input.title=`Selection race A ${oldFailure}`
    const a=await (await page.request.post('/api/investigations',{data:input})).json()
    input.title=`Selection race B ${oldFailure}`
    const b=await (await page.request.post('/api/investigations',{data:input})).json()
    let release:(()=>void)|undefined
    let finished=false
    await page.route(`**/api/investigations/${a.id}`,async route=>{
      await new Promise<void>(resolve=>{release=resolve})
      await route.fulfill(oldFailure?{status:503,json:{detail:'Older request failed'}}:{json:a})
      finished=true
    })
    await page.goto('/')
    await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
    await page.locator('.library-row').filter({hasText:a.input.title}).getByRole('button',{name:'Open',exact:true}).click()
    await expect.poll(()=>Boolean(release)).toBe(true)
    await page.locator('.library-row').filter({hasText:b.input.title}).getByRole('button',{name:'Open',exact:true}).click()
    await expect(page).toHaveURL(new RegExp(`/comparison/${b.id}/overview$`))
    await expect(page.locator('.breadcrumbs')).toContainText(b.input.title)
    release!()
    await expect.poll(()=>finished).toBe(true)
    await page.getByRole('button',{name:'Input JSON',exact:true}).click()
    expect(JSON.parse(await page.getByLabel('Investigation JSON').inputValue()).title).toBe(b.input.title)
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
}

test('an earlier bundle import cannot replace a later selected investigation',async({page})=>{
  const input=await (await page.request.get('/api/demos/transcript-switch')).json()
  input.title='Delayed import A'
  const a=await (await page.request.post('/api/investigations',{data:input})).json()
  const bundle=await (await page.request.get(`/api/investigations/${a.id}/bundle`)).json()
  input.title='Selected while importing B'
  const b=await (await page.request.post('/api/investigations',{data:input})).json()
  let release:(()=>void)|undefined
  let finished=false
  await page.route('**/api/bundles/import',async route=>{
    const response=await route.fetch()
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response});finished=true
  })
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Import replay-checked bundle').setInputFiles({name:'race-bundle.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle))})
  await expect.poll(()=>Boolean(release)).toBe(true)
  await page.locator('.library-row').filter({hasText:b.input.title}).getByRole('button',{name:'Open',exact:true}).click()
  await expect(page).toHaveURL(new RegExp(`/comparison/${b.id}/overview$`))
  await expect(page.locator('.breadcrumbs')).toContainText(b.input.title)
  release!()
  await expect.poll(()=>finished).toBe(true)
  await page.getByRole('button',{name:'Input JSON',exact:true}).click()
  expect(JSON.parse(await page.getByLabel('Investigation JSON').inputValue()).title).toBe(b.input.title)
})

test('a maximum-length title saves its default regression name on the first attempt',async({page})=>{
  const input=await (await page.request.get('/api/demos/transcript-switch')).json()
  input.title='L'.repeat(200)
  const result=await (await page.request.post('/api/investigations',{data:input})).json()
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.getByLabel('Search investigations').fill(input.title)
  await page.locator('.library-row').filter({hasText:result.id}).getByRole('button',{name:'Open',exact:true}).click()
  await page.getByRole('complementary').getByRole('button',{name:'Saved tests',exact:true}).click()
  await expect(page.getByLabel('Test name')).toHaveValue(`Regression: ${input.title}`.slice(0,200))
  await page.getByRole('button',{name:'Save regression case',exact:true}).click()
  await expect(page.getByText('SAVED CASE', {exact:true})).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})
