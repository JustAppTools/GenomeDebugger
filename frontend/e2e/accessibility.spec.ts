import {expect,test,type Page} from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

async function check(page:Page){
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()
  expect.soft(result.violations.map(v=>({rule:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,reason:n.failureSummary}))}))).toEqual([])
}
test('core screens pass automated accessibility checks and keyboard skip preserves the route',async({page})=>{
  test.setTimeout(90000)
  await page.goto('/')
  await check(page)
  for(const route of ['input','source','help','library','data']){
    await page.goto(`/#/${route}`)
    await expect(page.locator('main h1')).toBeVisible()
    if(route==='library')await expect(page.getByRole('heading',{name:'Investigation library'})).toBeVisible()
    await check(page)
  }
  await page.goto('/')
  await page.getByRole('button',{name:'Try an example',exact:true}).click()
  await expect(page.getByRole('heading',{name:'What this comparison tells you'})).toBeVisible()
  await check(page)
  const route=page.url()
  await page.getByRole('link',{name:'Skip to main content'}).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()
  await expect(page).toHaveURL(route)
  await page.getByRole('button',{name:'How was this checked?'}).click()
  await check(page)
})
