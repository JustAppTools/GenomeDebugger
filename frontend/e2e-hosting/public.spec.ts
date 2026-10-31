import {expect,test} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('public visitors keep separate records and notes, including after reload',async({page,browser,baseURL})=>{
  await page.goto('/')
  await expect(page.getByLabel('Public preview storage')).toBeVisible()
  const cookie=(await page.context().cookies()).find(c=>c.name==='__Host-genomedebugger-workspace')!
  expect(cookie.httpOnly&&cookie.secure).toBe(true)
  expect(await page.evaluate(()=>document.cookie)).not.toContain(cookie.value)
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title='Visitor A comparison '+Date.now()
  const saved=await(await page.request.post('/api/investigations',{data:input})).json()
  await page.request.post(`/api/workspace/library/${saved.id}/label`,{data:{notes:'Only visitor A can see these notes'}})
  const other=await browser.newContext({baseURL,ignoreHTTPSErrors:true})
  try{
    const b=await other.newPage();await b.goto('/')
    expect((await other.request.get(`/api/investigations/${saved.id}`)).status()).toBe(404)
    expect(await(await other.request.get('/api/investigations')).json()).toEqual([])
    const same=await(await other.request.post('/api/investigations',{data:input})).json()
    expect(same.id).toBe(saved.id)
    expect((await(await other.request.get(`/api/workspace/library/${same.id}/label`)).json()).notes).toBe('')
    await page.reload()
    expect((await(await page.request.get(`/api/workspace/library/${saved.id}/label`)).json()).notes).toBe('Only visitor A can see these notes')
  }finally{await other.close()}
})

test('hosted demo and readable report work over HTTPS and explain temporary storage',async({page})=>{
  await page.goto('/')
  await page.getByRole('button',{name:'Try an example',exact:true}).click()
  await expect(page.getByRole('heading',{name:'What this comparison tells you'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Copy workspace link'})).toBeVisible()
  await page.getByRole('button',{name:'Preview readable report'}).click()
  await expect(page.frameLocator('iframe[title="Comparison report preview"]').getByRole('heading').first()).toBeVisible()
})

test('a full bundle transfers data explicitly between visitor workspaces',async({page,browser,baseURL})=>{
  await page.goto('/')
  const input=await(await page.request.get('/api/demos/transcript-switch')).json();input.title='Portable hosted comparison '+Date.now()
  const saved=await(await page.request.post('/api/investigations',{data:input})).json()
  const bundle=await(await page.request.get(`/api/investigations/${saved.id}/bundle`)).json()
  const other=await browser.newContext({baseURL,ignoreHTTPSErrors:true})
  try{
    const response=await other.request.post('/api/bundles/import',{data:bundle});expect(response.status()).toBe(200)
    const id=(await response.json()).imported
    const result=await(await other.request.get(`/api/investigations/${id}`)).json()
    expect(result.input).toEqual(saved.input)
  }finally{await other.close()}
})

test('hosted data and help screens stay clear and pass core accessibility checks',async({page})=>{
  await page.goto('/#/data')
  await expect(page.getByRole('heading',{name:'Your temporary browser workspace'})).toBeVisible()
  await expect(page.getByRole('heading',{name:'Keep and transfer your comparisons'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Stop application'})).toHaveCount(0)
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()
  expect(result.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))).toEqual([])
})
