import {expect,test} from '@playwright/test'
import {createHash} from 'node:crypto'
import {readFile} from 'node:fs/promises'

const headers='assembly,sequence_id,position,ref,alt,gene_id,transcript_id,consequence,tool,tool_version,source_name,source_release,context_start,reference_sequence\r\n'
const row=(transcript:string,effect:string)=>`GRCh38,NC_000001.11,102,C,T,G,${transcript},${effect},Tool,1,Source,1,100,GACGTACG\r\n`

test('BOM files with Unicode names and reordered annotations retain bytes and compare consistently',async({page})=>{
  const raw=['\ufeff'+headers+row('T2','intron_variant')+row('T1','missense_variant'),'\ufeff'+headers+row('T1','missense_variant')+row('T2','intron_variant')]
  const names=['a'.repeat(130)+'.csv','b'.repeat(50)+'🧬.csv']
  await page.goto('/#/input')
  await page.getByText('Import two annotated CSV/TSV files',{exact:true}).click()
  for(const side of [0,1])await page.getByLabel(`Analysis ${side+1} tabular file`).setInputFiles({name:names[side],mimeType:'text/csv',buffer:Buffer.from(raw[side])})
  const previewResponse=page.waitForResponse(r=>r.url().endsWith('/api/imports/tabular/preview'))
  await page.getByRole('button',{name:'Preview imported rows'}).click()
  const preview=await previewResponse
  expect(preview.status()).toBe(200)
  const data=await preview.json()
  for(const side of [0,1]){
    expect(data.input.snapshots[side].provenance.configuration.original_utf8).toBe(raw[side])
    expect(data.files[side].original_sha256).toBe(createHash('sha256').update(Buffer.from(raw[side])).digest('hex'))
  }
  await page.getByRole('button',{name:'Review these two analyses'}).click()
  const comparedResponse=page.waitForResponse(r=>r.url().endsWith('/api/investigations')&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Compare analyses',exact:true}).click()
  const compared=await(await comparedResponse).json()
  expect(compared.differences.filter((d:any)=>d.meaningful)).toEqual([])
  expect(compared.findings.some((f:any)=>f.cause==='transcript selection')).toBe(false)
  await expect(page.getByText(/Tabular overview rows are stable display anchors/)).toBeVisible()
  const download=page.waitForEvent('download')
  await page.getByRole('button',{name:'Full bundle',exact:true}).click()
  const file=await(await download).path()
  const bundle=JSON.parse(await readFile(file!,'utf8'))
  expect(bundle.entries.investigation.input.snapshots[0].provenance.configuration.original_utf8).toBe(raw[0])
  expect((await page.request.post('/api/bundles/verify',{data:bundle})).status()).toBe(200)
})

test('home draft recovery follows save, resume and discard without a reload',async({page})=>{
  await page.goto('/')
  await page.getByRole('button',{name:'Enter my results',exact:true}).click()
  await page.getByLabel('Investigation title').fill('Draft recovery browser regression')
  await page.getByRole('button',{name:'Save draft locally'}).click()
  await page.getByRole('button',{name:'Results',exact:true}).click()
  await page.getByRole('button',{name:'Resume saved draft',exact:true}).click()
  await expect(page.getByLabel('Investigation title')).toHaveValue('Draft recovery browser regression')
  await page.getByRole('button',{name:'Discard saved draft'}).click()
  await page.getByRole('button',{name:'Results',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Choose a starting point'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Resume saved draft'})).toHaveCount(0)
})

