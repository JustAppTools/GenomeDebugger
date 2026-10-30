import {prepareExample,prepareGuided} from './workspace-helpers'
import {expect,test} from '@playwright/test'

test('the main flow explains results without game features and keeps technical detail optional',async({page})=>{
  await page.goto('/')
  await expect(page.getByRole('button',{name:/mystery|play replay|check hypothesis/i})).toHaveCount(0)
  await expect(page.getByRole('heading',{name:'Understand why two analysis results differ'})).toBeVisible()
  await prepareExample(page)
  await page.getByRole('button',{name:/^Try (?:an )?example(?: again)?$/}).first().click()
  await expect(page.getByRole('heading',{name:'What this comparison tells you'})).toBeVisible()
  await expect(page.getByText('An explanation was reproduced within this made-up example.',{exact:true})).toBeVisible()
  await expect(page.locator('.snapshot-card').first()).not.toBeVisible()
  await page.getByText('Explain the terms',{exact:true}).click()
  await expect(page.getByText('One RNA version produced from a gene.',{exact:false})).toBeVisible()
  await page.getByText('Show technical details',{exact:true}).click()
  await expect(page.locator('.snapshot-card')).toHaveCount(2)
  await expect(page.locator('.snapshot-card').first()).toBeVisible()
  await page.getByRole('button',{name:'See the changes',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Changes between the results'})).toBeVisible()
  await expect(page.locator('td.field-name').filter({hasText:'Predicted effect'}).first()).toBeVisible()
  await page.getByRole('button',{name:'Enter results',exact:true}).click()
  await prepareGuided(page)
  await expect(page.getByLabel('Analysis 1 gene id',{exact:true})).toBeVisible()
})

test('a new visitor can start the guided form on a phone',async({page})=>{
  await page.setViewportSize({width:390,height:844})
  await page.goto('/')
  await page.getByRole('button',{name:'Enter my results',exact:true}).click()
  await expect(page.getByLabel('Investigation title')).toBeVisible()
  await expect(page.getByRole('button',{name:'Compare analyses',exact:true})).toBeDisabled()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)).toBe(false)
})
