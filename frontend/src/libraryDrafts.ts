import type {LibraryEditDraft} from './WorkspaceLibrary'

type Store=Map<string,LibraryEditDraft>
type Listener=(id:string,saved:LibraryEditDraft,details:boolean)=>void
const listeners=new WeakMap<Store,Set<Listener>>()
export function subscribeToLibrarySaves(store:Store,listener:Listener) {
  let subscriptions=listeners.get(store)
  if(!subscriptions){subscriptions=new Set();listeners.set(store,subscriptions)}
  subscriptions.add(listener)
  return ()=>{subscriptions.delete(listener)}
}
export function reconcileLibrarySave(store:Store,submitted:LibraryEditDraft,saved:LibraryEditDraft,details:boolean) {
  const current=store.get(submitted.id)
  if(details&&current===submitted)store.delete(submitted.id)
  else if(current)store.set(submitted.id,mergeLibraryRevision(current,saved,details))
  listeners.get(store)?.forEach(listener=>listener(submitted.id,saved,details))
}
export function mergeLibraryRevision(draft:LibraryEditDraft,saved:LibraryEditDraft,details:boolean) {
  return {...draft,label_revision:details?saved.label_revision??draft.label_revision:draft.label_revision,
    details_revision:details?saved.details_revision??draft.details_revision:draft.details_revision,
    favorite:saved.favorite??draft.favorite,archived:saved.archived??draft.archived}
}
