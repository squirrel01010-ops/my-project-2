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
  await page.locator('[data-page="members"]').click();await page.locator('#adjust-form [name=id]').fill('123456789');await page.locator('#adjust-form [name=name]').fill('테스트 멤버');await page.locator('#adjust-form [name=amount]').fill('10000');await page.locator('#adjust-form [name=reason]').fill('브라우저 검증');await page.locator('#adjust-form button').click();await page.getByText('10,000',{exact:true}).waitFor();
  let retryCalls=0;const retryKeys=[];
  await page.route('**/api/adjust',async route=>{const body=route.request().postDataJSON();if(body.id!=='retry-check')return route.continue();retryKeys.push(body.key);const response=await route.fetch();retryCalls++;if(retryCalls===1)return route.fulfill({status:502,contentType:'application/json',body:JSON.stringify({error:'retry test'})});return route.fulfill({response})});
  const retryResult=await page.evaluate(async()=>{const body={id:'retry-check',amount:7,reason:'retry test'};try{await api('adjust',body)}catch{}await api('adjust',body);const state=await api('state');return state.users.find(u=>u.id==='retry-check').xp});
  if(retryResult!==7||retryKeys[0]!==retryKeys[1])throw Error('Ambiguous server error paid twice');
  await page.unroute('**/api/adjust');
  await page.locator('[data-page="casino"]').click();await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/workspace/stellar/preview-games.png',fullPage:true,animations:'disabled'});await page.locator('#game-search').fill('슬롯');if(await page.locator('[data-game]:visible').count()!==1)throw Error('Game search failed');await page.locator('#game-search').fill('');if(await page.locator('[data-game]').count()!==15)throw Error('Missing games');await page.locator('[data-game="mines"]').click();await page.locator('#play-form [name=id]').fill('123456789');await page.locator('#play-form button').click();await page.locator('#modal-body [data-action=pick]').first().waitFor();
  const publicState=await page.evaluate(async token=>await(await fetch('/api/state',{headers:{Authorization:'Bearer '+token}})).json(),token);if('hazards' in publicState.rounds[0].state)throw Error('Hidden hazards exposed');
  await page.locator('#close-modal').click();await page.locator('[data-page="shop"]').click();await page.locator('#add-product').click();await page.locator('#product-form [name=name]').fill('테스트 역할');await page.locator('#product-form [name=role_id]').fill('987654321');await page.locator('#product-form button').click();await page.locator('#modal').waitFor({state:'hidden'});await page.getByRole('heading',{name:'테스트 역할'}).waitFor();
  await page.locator('[data-page="settings"]').click();await page.locator('[name=chatXP]').fill('35');await page.locator('#add-reward').click();await page.locator('[data-reward] [data-k=role]').fill('987654321');await page.locator('#settings-form > .settings-sticky button').click();await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('저장'));
  await page.locator('[data-page="seasons"]').click();await page.locator('#end-season').click();await page.locator('#end-form [name=confirm]').fill('시즌 종료');await page.locator('#end-form button').click();await page.locator('#modal').waitFor({state:'hidden'});
  await page.locator('[data-page="logs"]').click();await page.getByRole('heading',{name:'관리자 변경 이력'}).waitFor();
  const python=(code)=>{const r=spawnSync(path.resolve('.venv/bin/python'),['-c',code],{env:{...process.env,DB_PATH:path.join(tmp,'test.db')},encoding:'utf8'});if(r.status!==0)throw Error(r.stderr);return r.stdout};
  await page.request.post('http://127.0.0.1:8092/api/adjust',{headers:{Authorization:'Bearer '+token},data:{id:'local-admin',amount:10000,key:'social-fund'}});
  await page.locator('[data-page="social"]').click();await page.locator('#holdem-create button').click();await page.locator('[data-holdem=start]').waitFor();
  python("import core;core.operate('222','adjust',dict(id='222',name='두 번째 멤버',amount=10000,key='fund'),True);s=core.state('222')['social']['holdem'][0];core.operate('222','holdem/join',dict(table=s['id'],key='join'))");
  await page.locator('[data-holdem=start]').click();await page.waitForFunction(()=>document.querySelector('#holdem-tables').textContent.includes('차례'));
  const pokerState=await page.evaluate(()=>data.social.holdem[0]);if(pokerState.players.find(p=>p.uid==='222').cards.join('')!=='🂠🂠')throw Error('Opponent cards leaked');
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/workspace/stellar/preview-holdem.png',fullPage:true,animations:'disabled'});
  python("import core;s=core.state()['social']['holdem'][0];uid=s['players'][s['turn']]['uid'];core.operate(uid,'holdem/action',dict(table=s['id'],revision=s['revision'],action='fold',key='finish'))");
  await page.locator('[data-social-tab=lottery]').click();await page.locator('#lottery-buy [name=numbers]').fill('1, 7, 20');await page.locator('#lottery-buy button').click();await page.getByText('1 · 7 · 20',{exact:true}).waitFor();
  await page.locator('[data-social-tab=crash]').click();await page.locator('#crash-join button').click();await page.getByText('🚀 출발 대기',{exact:true}).waitFor();
  python("import core,social,time;\nwith core.db(True) as c:\n r=c.execute(\"SELECT state FROM live_games WHERE kind='crash' ORDER BY created DESC LIMIT 1\").fetchone();import json;s=json.loads(r[0]);s['starts']=time.time()-8;s['crash']=500;social.save(c,s)");
  await page.waitForFunction(()=>document.querySelector('#crash-rounds').textContent.includes('200 띵조코인'));
  await page.locator('#social-config summary').click();await page.locator('#social-settings [name=lotteryPrice]').fill('125');await page.locator('#social-settings button').click();await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('저장'));
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/workspace/stellar/preview-social-mobile.png',fullPage:true,animations:'disabled'});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Social mobile overflow');await page.setViewportSize({width:1440,height:1000});
  await page.locator('[data-page="overview"]').click();await page.locator('#sync-commands').click();await page.waitForFunction(()=>document.querySelector('#sync-commands').disabled);await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/workspace/stellar/preview-desktop.png',fullPage:true,animations:'disabled'});
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/workspace/stellar/preview-mobile.png',fullPage:true,animations:'disabled'});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile horizontal overflow');
  await page.locator('[data-page=casino]').click();await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/workspace/stellar/preview-games-mobile.png',fullPage:true,animations:'disabled'});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Games mobile overflow');
  await page.locator('[data-page=settings]').click();await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'/workspace/stellar/preview-settings-mobile.png',fullPage:true,animations:'disabled'});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Settings mobile overflow');
  if(errors.length)throw Error(errors.join('\n'));
  console.log('Browser flow passed: login, XP adjustment, 15 games, persistent game, shop, settings, season, logs, multiplayer holdem/lottery/crash, desktop/mobile.');
 }finally{if(browser)await browser.close();server.kill();fs.rmSync(tmp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});

