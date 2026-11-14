export const TIMINGS=[30,30,85,45,60,40];
export function demoURL(input,base){const url=new URL(input||'../',base);if(url.username||url.password)throw Error('Do not include credentials in the demo URL.');if(url.protocol!=='https:'&&!(url.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(url.hostname)))throw Error('Use HTTPS, or HTTP on localhost.');url.searchParams.set('presentation','1');return url;}
export function formatTime(seconds){return `${Math.floor(Math.abs(seconds)/60)}:${String(Math.floor(Math.abs(seconds)%60)).padStart(2,'0')}`;}
export function allowedBridge(event,origin,parent){return event.source===parent&&event.origin===origin&&event.data?.type==='PHAROS_PRESENTATION'&&['ping','reset','closure','draft'].includes(event.data.command);}
