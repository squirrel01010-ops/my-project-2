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
  await page.locator('#chat-health-refresh').waitFor();
  await page.locator('[data-page="activity"]').click();await page.getByRole('heading',{name:'나의 코인 기록'}).waitFor();
  await page.setViewportSize({width:390,height:844});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Activity mobile overflow');
  await page.screenshot({path:'/workspace/stellar/preview-activity-mobile.png',fullPage:true});
  await page.locator('[data-page="history"]').click();await page.locator('#history-filter button').click();await page.locator('#history-next').waitFor();
  await page.locator('[data-page="social"]').click();
  let light=false,full=false;page.on('request',r=>{if(r.url().includes('/api/social?'))light=true;if(r.url().endsWith('/api/state'))full=true});
  await page.waitForTimeout(4000);if(!light||full)throw Error('Social polling did not use light endpoint');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Health, personal activity, history and lightweight polling UI checks passed');
 }finally{if(browser)await browser.close();server.kill();fs.rmSync(tmp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
