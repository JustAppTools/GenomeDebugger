import {expect,test,type Page} from '@playwright/test'
import {readFile} from 'node:fs/promises'

async function preserve(page:Page){
  const fixture=JSON.parse(await readFile('../fixtures/snpeff-mane-public-run.json','utf8'))
  const response=await page.request.post('/api/sources/historical-vep',{data:{query:fixture.source.query,
    raw_json:JSON.stringify([fixture.source.source_response]),source_release:110,tool_version:'110-selection-fixture',
    generated_at:'2024-01-01T00:00:00Z',assembly_accession:fixture.source.assembly_accession,source_uri:'Browser selection regression fixture'}})
  expect(response.ok()).toBe(true)
  return response.json()
}

test('public transcript changes preserve the new selection when an old comparison completes',async({page})=>{
  const source=await preserve(page)
  await page.route('**/api/sources/ensembl/lookup',route=>route.fulfill({json:{record:source,access:'cache'}}))
  const url=`**/api/sources/ensembl/records/${source.id}/compare`
  let release:(()=>void)|undefined
  await page.route(url,async route=>{
    const response=await route.fetch()
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.goto('/')
  await page.getByRole('button',{name:'Public source',exact:true}).click()
  await page.getByRole('button',{name:'Load cached',exact:true}).click()
  const oldA=await page.getByLabel('Analysis A transcript',{exact:true}).inputValue()
  const oldB=await page.getByLabel('Analysis B transcript',{exact:true}).inputValue()
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  await expect.poll(()=>Boolean(release)).toBe(true)
  const newA=source.transcripts.find((row:{transcript_id:string})=>![oldA,oldB].includes(row.transcript_id)).transcript_id
  await page.getByLabel('Analysis A transcript',{exact:true}).selectOption(newA)
  release!()
  await expect(page.getByRole('status')).toContainText('Transcript selection changed while comparing')
  await expect(page.getByLabel('Analysis A transcript',{exact:true})).toHaveValue(newA)
  await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toHaveCount(0)
  await page.unroute(url)
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  await page.getByRole('heading',{name:'Compared analyses',exact:true}).waitFor()
  await page.getByRole('button',{name:'Snapshot JSON',exact:true}).click()
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  expect(JSON.parse(await page.getByLabel('Investigation JSON').inputValue()).snapshots[0].annotation.transcript_id).toBe(newA)
})

test('preserved transcript changes preserve the new selection when an old comparison completes',async({page})=>{
  const source=await preserve(page)
  let release:(()=>void)|undefined
  await page.route('**/api/sources/compare',async route=>{
    const response=await route.fetch()
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.goto('/')
  await page.getByRole('button',{name:'Public source',exact:true}).click()
  await page.getByRole('button',{name:'Load preserved sources',exact:true}).click()
  await page.getByLabel('Preserved analysis 1 source').selectOption(source.id)
  await page.getByLabel('Preserved analysis 2 source').selectOption(source.id)
  await page.getByLabel('Preserved analysis 2 transcript').selectOption(source.transcripts[1].transcript_id)
  await page.getByRole('button',{name:'Compare preserved sources',exact:true}).click()
  await expect.poll(()=>Boolean(release)).toBe(true)
  const newA=source.transcripts[2].transcript_id
  await page.getByLabel('Preserved analysis 1 transcript').selectOption(newA)
  release!()
  await expect(page.getByRole('status')).toContainText('Selection changed while comparing')
  await expect(page.getByLabel('Preserved analysis 1 transcript')).toHaveValue(newA)
  await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toHaveCount(0)
  await page.unroute('**/api/sources/compare')
  await page.getByRole('button',{name:'Compare preserved sources',exact:true}).click()
  await page.getByRole('heading',{name:'Compared analyses',exact:true}).waitFor()
  await page.getByRole('button',{name:'Snapshot JSON',exact:true}).click()
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  expect(JSON.parse(await page.getByLabel('Investigation JSON').inputValue()).snapshots[0].annotation.transcript_id).toBe(newA)
})

test('guided mode accepts a Unicode title within the API character limit',async({page})=>{
  const input=await (await page.request.get('/api/demos/transcript-switch')).json()
  input.title='🧬'.repeat(150)
  expect((await page.request.post('/api/investigations',{data:input})).ok()).toBe(true)
  await page.goto('/')
  await page.getByRole('button',{name:'Snapshot input',exact:true}).click()
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  await page.getByLabel('Investigation JSON').fill(JSON.stringify(input))
  await page.getByRole('button',{name:'Guided form',exact:true}).click()
  await expect(page.getByRole('button',{name:'Compare analyses',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Compare analyses',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toBeVisible()
})
