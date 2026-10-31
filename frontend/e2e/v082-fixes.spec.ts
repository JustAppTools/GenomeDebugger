import {openWorkspaceAdvanced} from './workspace-helpers'
// Browser regressions for the 0.8.1 audit, fixed in 0.8.2.
import {expect,test} from '@playwright/test'
import {readFile} from 'node:fs/promises'
import {execFileSync} from 'node:child_process'
import path from 'node:path'

async function create(page:any,title:string){
  const input=await(await page.request.get('/api/demos/transcript-switch')).json();input.title=title
  return (await page.request.post('/api/investigations',{data:input})).json()
}
test('a favorite request cannot bypass another tab note conflict',async({page})=>{
  const saved=await create(page,'Audit notes revision '+Date.now()),url=`/api/workspace/library/${saved.id}/label`
  await page.goto('/#/library');await page.getByLabel('Search investigations').fill(saved.id)
  await page.locator('.library-row').filter({hasText:saved.id}).getByRole('button',{name:'Edit details'}).click()
  await page.getByRole('textbox',{name:'Notes',exact:true}).fill('Local pending review')
  expect((await page.request.post(url,{data:{notes:'Another tab saved this'}})).status()).toBe(200)
  const flagged=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Favorite',exact:true}).click();await flagged
  await expect(page.getByRole('button',{name:'Save library details'})).toBeEnabled()
  const edited=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Save library details'}).click()
  expect((await edited).status()).toBe(409)
  expect((await(await page.request.get(url)).json()).notes).toBe('Another tab saved this')
  await expect(page.getByRole('alert')).toContainText('another tab')
  await expect(page.getByRole('textbox',{name:'Notes',exact:true})).toHaveValue('Local pending review')
})

test('editing different records and leaving the section preserves unsaved details',async({page})=>{
  const title='Audit editor switch '+Date.now()
  const a=await create(page,title+' A'),b=await create(page,title+' B')
  await page.goto('/#/library');await page.getByLabel('Search investigations').fill(title)
  const rowA=page.locator('.library-row').filter({hasText:a.id}),rowB=page.locator('.library-row').filter({hasText:b.id})
  await rowA.getByRole('button',{name:'Edit details'}).click()
  await page.getByRole('textbox',{name:'Notes',exact:true}).fill('Unsaved review')
  await rowB.getByRole('button',{name:'Edit details'}).click()
  await expect(page.getByRole('textbox',{name:'Notes',exact:true})).toHaveValue('')
  await rowA.getByRole('button',{name:'Edit details'}).click()
  await expect(page.getByRole('textbox',{name:'Notes',exact:true})).toHaveValue('Unsaved review')
  await page.getByRole('link',{name:'Guide',exact:true}).click()
  await page.getByRole('link',{name:'Saved work',exact:true}).click()
  await expect(page.getByRole('textbox',{name:'Notes',exact:true})).toHaveValue('Unsaved review')
  await page.getByRole('button',{name:'Cancel editing'}).click()
})

test('undo to the compared input removes the stale-result warning',async({page})=>{
  const saved=await create(page,'Audit undo '+Date.now())
  await page.goto(`/#/comparison/${saved.id}/overview`)
  await openWorkspaceAdvanced(page,'Input JSON')
  const input=page.getByLabel('Investigation JSON'),original=await input.inputValue()
  await input.fill(original+' ');await page.getByRole('button',{name:'Undo edit'}).click()
  await expect(input).toHaveValue(original)
  await page.getByRole('link',{name:'Compare',exact:true}).click()
  await expect(page.getByText(/Your input has changed\. The displayed comparison/)).toHaveCount(0)
})

test('readable report includes unchanged extra transcripts from an actual multi-variant comparison',async({page})=>{
  const input=await(await page.request.get('/api/demos/matching')).json();input.title='Audit report rows '+Date.now()
  for(const snapshot of input.snapshots){
    snapshot.annotations=[{gene_id:'G-EXTRA',transcript_id:'REPORT-EXTRA-TX',consequence:'synonymous_variant'}]
    snapshot.variant_records=[{variant:{assembly:'GRCh38',sequence_id:'NC_000001.11',position:104,ref:'T',alt:'G',reference_context:{start:100,sequence:'GACGTACG'}},annotations:[{gene_id:'G-SECOND',transcript_id:'REPORT-SECOND-TX',consequence:'intron_variant'}]}]
  }
  const response=await page.request.post('/api/investigations',{data:input});expect(response.status()).toBe(200)
  const saved=await response.json();expect(saved.differences).toEqual([])
  await page.goto(`/#/comparison/${saved.id}/overview`)
  await expect(page.getByRole('heading',{name:'Review all represented variants'})).toBeVisible()
  const download=page.waitForEvent('download')
  await page.getByRole('button',{name:'Readable report',exact:true}).click()
  await page.getByRole('button',{name:'Download readable HTML'}).click()
  const html=await readFile((await(await download).path())!,'utf8')
  expect(html).toContain('REPORT-EXTRA-TX');expect(html).toContain('REPORT-SECOND-TX')
  expect(saved.input.snapshots[0].annotations[0].transcript_id).toBe('REPORT-EXTRA-TX')
})

