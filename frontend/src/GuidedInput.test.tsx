import { expect, test } from 'vitest'
import { blankInput, isGuidedInput, normalizeGuidedInput, validateGuidedInput } from './GuidedInput'

test.each([123, {}, [], true])('reports an invalid imported reference sequence without throwing: %j', sequence=>{
  const input = blankInput() as unknown as {snapshots:{variant:{reference_context?:unknown}}[]}
  input.snapshots[0].variant.reference_context = {start:1,sequence}
  expect(()=>validateGuidedInput(input)).not.toThrow()
  expect(isGuidedInput(input)).toBe(false)
  expect(validateGuidedInput(input).some(error=>error.includes('sequence must be text'))).toBe(true)
})

test('checks additional variant types before opening guided mode',()=>{
  const input = {...blankInput(),snapshots:[...blankInput().snapshots]}
  const malformed = {...input,snapshots:input.snapshots.map(snapshot=>({...snapshot,variant_records:[null]}))}
  expect(isGuidedInput(malformed)).toBe(false)
  expect(()=>validateGuidedInput(malformed)).not.toThrow()
})

test('applies the optional synthetic default without changing the imported object',()=>{
  const value:Record<string,unknown>={...blankInput()};delete value.synthetic
  expect(isGuidedInput(normalizeGuidedInput(value))).toBe(true)
  expect(validateGuidedInput(value).some(error=>error.includes('synthetic'))).toBe(false)
  expect(value).not.toHaveProperty('synthetic')
})

test.each([null,'false',0])('preserves an invalid explicit synthetic value: %j',synthetic=>{
  const value={...blankInput(),synthetic}
  expect(isGuidedInput(normalizeGuidedInput(value))).toBe(false)
  expect(validateGuidedInput(value).some(error=>error.includes('synthetic'))).toBe(true)
})

test('uses API-compatible Unicode lengths for titles and annotation identifiers',()=>{
  const input=blankInput()
  input.title='🧬'.repeat(200)
  input.snapshots[0].annotation.gene_id='🧬'.repeat(100)
  let errors=validateGuidedInput(input)
  expect(errors.some(error=>error.includes('Title exceeds'))).toBe(false)
  expect(errors.some(error=>error.includes('gene ID exceeds'))).toBe(false)
  input.title+='🧬';input.snapshots[0].annotation.gene_id+='🧬'
  errors=validateGuidedInput(input)
  expect(errors).toContain('Title exceeds 200 characters')
  expect(errors).toContain('Analysis 1: gene ID exceeds 100 characters')
})
