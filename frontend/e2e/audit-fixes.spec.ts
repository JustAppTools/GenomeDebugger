import {prepareExample,prepareGuided} from './workspace-helpers'
import {expect,test,type Page} from '@playwright/test'

async function example(page:Page) {
  await page.goto('/')
  await prepareExample(page)
  await page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/}).first().click()
  await page.getByRole('heading',{name:'What this comparison tells you'}).waitFor()
}

test('change search accepts displayed labels and internal identifiers',async({page})=>{
  await example(page)
  await page.getByRole('button',{name:'See the changes',exact:true}).click()
  for(const query of ['Predicted effect','  PREDICTED EFFECT  ','consequence']) {
    await page.getByLabel('Search fields',{exact:true}).fill(query)
    await expect(page.locator('td.field-name').filter({hasText:'Predicted effect'})).toBeVisible()
  }
  await page.getByLabel('Search fields',{exact:true}).fill('No such field')
  await expect(page.getByText('No differences match these filters.')).toBeVisible()
})

test('candidate verdicts identify edits during a run and after it completes',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title='Candidate freshness regression'
  const result=await(await page.request.post('/api/investigations',{data:input})).json()
  const baseline=await page.request.post(`/api/investigations/${result.id}/regression-cases`,{data:{name:'Candidate freshness'}})
  expect(baseline.ok()).toBe(true)
  await page.goto('/')
  await page.getByRole('button',{name:'Saved comparisons',exact:true}).click()
  await page.locator('.library-row').filter({hasText:result.id}).getByRole('button',{name:'Open',exact:true}).click()
  await page.getByRole('complementary').getByRole('button',{name:'Saved tests',exact:true}).click()
  await page.getByRole('button',{name:'Check candidate',exact:true}).waitFor()
  let release:(()=>void)|undefined
  await page.route('**/api/regression-cases/*/runs',async route=>{
    if(route.request().method()!=='POST'){await route.continue();return}
    const response=await route.fetch()
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await page.getByRole('button',{name:'Check candidate',exact:true}).click()
  await expect.poll(()=>Boolean(release)).toBe(true)
  await page.getByLabel('Candidate analysis 2 consequence',{exact:true}).fill('stop_gained')
  release!()
  await expect(page.getByRole('heading',{name:'Previous candidate passed',exact:true})).toBeVisible()
  await expect(page.getByRole('status')).toContainText('Candidate input has changed')
  await expect(page.getByRole('heading',{name:'Regression passed',exact:true})).toHaveCount(0)
  await page.unroute('**/api/regression-cases/*/runs')
  await page.getByRole('button',{name:'Check candidate',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Regression failed',exact:true})).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  await page.getByRole('button',{name:'Advanced JSON',exact:true}).click()
  const next=JSON.parse(await page.getByLabel('Candidate input JSON').inputValue())
  next.title='Edited after completed run'
  await page.getByLabel('Candidate input JSON').fill(JSON.stringify(next))
  await expect(page.getByRole('heading',{name:'Previous candidate failed',exact:true})).toBeVisible()
  await expect(page.getByRole('status')).toContainText('Candidate input has changed')
  await page.locator('.history-list button').last().click()
  await expect(page.getByRole('heading',{name:'Saved candidate passed',exact:true})).toBeVisible()
  await expect(page.getByRole('status')).toContainText('viewing a saved candidate run')
})

for(const invalidOldFile of [false,true]) {
  test(`the latest input file wins over an earlier ${invalidOldFile?'invalid':'valid'} file read`,async({page})=>{
    const input=await(await page.request.get('/api/demos/transcript-switch')).json()
    await page.goto('/')
    await page.getByRole('button',{name:'Enter results',exact:true}).click()
    await prepareGuided(page)
    await page.evaluate(()=>{
      const original=File.prototype.arrayBuffer
      File.prototype.arrayBuffer=async function(){
        const value=await original.call(this)
        if(this.name==='slow.json') await new Promise<void>(resolve=>{(window as any).releaseInputFile=resolve})
        return value
      }
    })
    const content=invalidOldFile?'invalid json':JSON.stringify({...input,title:'Old slow input'})
    await page.getByLabel('Import input JSON',{exact:true}).setInputFiles({name:'slow.json',mimeType:'application/json',buffer:Buffer.from(content)})
    await expect.poll(()=>page.evaluate(()=>Boolean((window as any).releaseInputFile))).toBe(true)
    await page.getByLabel('Import input JSON',{exact:true}).setInputFiles({name:'new.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({...input,title:'New selected input'}))})
    await expect(page.getByLabel('Investigation JSON',{exact:true})).toHaveValue(/New selected input/)
    await page.evaluate(()=>(window as any).releaseInputFile())
    // A fresh user interaction after the old read resumes also checks that it
    // did not leave the latest operation busy or install an old parse error.
    await expect(page.getByRole('button',{name:'Compare',exact:true})).toBeEnabled()
    await expect(page.getByLabel('Investigation JSON',{exact:true})).toHaveValue(/New selected input/)
    await expect(page.getByRole('alert')).toHaveCount(0)
  })
}

test('edits made while an example loads are preserved and explained',async({page})=>{
  await page.goto('/')
  await page.getByRole('button',{name:'Enter results',exact:true}).click()
  await prepareGuided(page)
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  let release:(()=>void)|undefined
  await page.route('**/api/demos/transcript-switch',async route=>{
    const response=await route.fetch()
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response})
  })
  await prepareExample(page)
  await page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/}).click()
  await expect.poll(()=>Boolean(release)).toBe(true)
  const draft='{"title":"Keep my new draft"}'
  await page.getByLabel('Investigation JSON',{exact:true}).fill(draft)
  release!()
  await expect(page.getByRole('status')).toContainText('Your draft was kept')
  await expect(page.getByLabel('Investigation JSON',{exact:true})).toHaveValue(draft)
  await expect(page.getByRole('heading',{name:'What this comparison tells you'})).toHaveCount(0)
  await expect(page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/})).toBeEnabled()
})

