import {useEffect} from 'react';
export const APP_NAME='AI Football';
// The browser tab, history and shared links name the page itself, not the whole site.
export function useDocumentTitle(title?:string|null){useEffect(()=>{document.title=title?`${title} — ${APP_NAME}`:APP_NAME},[title])}