test('a pending notes save locks the editor and an older tab archives without overwriting notes',async({page,context})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title=`Notes concurrency ${Date.now()}`
  const saved=await(await page.request.post('/api/investigations',{data:input})).json()
  const other=await context.newPage()
  for(const tab of [page,other]){
    await tab.goto('/#/library');await tab.getByLabel('Search investigations').fill(saved.id)
    await expect(tab.locator('.library-row')).toHaveCount(1)
  }
  let waiting=false;let release:()=>void=()=>{}
  await page.route(`**/api/workspace/library/${saved.id}/label`,async route=>{
    if(route.request().method()!=='POST'){await route.continue();return}
    const response=await route.fetch();waiting=true
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.locator('.library-row').filter({hasText:saved.id}).getByRole('button',{name:'Edit details'}).click()
  await page.getByRole('textbox',{name:'Notes',exact:true}).fill('Preserve this review')
  await page.getByRole('button',{name:'Save library details'}).click()
  await expect.poll(()=>waiting).toBe(true)
  await expect(page.getByRole('textbox',{name:'Notes',exact:true})).toBeDisabled()
  await expect(page.getByLabel('Display name')).toBeDisabled()
  const archived=other.waitForResponse(r=>r.url().endsWith(`/${saved.id}/label`)&&r.request().method()==='POST')
  await other.getByRole('button',{name:'Archive',exact:true}).click()
  const response=await archived
  expect(response.request().postDataJSON()).toEqual({archived:true})
  expect((await response.json()).notes).toBe('Preserve this review')
  release()
  await expect(page.getByRole('button',{name:'Save library details'})).toHaveCount(0)
  const label=await(await page.request.get(`/api/workspace/library/${saved.id}/label`)).json()
  expect(label.notes).toBe('Preserve this review');expect(label.archived).toBe(true)
  await other.close()
})

test('conflicting library edits keep the unsaved text visible',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json();input.title=`Notes conflict ${Date.now()}`
  const saved=await(await page.request.post('/api/investigations',{data:input})).json()
  await page.goto('/#/library');await page.getByLabel('Search investigations').fill(saved.id)
  await page.locator('.library-row').filter({hasText:saved.id}).getByRole('button',{name:'Edit details'}).click()
  await page.getByRole('textbox',{name:'Notes',exact:true}).fill('My pending review')
  expect((await page.request.post(`/api/workspace/library/${saved.id}/label`,{data:{notes:'Another tab saved this'}})).ok()).toBe(true)
  await page.getByRole('button',{name:'Save library details'}).click()
  await expect(page.getByRole('alert')).toContainText('another tab')
  await expect(page.getByRole('textbox',{name:'Notes',exact:true})).toHaveValue('My pending review')
  await expect(page.getByRole('textbox',{name:'Notes',exact:true})).toBeEnabled()
  expect((await(await page.request.get(`/api/workspace/library/${saved.id}/label`)).json()).notes).toBe('Another tab saved this')
})

test('re-comparison preserves Recent names and refreshes an archive change',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json();input.title=`Recent labels ${Date.now()}`
  const saved=await(await page.request.post('/api/investigations',{data:input})).json()
  const url=`/api/workspace/library/${saved.id}/label`
  expect((await page.request.post(url,{data:{display_name:'A recognizable browser comparison'}})).ok()).toBe(true)
  await page.goto(`/#/comparison/${saved.id}/overview`)
  const recent=page.getByRole('complementary').getByRole('button',{name:/A recognizable browser comparison/})
  await expect(recent).toBeVisible()
  const metadata=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='GET')
  await page.getByRole('button',{name:'Run comparison',exact:true}).click()
  await metadata;await expect(recent).toBeVisible()
  expect((await page.request.post(url,{data:{archived:true}})).ok()).toBe(true)
  await page.getByRole('button',{name:'Run comparison',exact:true}).click()
  await expect(recent).toHaveCount(0)
})

test('each alternate teaching example describes only the evidence it contains',async({page})=>{
  for(const kind of ['matching','uncertain']){
    const input=await(await page.request.get('/api/demos/'+kind)).json()
    const saved=await(await page.request.post('/api/investigations',{data:input})).json()
    await page.goto(`/#/comparison/${saved.id}/overview`)
    await expect(page.getByText('No controlled lookup was provided or replayed for this example.')).toBeVisible()
    await expect(page.getByText('The controlled lookup repeats those outputs within this constructed example. It does not test a real annotation system.')).toHaveCount(0)
    if(kind==='uncertain')await expect(page.getByText(/This made-up example omits reference context/)).toBeVisible()
  }
})

test('additional variant evidence exposes the actual identity status and reason',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json();input.controlled_lookup=null
  input.title=`Additional identity ${Date.now()}`
  for(const snapshot of input.snapshots)snapshot.variant_records=[{variant:{assembly:'GRCh38',sequence_id:'NC_000001.11',position:104,ref:'T',alt:'G'},annotations:[{gene_id:'G2',transcript_id:'T2',consequence:'intron_variant'}]}]
  const saved=await(await page.request.post('/api/investigations',{data:input})).json()
  const evidence=saved.evidence.find((e:any)=>e.id.startsWith('variant-record-'))
  await page.goto(`/#/comparison/${saved.id}/evidence`)
  await page.getByRole('navigation',{name:'Evidence records'}).getByRole('button',{name:/Additional variant identity/}).click()
  await expect(page.locator('.evidence-detail > .evidence-facts')).toContainText('unresolved')
  await expect(page.locator('.evidence-detail > .evidence-facts')).toContainText(evidence.data.explanation)
  await expect(page.locator('.raw-record pre')).not.toBeVisible()
})
