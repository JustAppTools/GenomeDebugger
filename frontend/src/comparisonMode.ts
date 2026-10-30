import type {InvestigationInput} from './types'

export function isCollectionInput(input:InvestigationInput) {
  return input.snapshots.some(({provenance})=>
    provenance.configuration?.import_format==='genomedebugger-tabular-v1'&&
    provenance.configuration?.row_order_policy==='canonical-variant-and-annotation-keys-v1')
}