test('a legal long filename is accepted without changing its original metadata',async({page})=>{
  const header='assembly,sequence_id,position,ref,alt,gene_id,transcript_id,consequence,tool,tool_version,source_name,source_release\n'
  const raw=header+'GRCh38,NC_000001.11,102,C,T,G,T,intron_variant,Tool,1,Source,1\n'
  await page.goto('/#/input');await page.getByText('Import two annotated CSV/TSV files',{exact:true}).click()
  for(const [i,name] of ['x'.repeat(147)+'.csv','B.csv'].entries())await page.getByLabel(`Analysis ${i+1} tabular file`).setInputFiles({name,mimeType:'text/csv',buffer:Buffer.from(raw)})
  const response=page.waitForResponse(r=>r.url().endsWith('/api/imports/tabular/preview'))
  await page.getByRole('button',{name:'Preview imported rows'}).click()
  const preview=await response;expect(preview.status()).toBe(200)
  expect((await preview.json()).input.snapshots[0].provenance.configuration.import_filename).toBe('x'.repeat(147)+'.csv')
  await expect(page.getByRole('heading',{name:'Import preview — no comparison saved yet'})).toBeVisible()
})

test('adding an imported transcript is explained as a row addition without a selected-transcript claim',async({page})=>{
  const header='assembly,sequence_id,position,ref,alt,gene_id,transcript_id,consequence,tool,tool_version,source_name,source_release,context_start,reference_sequence\n'
  const row=(id:string,effect:string)=>`GRCh38,NC_000001.11,102,C,T,G,${id},${effect},Tool,1,Source,1,100,GACGTACG\n`
  await page.goto('/#/input');await page.getByText('Import two annotated CSV/TSV files',{exact:true}).click()
  for(const [i,raw] of [header+row('T2','intron_variant'),header+row('T2','intron_variant')+row('T1','missense_variant')].entries()){
    await page.getByLabel(`Analysis ${i+1} tabular file`).setInputFiles({name:`${i}.csv`,mimeType:'text/csv',buffer:Buffer.from(raw)})
  }
  await page.getByRole('button',{name:'Preview imported rows'}).click()
  await page.getByRole('button',{name:'Review these two analyses'}).click()
  const response=page.waitForResponse(r=>r.url().endsWith('/api/investigations')&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Compare analyses',exact:true}).click()
  const result=await(await response).json()
  expect(result.findings.some((f:any)=>f.cause==='transcript selection')).toBe(false)
  await expect(page.locator('.comparison-story')).toContainText('1 added and 0 removed')
  await expect(page.locator('.outcome-pair')).toContainText('All supplied rows are compared.')
  await expect(page.getByRole('heading',{name:'Review all represented variants'})).toBeVisible()
  await expect(page.locator('.findings-readable .finding h3').filter({hasText:'transcript selection'})).toHaveCount(0)
})

test('a user can favorite their open editor and save notes without overwriting other flags',async({page})=>{
  const saved=await create(page,'Audit own favorite '+Date.now()),url=`/api/workspace/library/${saved.id}/label`
  await page.goto('/#/library');await page.getByLabel('Search investigations').fill(saved.id)
  await page.locator('.library-row').filter({hasText:saved.id}).getByRole('button',{name:'Edit details'}).click()
  await page.getByRole('textbox',{name:'Notes',exact:true}).fill('Keep my review')
  await page.getByRole('button',{name:'Favorite',exact:true}).click()
  await expect(page.getByRole('button',{name:'Unfavorite',exact:true})).toBeVisible()
  const response=page.waitForResponse(r=>r.url().endsWith(url)&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Save library details'}).click()
  expect((await response).status()).toBe(200)
  const label=await(await page.request.get(url)).json()
  expect(label.favorite).toBe(true);expect(label.notes).toBe('Keep my review')
})

test.describe('local date filtering',()=>{
  test.use({timezoneId:'America/Chicago'})
  test('local midnight boundaries include the correct records across the daylight saving change',async({page})=>{
    const title='Date boundaries '+Date.now(),rows=[]
    for(const [i,timestamp] of ['2026-10-28T02:00:00Z','2026-10-28T05:00:00Z','2026-11-02T05:30:00Z','2026-11-02T06:00:00Z'].entries()){
      const saved=await create(page,title+' '+i);rows.push([saved.id,timestamp])
    }
    const info=await(await page.request.get('/api/workspace/data')).json()
    expect(path.basename(info.database_path)).toMatch(/^genomedebugger-e2e-\d+-(?:chromium|webkit|firefox)\.db$/)
    const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
    execFileSync(python,['-c',"import sqlite3,json,sys; db=sqlite3.connect(sys.argv[1]); db.executemany('UPDATE investigations SET created_at=? WHERE id=?',[(stamp,id_) for id_,stamp in json.loads(sys.argv[2])]); db.commit(); db.close()",info.database_path,JSON.stringify(rows)])
    await page.goto('/#/library');await page.getByLabel('Search investigations').fill(title)
    await page.getByText('More filters',{exact:true}).click()
    const filter=page.getByLabel('Saved on or after (your local date)',{exact:true})
    let response=page.waitForResponse(r=>r.url().includes('/api/workspace/library?')&&r.url().includes('since_instant='))
    await filter.fill('2026-10-28')
    const first=await response
    expect(new URL(first.url()).searchParams.get('since_instant')).toBe('2026-10-28T05:00:00.000Z')
    await expect(page.locator('.library-row')).toHaveCount(3)
    response=page.waitForResponse(r=>r.url().includes('/api/workspace/library?')&&new URL(r.url()).searchParams.get('since')==='2026-11-02')
    await filter.fill('2026-11-02')
    expect(new URL((await response).url()).searchParams.get('since_instant')).toBe('2026-11-02T06:00:00.000Z')
    await expect(page.locator('.library-row')).toHaveCount(1)
    await expect(page.locator('.library-row')).toContainText(rows[3][0])
  })
})
