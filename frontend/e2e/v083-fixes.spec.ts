import {openWorkspaceAdvanced,openWorkspaceInputs,openWorkspaceSources} from './workspace-helpers'
// Corrected 0.8.2 audit workflows, released in 0.8.3. Synthetic isolated data only.
import {expect,test} from '@playwright/test'
import {createHash} from 'node:crypto'

async function create(page:any,title:string){
  const input=await(await page.request.get('/api/demos/transcript-switch')).json();input.title=title
  const response=await page.request.post('/api/investigations',{data:input});expect(response.status()).toBe(200)
  return response.json()
}

test('near-limit saved draft can resume after leaving the input screen',async({page})=>{
  const text=JSON.stringify('\\'.repeat(999990))
  await page.goto('/#/input');await page.getByRole('button',{name:'JSON editor'}).click()
  await page.getByLabel('Investigation JSON').fill(text)
  await page.getByRole('button',{name:'Save draft locally'}).click()
  await expect(page.getByText('Draft saved in this browser. It is editable and separate from completed comparisons.')).toBeVisible()
  await page.getByRole('link',{name:'Guide',exact:true}).click()
  await openWorkspaceInputs(page)
  await page.getByRole('button',{name:'Resume saved draft',exact:true}).click()
  await expect(page.getByLabel('Investigation JSON')).toHaveValue(text)
})

test('guided entry requires context start when only reference letters are entered',async({page})=>{
  const saved=await create(page,'Context start audit '+Date.now())
  await page.goto(`/#/comparison/${saved.id}/input`)
  await page.getByRole('button',{name:'Guided form',exact:true}).click()
  await page.getByRole('button',{name:'Show all fields (experienced users)'}).click()
  await page.getByRole('button',{name:'Remove reference context for Analysis 1',exact:true}).click()
  const letters=page.getByLabel('Analysis 1 reference sequence',{exact:true})
  await letters.locator('..').locator('..').locator('..').getByText('Optional reference context',{exact:true}).click()
  await letters.fill('ACGT')
  await expect(page.getByLabel('Analysis 1 context start',{exact:true})).toHaveValue('')
})

test('opening Help retains a public query and unsaved candidate outputs',async({page})=>{
  await page.goto('/#/source');await page.getByLabel('Position',{exact:true}).fill('12345')
  await page.getByRole('link',{name:'Guide',exact:true}).click()
  await openWorkspaceSources(page)
  await expect(page.getByLabel('Position',{exact:true})).toHaveValue('12345')
  const saved=await create(page,'Candidate navigation audit '+Date.now())
  expect((await page.request.post(`/api/investigations/${saved.id}/regression-cases`,{data:{name:'Navigation baseline'}})).status()).toBe(200)
  await page.goto(`/#/comparison/${saved.id}/regression`)
  await page.getByLabel('Candidate analysis 1 consequence',{exact:true}).fill('stop_gained')
  await page.getByRole('link',{name:'Guide',exact:true}).click()
  await openWorkspaceAdvanced(page,'Saved tests')
  await expect(page.getByLabel('Candidate analysis 1 consequence',{exact:true})).toHaveValue('stop_gained')
})

test('Enter results retains unfinished JSON in its editor',async({page})=>{
  await page.goto('/#/input');await page.getByRole('button',{name:'JSON editor'}).click()
  const text='{"title":"Keep unfinished analysis", "snapshots":['
  await page.getByLabel('Investigation JSON').fill(text)
  await page.getByRole('link',{name:'Guide',exact:true}).click()
  await openWorkspaceInputs(page)
  await expect(page.getByLabel('Investigation JSON')).toHaveValue(text)
  await expect(page.getByRole('alert')).toContainText('Repair the JSON')
})

