import { expect, test } from 'vitest'
import { blankInput, isGuidedInput, validateGuidedInput } from './GuidedInput'

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
