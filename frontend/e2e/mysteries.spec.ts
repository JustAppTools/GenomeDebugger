import {expect,test} from '@playwright/test'

const missions=[
  {number:'01',id:'vanishing-transcript',answer:'Transcript coverage differs; the reason for the omission is unknown.',wrong:'The analyses describe different alleles.'},
  {number:'02',id:'different-disguise',answer:'The substitutions match within the supplied local context.',wrong:'An independent reference assembly has been authenticated.'},
  {number:'03',id:'database-time-machine',answer:'The release changed; its causal role remains unproven.',wrong:'The release change definitely caused the consequence change.'},
]

test('three mysteries teach evidence, allow retry, and preserve browser progress',async({page})=>{
  await page.goto('/')
  await page.getByRole('button',{name:'Explore the Mystery Lab',exact:true}).click()
  for(const mission of missions){
    await page.getByRole('button',{name:`Open case ${mission.number}`,exact:false}).click()
    await expect(page.getByRole('heading',{name:'What does the evidence establish?'}).or(page.getByRole('heading',{name:'How far can this comparison take us?'})).or(page.getByRole('heading',{name:'Which conclusion is supported?'}))).toBeVisible()
    await page.getByRole('radio',{name:mission.wrong,exact:true}).check()
    await page.getByRole('button',{name:'Check hypothesis',exact:true}).click()
    await expect(page.getByRole('heading',{name:'A clue worth revisiting',exact:true})).toBeVisible()
    await page.getByRole('radio',{name:mission.answer,exact:true}).check()
    await page.getByRole('button',{name:'Check hypothesis',exact:true}).click()
    await expect(page.getByRole('heading',{name:'Evidence traced',exact:true})).toBeVisible()
    await page.getByRole('button',{name:'All case files',exact:true}).click()
  }
  await expect(page.getByText('3 / 3 evidence trails completed',{exact:true})).toBeVisible()
  await page.reload()
  await page.getByRole('button',{name:'Mystery lab',exact:true}).click()
  await expect(page.getByText('3 / 3 evidence trails completed',{exact:true})).toBeVisible()
})

test('a mystery opens in the real workbench and exports a replay-checked bundle',async({page})=>{
  await page.goto('/')
  await page.getByRole('button',{name:'Mystery lab',exact:true}).click()
  await page.getByRole('button',{name:'Open case 02',exact:false}).click()
  await page.getByRole('button',{name:'Replay stage 2: Reference',exact:true}).click()
  await page.getByRole('button',{name:'Inspect identity-inputs',exact:true}).click()
  await expect(page.locator('.case-evidence pre')).toContainText('reference_context')
  await page.getByRole('button',{name:'Open & save investigation',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toBeVisible()
  await expect(page.getByRole('region',{name:'Recorded analysis replay'})).toBeVisible()
  const downloading=page.waitForEvent('download')
  await page.getByRole('button',{name:'Bundle',exact:true}).click()
  const path=await(await downloading).path()
  const {readFile}=await import('node:fs/promises')
  const bundle=JSON.parse(await readFile(path!,'utf8'))
  expect((await page.request.post('/api/bundles/verify',{data:bundle})).ok()).toBe(true)
})

test('replay pauses at a difference, supports stepping, and fits mobile with reduced motion',async({page})=>{
  await page.setViewportSize({width:390,height:844})
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.goto('/')
  await page.getByRole('button',{name:'Mystery lab',exact:true}).click()
  await page.getByRole('button',{name:'Open case 01',exact:false}).click()
  await page.getByRole('button',{name:'Play replay',exact:true}).click()
  await expect(page.getByText('Paused at an observed difference.',{exact:true})).toBeVisible({timeout:8000})
  await expect(page.getByRole('button',{name:'Replay stage 3: Transcript'})).toHaveAttribute('aria-current','step')
  await page.getByRole('button',{name:'Previous replay step',exact:true}).click()
  await expect(page.getByRole('button',{name:'Replay stage 2: Reference'})).toHaveAttribute('aria-current','step')
  expect(await page.locator('.replay-scene').evaluate(el=>getComputedStyle(el).animationName)).toBe('none')
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)).toBe(false)
})
