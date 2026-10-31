import {openWorkspaceInputs} from './workspace-helpers'
import {prepareGuided} from './workspace-helpers'
import {test,expect,type Page} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import path from 'node:path'

async function openSaved(page:Page,result:any) {
  await page.goto('/')
  await page.getByRole('link',{name:'Saved work',exact:true}).click()
  await page.getByLabel('Search investigations').fill(result.id)
  await page.locator('.library-row').filter({hasText:result.id}).getByRole('button',{name:'Open',exact:true}).click()
  await page.getByRole('heading',{name:'Compared analyses',exact:true}).waitFor()
}

for(const [field,length] of [['label',150],['id',100],['source_name',100]] as const) {
  test(`full ${field} values stay readable in phone and desktop analysis cards`,async({page},testInfo)=>{
    const input=await(await page.request.get('/api/demos/transcript-switch')).json()
    input.title=`0.7.10 layout ${field} ${Date.now()}`
    const text='W'.repeat(length)
    if(field==='source_name')input.snapshots[0].provenance[field]=text
    else input.snapshots[0][field]=text
    const response=await page.request.post('/api/investigations',{data:input})
    expect(response.ok()).toBe(true)
    await openSaved(page,await response.json())
    await page.getByText('Show technical details',{exact:true}).click()
    const card=page.locator('.snapshot-card').first()
    await expect(card).toContainText(text)
    for(const width of [375,320,1280]) {
      await page.setViewportSize({width,height:900})
      await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
      const value=card.getByText(text,{exact:field!=='source_name'})
      await expect(value).toBeVisible()
      const box=await value.boundingBox()
      expect(box!.x).toBeGreaterThanOrEqual(0)
      expect(box!.x+box!.width).toBeLessThanOrEqual(width)
      if(width===375&&field==='label')await card.screenshot({path:testInfo.outputPath('analysis-card-phone.png')})
    }
  })
}

test('missing and empty protein values remain distinct without changing saved comparison data',async({page})=>{
  const input=await(await page.request.get('/api/demos/transcript-switch')).json()
  input.title=`0.7.10 protein display ${Date.now()}`
  input.controlled_lookup=null
  input.snapshots[1]=structuredClone(input.snapshots[0]);input.snapshots[1].id='B'
  input.snapshots[0].annotation.protein_consequence=null
  input.snapshots[1].annotation.protein_consequence=''
  const response=await page.request.post('/api/investigations',{data:input})
  expect(response.ok()).toBe(true)
  const result=await response.json()
  expect(result.differences).toHaveLength(1)
  expect(result.differences[0]).toMatchObject({field:'protein_consequence',before:null,after:'',meaningful:true})
  await openSaved(page,result)
  await page.getByRole('button',{name:'See the changes',exact:true}).click()
  const row=page.locator('tr').filter({has:page.locator('td.field-name').filter({hasText:'Predicted protein change'})})
  await expect(row.locator('td').nth(1)).toHaveText('Not provided')
  await expect(row.locator('td').nth(2)).toHaveText('Empty text')
  const saved=await(await page.request.get('/api/investigations/'+result.id)).json()
  expect(saved).toEqual(result)
})

for(const invalid of ['boolean coordinate','blank required title']) {
  test(`JSON entry explains ${invalid} and preserves the rejected draft`,async({page})=>{
    const input=await(await page.request.get('/api/demos/transcript-switch')).json()
    input.title=`0.7.10 invalid entry ${Date.now()}`
    if(invalid==='boolean coordinate')input.snapshots[0].variant.position=true
    else input.title=' \t\u00a0'
    const text=JSON.stringify(input,null,2)
    await page.goto('/')
    await openWorkspaceInputs(page)
    await prepareGuided(page)
    await page.getByRole('button',{name:'JSON editor',exact:true}).click()
    await page.getByLabel('Investigation JSON').fill(text)
    const finished=page.waitForResponse(r=>r.url().endsWith('/api/investigations')&&r.request().method()==='POST')
    await page.getByRole('button',{name:'Compare',exact:true}).click()
    expect((await finished).status()).toBe(422)
    await expect(page.getByRole('alert')).toContainText(invalid==='boolean coordinate'?'valid integer':'non-whitespace text')
    await expect(page.getByLabel('Investigation JSON')).toHaveValue(text)
    await expect(page.getByRole('heading',{name:'Compared analyses',exact:true})).toHaveCount(0)
  })
}

test('JSON edits cannot present an old source agreement as a check of changed consequences',async({page})=>{
  const python=path.resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
  const bundle=JSON.parse(execFileSync(python,['e2e/reference-bundle.py'],{encoding:'utf8'}))
  expect((await page.request.post('/api/bundles/import',{data:bundle})).ok()).toBe(true)
  const source=bundle.entries.source_record,q=source.query
  const ann=source.transcripts.map((row:any)=>`${q.alt}|${row.consequence_terms.join('&')}|MODIFIER|G|${row.gene_id}|transcript|${row.transcript_id}`).join(',')
  const checked=await page.request.post(`/api/sources/ensembl/records/${source.id}/snpeff-check`,{data:{
    vcf_text:`${q.chromosome}\t${q.position}\t.\t${q.ref}\t${q.alt}\t.\tPASS\tANN=${ann}`,
    snpeff_version:'scope',genome_database:'scope',database_sha256:'a'.repeat(64)}})
  expect(checked.ok()).toBe(true)
  const result=await page.request.post(`/api/sources/ensembl/records/${source.id}/compare`,{data:{
    transcript_a:source.transcripts[0].transcript_id,transcript_b:source.transcripts[1].transcript_id,
    reference_check_id:null,annotation_check_id:(await checked.json()).id}})
  expect(result.ok()).toBe(true)
  const original=await result.json(),input=structuredClone(original.input)
  for(const snapshot of input.snapshots){snapshot.provenance.tool='Custom transformed output';snapshot.annotation.consequence='stop_gained'}
  await openSaved(page,original)
  await openWorkspaceInputs(page)
  await prepareGuided(page)
  await page.getByRole('button',{name:'JSON editor',exact:true}).click()
  await page.getByLabel('Investigation JSON').fill(JSON.stringify(input))
  const rejected=page.waitForResponse(r=>r.url().endsWith('/api/investigations')&&r.request().method()==='POST')
  await page.getByRole('button',{name:'Compare',exact:true}).click()
  expect((await rejected).status()).toBe(422)
  await expect(page.getByRole('alert')).toContainText('does not apply to the edited annotations')
  await expect(page.getByRole('alert')).toContainText('remove the annotation check')
  expect(await(await page.request.get('/api/investigations/'+original.id)).json()).toEqual(original)
})
