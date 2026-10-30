export type Tab='overview'|'differences'|'evidence'|'regression'|'input'|'source'|'library'|'help'|'data'
const tabs:Tab[]=['overview','differences','evidence','regression','input','source','library','help','data']
export function readRoute(hash=window.location.hash):{tab:Tab;id:string|null} {
  const parts=hash.replace(/^#\/?/,'').split('/')
  if(parts[0]==='comparison'&&/^[a-zA-Z0-9_-]{1,100}$/.test(parts[1]??''))return {id:parts[1],tab:tabs.includes(parts[2] as Tab)?parts[2] as Tab:'overview'}
  return {id:null,tab:tabs.includes(parts[0] as Tab)?parts[0] as Tab:'overview'}
}
export function writeRoute(tab:Tab,id?:string|null) {
  const hash=id&&!['source','library','help','data'].includes(tab)?`#/comparison/${id}/${tab}`:`#/${tab}`
  if(window.location.hash!==hash)window.history.pushState(null,'',hash)
}
