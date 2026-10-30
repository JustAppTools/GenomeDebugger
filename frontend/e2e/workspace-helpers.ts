import type {Page} from '@playwright/test'

// Regression scenarios explicitly opt into the expert controls they exercise.
// These fixture values are test inputs, not application defaults.
export async function prepareGuided(page:Page) {
  const all=page.getByRole('button',{name:'Show all fields (experienced users)',exact:true})
  if(await all.isVisible())await all.click()
  for(const summary of await page.getByText('Optional reference context',{exact:true}).all()){
    if(await summary.locator('..').getAttribute('open')===null)await summary.click()
  }
  for(const side of [1,2]){
    for(const [field,value] of Object.entries({assembly:'GRCh38','sequence accession':'NC_000001.11',position:'1',reference:'A',alternate:'T'})){
      const input=page.getByLabel(`Analysis ${side} ${field}`,{exact:true})
      if(await input.isVisible()&&!(await input.inputValue()))await input.fill(value)
    }
  }
}
export async function openSourceTools(page:Page,part:'history'|'snpeff'|'ncbi'|'transcripts') {
  const names={history:'Import original VEP output or compare preserved sources (advanced)',snpeff:'Advanced annotation output: SnpEff',ncbi:'Optional NCBI reference and notation check',transcripts:'Browse all reported transcripts and exact terms'}
  const summary=page.getByText(names[part],{exact:true})
  await summary.waitFor({state:'visible'})
  if(await summary.locator('..').getAttribute('open')===null)await summary.click()
}
export async function prepareExample(page:Page){
  const summary=page.getByText('Try another teaching case',{exact:true})
  if(await summary.isVisible()&&await summary.locator('..').getAttribute('open')===null)await summary.click()
}
