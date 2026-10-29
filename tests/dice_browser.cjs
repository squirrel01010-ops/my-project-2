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
  await page.evaluate(()=>startGame('dice'));
  const mode=page.locator('#play-form [name="dice-mode"]');
  if(await page.locator('#play-form [name="choice"] option').count()!==6)throw Error('Missing six numbers');
  await mode.selectOption('parity');
  if(await page.locator('#play-form [name="choice"] option').count()!==2)throw Error('Missing parity options');
  await page.locator('#play-form [name="choice"]').selectOption('even');
  await mode.selectOption('number');
  await page.locator('#play-form [name="choice"]').selectOption('6');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Dice number/parity selector checks passed');
 }finally{if(browser)await browser.close();server.kill();fs.rmSync(tmp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});
