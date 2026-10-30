import {useCallback,useEffect,useRef,useState,type SetStateAction} from 'react'

// Per-App memory only: no implicit storage of scientific drafts in the browser.
export function useRetainedState<T>(store:Map<string,unknown>|undefined,key:string,initial:T) {
  const [value,setValue]=useState<T>(()=>store?.has(key)?store.get(key) as T:initial)
  const latest=useRef(value),live=useRef(true)
  useEffect(()=>{live.current=true;return()=>{live.current=false}},[])
  const update=useCallback((next:SetStateAction<T>)=>{
    if(!live.current)return
    const resolved=typeof next==='function'?(next as (previous:T)=>T)(latest.current):next
    latest.current=resolved;store?.set(key,resolved);setValue(resolved)
  },[store,key])
  return [value,update] as const
}
