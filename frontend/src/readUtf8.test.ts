import {expect,test} from 'vitest'
import {readUtf8} from './readUtf8'

function file(bytes:number[]) {return {arrayBuffer:async()=>new Uint8Array(bytes).buffer} as File}

test('decodes UTF-8, rejects distinct malformed sequences, and handles BOM explicitly',async()=>{
  expect(await readUtf8(file([0x41,0xc3,0xa9]))).toBe('Aé')
  for(const byte of [0xe9,0xf1])await expect(readUtf8(file([0x22,byte,0x22]))).rejects.toThrow('valid UTF-8')
  expect(await readUtf8(file([0xef,0xbb,0xbf,0x41]))).toBe('A')
  expect(await readUtf8(file([0xef,0xbb,0xbf,0x41]),true)).toBe('\ufeffA')
})
