'use strict';
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),port=Number(process.env.SKILL_TEST_PORT||18765),base=`http://127.0.0.1:${port}`;
const capture=process.argv.includes('--capture'),output=process.env.SKILL_CAPTURE_DIR;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 let browser,page,ready=false,exitCode=null;const checks=[],errors=[];
 const child=spawn(process.env.PYTHON||'python',[path.join(root,'scripts/demo.py'),'--port',String(port)],{cwd:root,stdio:['ignore','pipe','pipe'],windowsHide:true});
 child.on('error',e=>{errors.push(e.message);exitCode=1});child.on('exit',code=>{exitCode=code});
 child.stdout.on('data',()=>{});child.stderr.on('data',()=>{});
 const pass=name=>checks.push(name);
 try{
   for(let i=0;i<100;i++){
     if(exitCode!==null)throw new Error('Isolated demo exited before becoming healthy.');
     try{const response=await fetch(base+'/api/health');if(response.ok){ready=true;break;}}catch{}
     await pause(100);
   }
   assert.ok(ready,'Demo did not start');
   browser=await chromium.launch(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL,headless:true}:{headless:true});
   const context=await browser.newContext({viewport:{width:1440,height:720},reducedMotion:'reduce'});page=await context.newPage();
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/my-skills.html',{waitUntil:'networkidle'});await page.waitForSelector('.cap-row');
   assert.equal(await page.locator('.cap-row').count(),3);pass('isolated demo contains exactly three original examples');
   const catalog=await page.evaluate(async()=> (await (await fetch('/api/skills?scope=all')).json()).skills);
   assert.deepEqual(catalog.map(s=>s.name).sort(),['market-research','project-readme','web-ui-review']);pass('personal skill library is absent');
   if(capture&&output){fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,'workbench.png')});}
   await page.locator('#open-task-finder').click();await page.locator('#finder-form button[type=submit]').click();assert.equal(await page.locator('#finder-goal').getAttribute('aria-invalid'),'true');pass('required goal is accessible');
   const goal='调研项目管理工具市场，比较主要产品与替代方案。';await page.locator('#finder-goal').fill(goal);await page.locator('#finder-form button[type=submit]').click();assert.equal(await page.locator('.finder-skill-name').first().innerText(),'market-research');pass('task finds matching available skill');
   if(capture&&output){await page.setViewportSize({width:1440,height:900});await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(output,'task-finder.png'),fullPage:true});}
   for(const width of [1440,390]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);pass('no overflow '+width);}
   await page.locator('[data-finder-choose="0"]').click();assert.equal(await page.locator('#task-goal').inputValue(),goal);assert.ok((await page.locator('#task-preview').inputValue()).includes(goal));pass('goal reaches editable brief');
   await page.locator('#task-materials').fill('示例：三款产品的公开资料链接');await page.locator('#task-save').click();await page.locator('#task-back').click();assert.equal(await page.locator('#finder-goal').inputValue(),goal);pass('return preserves task');
   await page.locator('#finder-goal').fill('研究开源项目管理市场');await page.locator('#finder-form button[type=submit]').click();await page.locator('[data-finder-choose="0"]').click();assert.equal(await page.locator('#task-goal').inputValue(),goal);assert.ok(await page.locator('#task-incoming').isVisible());pass('existing draft is preserved');
   await page.locator('#task-use-incoming').click();assert.equal(await page.locator('#task-goal').inputValue(),'研究开源项目管理市场');assert.ok((await page.locator('#task-materials').inputValue()).includes('三款产品'));pass('explicit adoption only replaces goal');
   await page.locator('#task-back').click();await page.locator('#finder-goal').fill('量子瞬移宠物');assert.equal(await page.locator('[data-finder-choose]').count(),0);await page.locator('#finder-form button[type=submit]').click();assert.equal(await page.locator('.finder-candidate').count(),0);pass('stale choices cleared and unknown task honest');
   await page.locator('[data-finder-back]').first().click();await page.locator('.cap-row .favorite').first().click();await page.locator('[data-scope=favorites]').click();assert.equal(await page.locator('.cap-row').count(),1);pass('favorites remain usable');
   await page.reload({waitUntil:'networkidle'});await page.waitForSelector('.cap-row');await page.locator('[data-scope=favorites]').click();assert.equal(await page.locator('.cap-row').count(),1);pass('favorites survive reload');
   for(const route of ['workflows.html','sources.html','insights.html','removed-skills.html','public-skills.html']){const response=await page.goto(base+'/'+route,{waitUntil:'networkidle'});assert.equal(response.status(),200);pass('route '+route);}
   assert.deepEqual(errors,[]);pass('no page errors');console.log(JSON.stringify({checks:checks.length,errors}));
 }finally{
   if(ready){try{if(!page)throw new Error('No browser page');await page.evaluate(async()=>{await fetch('/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})});}catch{}}
   if(browser)await browser.close();
   for(let i=0;i<50&&exitCode===null;i++)await pause(100);
   if(exitCode===null)child.kill();
 }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
