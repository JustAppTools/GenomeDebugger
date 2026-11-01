import {expect,test} from '@playwright/test'
import {readFileSync} from 'node:fs'
const fixture=JSON.parse(readFileSync(new URL('../../fixtures/transcript-switch.json',import.meta.url),'utf-8'))

test('report preview is visible and focused, and closing restores its trigger',async({page})=>{
  await page.setViewportSize({width:1280,height:720})
  await page.goto('/')
  await page.getByRole('button',{name:'Try an example',exact:true}).click()
  const trigger=page.getByRole('button',{name:'Preview readable report',exact:true})
  await trigger.click()
  const preview=page.getByRole('region',{name:'Readable report preview'})
  await expect(preview).toBeFocused()
  const frame=await page.getByTitle('Comparison report preview').boundingBox()
  expect(frame?.y).toBeGreaterThanOrEqual(0)
  expect(frame!.y).toBeLessThan(720)
  await page.getByRole('button',{name:'Close report preview'}).click()
  await expect(trigger).toBeFocused()
})

test('failed example retains loaded inputs at the input route',async({page})=>{
  await page.route('**/api/investigations',async route=>{
    if(route.request().method()==='POST')return route.fulfill({status:503,json:{detail:'Injected capacity failure'}})
    return route.continue()
  })
  await page.goto('/')
  await page.getByRole('button',{name:'Try an example',exact:true}).click()
  await expect(page.getByRole('alert')).toContainText('Demo comparison failed')
  await expect(page).toHaveURL(/#\/input$/)
  await expect(page.getByLabel('Investigation JSON')).toHaveValue(/Synthetic transcript/)
})

for(const route of ['differences','evidence','regression'])test(`orphan ${route} link provides working recovery`,async({page})=>{
  await page.goto(`/#/${route}`)
  await expect(page.getByRole('heading',{name:'Choose a comparison first'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Understand',exact:true})).not.toHaveAttribute('aria-current')
  await page.getByRole('button',{name:'Open saved work'}).click()
  await expect(page.getByRole('heading',{name:'Saved work'})).toBeVisible()
})

test('deletion completing after navigation removes the recent-work entry',async({page})=>{
  const payload=structuredClone(fixture);payload.title=`Deletion navigation regression ${Date.now()}`
  const saved=await (await page.request.post('/api/investigations',{data:payload})).json()
  await page.goto('/')
  await expect(page.getByRole('button',{name:payload.title,exact:false})).toBeVisible()
  await page.getByRole('link',{name:'Saved work',exact:true}).click()
  await page.getByRole('textbox',{name:'Search investigations'}).fill(payload.title)
  const item=page.locator('.library-row').filter({hasText:payload.title})
  await item.getByText('Permanent deletion',{exact:true}).click()
  let release!:()=>void
  const gate=new Promise<void>(resolve=>{release=resolve})
  let received!:()=>void
  const started=new Promise<void>(resolve=>{received=resolve})
  await page.route(`**/api/investigations/${saved.id}`,async route=>{
    if(route.request().method()!=='DELETE')return route.continue()
    received();await gate;await route.continue()
  })
  page.once('dialog',dialog=>dialog.accept())
  await item.getByRole('button',{name:'Delete',exact:true}).click()
  await started
  await page.getByRole('button',{name:'GenomeDebugger home'}).click()
  const completed=page.waitForResponse(response=>response.url().endsWith(`/api/investigations/${saved.id}`)&&response.request().method()==='DELETE')
  release();await completed
  await expect(page.getByRole('button',{name:payload.title,exact:false})).toHaveCount(0)
})
