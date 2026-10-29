const {chromium}=require('playwright');
const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs');const os=require('node:os');const path=require('node:path');
(async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'stellar-browser-'));const token=require('node:crypto').randomBytes(32).toString('hex');
 const server=spawn(path.resolve('.venv/bin/python'),['app.py'],{env:{...process.env,DB_PATH:path.join(tmp,'test.db'),BACKUP_DIR:path.join(tmp,'backup'),ADMIN_TOKEN:token,PORT:'8092',PUBLIC_URL:'http://127.0.0.1:8092'},stdio:'ignore'});
 let browser;
 try{
  for(let i=0;i<50;i++){try{if((await fetch('http://127.0.0.1:8092/health')).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
  browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  const page=await browser.newPage({timezoneId:'Asia/Seoul',viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8092');await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/workspace/stellar/preview-login.png',fullPage:true,animations:'disabled'});await page.locator('#local-login summary').click();await page.locator('#token').fill(token);await page.locator('#login-form button').click();await page.locator('#login').waitFor({state:'hidden'});
  await page.setViewportSize({width:390,height:844});
  const result=await page.evaluate(async()=>{
   const r={game:'horse',state:{order:[3,1,5,2,4],done:true,message:'3번 말 우승',mult:0},status:'done',bet:100,payout:0,fee:15,uid:'local-admin'};
   const snapshots=[];const observer=new MutationObserver(()=>{const track=document.querySelector('.horse-track');if(track)snapshots.push(track.textContent)});observer.observe(document.querySelector('#modal-body'),{childList:true,subtree:true});
   await animateHorse(r);observer.disconnect();showRound(r);
   return {snapshots,final:document.querySelector('#modal-body').textContent,overflow:document.documentElement.scrollWidth>innerWidth};
  });
  if(result.overflow)throw Error('Mobile overflow');
  if(result.final.includes('수수료'))throw Error('Fee shown on loss');
  for(let horse=1;horse<=5;horse++){let last=0;for(const text of result.snapshots){const row=text.split('\n').find(x=>x.startsWith(horse+' '));const pos=row.split('🐎')[1].replace('┃','').length;if(pos<last)throw Error('Horse moved backwards');last=pos}if(last!==24)throw Error('Horse did not finish')}
  await page.screenshot({path:'/workspace/stellar/preview-horse-mobile.png'});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Mobile race: forward movement, finish and loss fee checks passed');
 }finally{if(browser)await browser.close();server.kill();fs.rmSync(tmp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
