import {useEffect,useState,type ReactNode} from 'react'
export default function OperationStatus({active,label,children}:{active:boolean;label:string;children?:ReactNode}){
  const [seconds,setSeconds]=useState(0)
  useEffect(()=>{setSeconds(0);if(!active)return;const began=Date.now(),timer=window.setInterval(()=>setSeconds(Math.floor((Date.now()-began)/1000)),1000);return()=>window.clearInterval(timer)},[active,label])
  if(!active)return null
  return <div className="operation-progress" role="status"><span>{label}…</span><span aria-hidden="true">{seconds}s elapsed</span>{children}</div>
}
