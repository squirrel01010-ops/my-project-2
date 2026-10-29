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
  await page.locator('[data-page="settings"]').click();
  await page.locator('[name="slots-pair"]').fill('0.75');
  for(let i=0;i<5;i++)await page.locator(`[name="slots-triple-${i}"]`).fill(String(i+3));
  await page.locator('[data-odds=slots] summary').click();await page.locator('[name=odds-enabled-slots]').check();await page.locator('[name=odds-slots-0]').fill('2');await page.locator('#settings-form > .settings-sticky button').click();
  await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('저장'));
  const state=await page.evaluate(()=>data.settings.games.slots);
  if(await page.evaluate(()=>data.settings.probabilities.slots[0])!==2)throw Error('Weights not saved');
  if(state.pairMultiplier!==0.75||JSON.stringify(state.tripleMultipliers)!=='[3,4,5,6,7]')throw Error('Slot settings not saved');
  await page.reload();await page.locator('#local-login summary').click();await page.locator('#token').fill(token);await page.locator('#login-form button').click();await page.locator('#login').waitFor({state:'hidden'});await page.locator('[data-page="settings"]').click();
  if(await page.locator('[name="slots-pair"]').inputValue()!=='0.75')throw Error('Reload lost settings');
  await page.setViewportSize({width:390,height:844});
  await page.locator('[name="slots-pair"]').scrollIntoViewIfNeeded();
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile overflow');
  await page.screenshot({path:'/workspace/stellar/preview-slots-mobile.png'});
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Slot settings save, reload and mobile checks passed');
 }finally{if(browser)await browser.close();server.kill();fs.rmSync(tmp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