test('typing during a file read keeps the newer guided draft',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  await page.goto('/')
  await page.getByRole('button',{name:'Enter results',exact:true}).click()
  await prepareGuided(page)
  await page.evaluate(()=>{
    File.prototype.arrayBuffer=()=>new Promise<ArrayBuffer>(resolve=>{(window as any).releaseInputFile=resolve})
  })
  await page.getByLabel('Import input JSON',{exact:true}).setInputFiles({name:'slow.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(input))})
  await expect.poll(()=>page.evaluate(()=>Boolean((window as any).releaseInputFile))).toBe(true)
  await page.getByLabel('Investigation title').fill('Newer guided draft')
  await page.evaluate(content=>(window as any).releaseInputFile(new TextEncoder().encode(content).buffer),JSON.stringify(input))
  await expect(page.getByRole('status').filter({hasText:'Your draft was kept'})).toBeVisible()
  await expect(page.getByLabel('Investigation title')).toHaveValue('Newer guided draft')
})

test('an input file supersedes a pending example request',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title='File chosen after example'
  await page.goto('/')
  await page.getByRole('button',{name:'Enter results',exact:true}).click()
  await prepareGuided(page)
  let release:(()=>void)|undefined
  let finished=false
  await page.route('**/api/demos/transcript-switch',async route=>{
    const response=await route.fetch()
    await new Promise<void>(resolve=>{release=resolve})
    await route.fulfill({response});finished=true
  })
  await prepareExample(page)
  await page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/}).click()
  await expect.poll(()=>Boolean(release)).toBe(true)
  await page.getByLabel('Import input JSON',{exact:true}).setInputFiles({name:'latest.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(input))})
  await expect(page.getByLabel('Investigation JSON')).toHaveValue(/File chosen after example/)
  release!()
  await expect.poll(()=>finished).toBe(true)
  await expect(page.getByLabel('Investigation JSON')).toHaveValue(/File chosen after example/)
  await expect(page.getByRole('button',{name:'Compare',exact:true})).toBeEnabled()
})