test('leaving a pending notes save keeps the restored editor revision current',async({page})=>{
  const saved=await create(page,'Pending editor audit '+Date.now()),url=`/api/workspace/library/${saved.id}/label`
  await page.goto('/#/library');await page.getByLabel('Search investigations').fill(saved.id)
  await page.locator('.library-row').filter({hasText:saved.id}).getByRole('button',{name:'Edit details'}).click()
  await page.getByRole('textbox',{name:'Notes',exact:true}).fill('First saved notes')
  let waiting=false,release:()=>void=()=>{},first=true
  await page.route(`**${url}`,async route=>{
    if(route.request().method()!=='POST'||!first){await route.continue();return}
    first=false;const response=await route.fetch();waiting=true
    await new Promise<void>(resolve=>{release=resolve});await route.fulfill({response})
  })
  await page.getByRole('button',{name:'Save library details'}).click()
  await expect.poll(()=>waiting).toBe(true)
  await page.getByRole('link',{name:'Guide',exact:true}).click()
  await page.getByRole('link',{name:'Saved work',exact:true}).click()
  await expect(page.getByRole('textbox',{name:'Notes',exact:true})).toHaveValue('First saved notes')
  const firstResponse=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='POST')
  release();await(await firstResponse).finished()
  await page.getByRole('textbox',{name:'Notes',exact:true}).fill('Additional notes after returning')
  const response=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Save library details'}).click()
  expect((await response).status()).toBe(200)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('custom row policy retains the verified selection explanation',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  for(const snapshot of input.snapshots)snapshot.provenance.configuration.row_order_policy='manual-input-order'
  input.title='Custom row policy audit '+Date.now()
  const response=await page.request.post('/api/investigations',{data:input});expect(response.status()).toBe(200)
  const result=await response.json();expect(result.findings.some((f:any)=>f.cause==='transcript selection'&&f.status==='verified')).toBe(true)
  await page.goto(`/#/comparison/${result.id}/overview`)
  await expect(page.locator('.comparison-story')).toContainText('The selected transcripts also differ')
  await expect(page.locator('.findings-readable')).toContainText('Changing only the selected transcript reproduces')
})

test('keyboard focus is visible on both JSON import controls',async({page})=>{
  await page.goto('/#/input')
  await page.locator('main h1').focus()
  const toolbar=page.locator('.input-toolbar')
  const before=await toolbar.screenshot({path:'../.build/fixes083-import-focus-before.png'})
  const input=page.getByLabel('Import input JSON',{exact:true})
  await page.getByRole('button',{name:'JSON editor',exact:true}).focus()
  await page.keyboard.press('Tab')
  await expect(input).toBeFocused()
  const after=await toolbar.screenshot({path:'../.build/fixes083-import-focus-after.png'})
  expect(createHash('sha256').update(before).digest('hex')).not.toBe(createHash('sha256').update(after).digest('hex'))
  await page.goto('/#/library');await page.locator('main h1').focus()
  await expect(page.locator('.library-list')).toHaveAttribute('aria-busy','false')
  const bundle=page.locator('.library-panel')
  const bundleBefore=await bundle.screenshot({path:'../.build/fixes083-bundle-focus-before.png'})
  await page.keyboard.press('Tab');await expect(page.getByLabel('Import replay-checked bundle',{exact:true})).toBeFocused()
  await expect(page.locator('.bundle-import')).toHaveCSS('outline-width','3px')
  const bundleAfter=await bundle.screenshot({path:'../.build/fixes083-bundle-focus-after.png'})
  expect(createHash('sha256').update(bundleBefore).digest('hex')).not.toBe(createHash('sha256').update(bundleAfter).digest('hex'))
})

test('clearing an optional protein entry preserves matching blank fields',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title='Optional field audit '+Date.now();input.controlled_lookup=null
  input.snapshots[1]=structuredClone(input.snapshots[0]);input.snapshots[1].id='B';input.snapshots[1].label='B'
  for(const snapshot of input.snapshots)snapshot.annotation.protein_consequence=null
  const response=await page.request.post('/api/investigations',{data:input}),saved=await response.json()
  expect(saved.differences).toEqual([])
  await page.goto(`/#/comparison/${saved.id}/input`)
  await page.getByRole('button',{name:'Guided form'}).click();await page.getByRole('button',{name:'Show all fields (experienced users)'}).click()
  const first=page.getByLabel('Analysis 1 protein consequence',{exact:true})
  await first.fill('Temporary value');await first.fill('')
  await expect(first).toHaveValue('');await expect(page.getByLabel('Analysis 2 protein consequence',{exact:true})).toHaveValue('')
  const compared=page.waitForResponse(r=>r.url().endsWith('/api/investigations')&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Compare analyses',exact:true}).click()
  const result=await(await compared).json()
  expect(result.differences).toEqual([])
})

test('a failed local-data request stops loading and can be retried',async({page})=>{
  await page.route('**/api/workspace/data',route=>route.abort('failed'))
  await page.goto('/#/data')
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByText('Loading storage details…')).toHaveCount(0)
  await page.unroute('**/api/workspace/data')
  await page.getByRole('button',{name:'Retry storage details'}).click()
  await expect(page.getByText('Database location',{exact:true})).toBeVisible()
})
