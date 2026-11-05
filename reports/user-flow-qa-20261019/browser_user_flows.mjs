import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
const root=process.cwd(), out=path.join(root,'reports/userflow');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const summary={modes:{},exceptions:[],networkFailures:[],snapshots:[]};
const chrome=spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',['--headless=new','--remote-debugging-port=9447','--no-first-run','--no-default-browser-check','--window-size=1440,900','--user-data-dir='+path.join(out,'browser-profile'),'about:blank'],{windowsHide:true,stdio:'ignore'});
let browser,app,seq=0; const pending=new Map();
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;const timer=setTimeout(()=>{pending.delete(id);reject(Error(method+' timeout'));},15000);pending.set(id,{resolve,reject,timer});browser.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result?.value;}
function records(){try{return fs.readFileSync(path.join(out,'ui-flow.jsonl'),'utf8').trim().split('\n').filter(Boolean).map(s=>JSON.parse(s));}catch{return [];}}
try{
 let pages;for(let i=0;i<60;i++){try{pages=await(await fetch('http://127.0.0.1:9447/json/list')).json();if(pages.some(p=>p.type==='page'))break;}catch{}await sleep(200);}
 const page=pages.find(p=>p.type==='page');browser=new WebSocket(page.webSocketDebuggerUrl);await new Promise((r,j)=>{browser.onopen=r;browser.onerror=j;});
 browser.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);}
 if(m.method==='Runtime.exceptionThrown')summary.exceptions.push(m.params.exceptionDetails);
 if(m.method==='Network.loadingFailed')summary.networkFailures.push(m.params.errorText);
 if(m.method==='Network.webSocketFrameReceived'){try{const packet=JSON.parse(m.params.response.payloadData);const log=records();const mode=log.at(-1)?.mode||'STARTUP';const stats=summary.modes[mode]??={robotPackets:0,worldPackets:0,jointPoses:[],grippers:[],capturedObserved:false,attachedObserved:false};
 if(packet.type==='robot_state'){stats.robotPackets++;const joints=packet.joints?.map(v=>Math.round(v*10)/10);if(joints&&stats.jointPoses.length<100&&!stats.jointPoses.some(a=>JSON.stringify(a)===JSON.stringify(joints)))stats.jointPoses.push(joints);if(!stats.grippers.includes(packet.gripper))stats.grippers.push(packet.gripper);}
 if(packet.type==='world_state'){stats.worldPackets++;stats.capturedObserved ||= packet.pieces?.some(p=>p.captured);stats.attachedObserved ||= packet.pieces?.some(p=>p.attached);}
 }catch{}}
 };
 await send('Runtime.enable');await send('Page.enable');await send('Network.enable');
 await send('Page.navigate',{url:'http://127.0.0.1:8099/robot-3d-viewer/?ws=ws%3A%2F%2F127.0.0.1%3A8775&autoconnect=1'});
 const readyAt=Date.now();while(Date.now()-readyAt<45000){if(await evaluate('Boolean(window.__state && document.querySelector("#wsUrl")?.value.endsWith(":8775"))'))break;await sleep(250);}
 const stdout=fs.openSync(path.join(out,'ui-driver-final.log'),'w');
 app=spawn(path.join(root,'.venv312/Scripts/python.exe'),['reports/userflow/run_ui_flows.py'],{cwd:root,windowsHide:true,stdio:['ignore',stdout,stdout],env:{...process.env,OMP_NUM_THREADS:'1',OPENBLAS_NUM_THREADS:'1',MKL_NUM_THREADS:'1'}});
 const start=Date.now();let lastConnectionAttempt=0;const saved=new Set();
 while(Date.now()-start<480000){const log=records(),last=log.at(-1),mode=last?.mode;const latest=log.findLast(x=>x.kind==='stable_commit');
 const ui=await evaluate('({ws:window.__state?.liveSocket?.readyState,joints:window.__state?.jointsDeg,source:window.__state?.liveSource,canvas:document.querySelector("#scene")?.width,sceneChildren:window.__scene?.children.length,text:document.body.innerText.slice(0,300)})');
 if(mode&&ui.ws!==1&&Date.now()-lastConnectionAttempt>1200){await evaluate('document.querySelector("#liveBtn")?.click()');lastConnectionAttempt=Date.now();}
 if(mode&&ui.ws===1&&ui.sceneChildren>3&&latest?.mode===mode){const n=latest.plies;const label=n>=10?'ten-plies':n>=2?'moving':'initial';const key=mode+'-'+label;if(!saved.has(key)){
 const shot=await send('Page.captureScreenshot',{format:'png'});const name='browser-'+key+'.png';fs.writeFileSync(path.join(out,name),Buffer.from(shot.data,'base64'));summary.snapshots.push({mode,label,plies:n,file:name,ui});saved.add(key);}}
 if(last?.kind==='driver_exit'){summary.driverComplete=last.complete;break;}
 if(app.exitCode!==null){summary.driverExit=app.exitCode;break;}
 await sleep(250);
 }
 summary.driverComplete ||= records().some(x=>x.kind==='complete');
 summary.finishedAt=new Date().toISOString();
 fs.writeFileSync(path.join(out,'browser-evidence.json'),JSON.stringify(summary,null,2));
 console.log(JSON.stringify({complete:summary.driverComplete,exceptions:summary.exceptions.length,modes:Object.fromEntries(Object.entries(summary.modes).map(([k,v])=>[k,{packets:v.robotPackets,world:v.worldPackets,poses:v.jointPoses.length,grippers:v.grippers,attached:v.attachedObserved,captured:v.capturedObserved}])),screenshots:summary.snapshots.length}));
 if(!summary.driverComplete||summary.exceptions.length)process.exitCode=1;
}finally{if(browser?.readyState===1){try{await send('Browser.close');}catch{}}if(app&&app.exitCode===null)app.kill();chrome.kill();}
