const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const {mkdtempSync,rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const {join,resolve} = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');
(async()=>{
  const socket=net.createServer(); await new Promise(r=>socket.listen(0,'127.0.0.1',r)); const port=socket.address().port; await new Promise(r=>socket.close(r));
  const data=mkdtempSync(join(tmpdir(),'wishnest-catalog-'));
  const server=spawn('python3',['server.py'],{cwd:resolve(__dirname,'..'),env:{...process.env,WISHLIST_DATA:data,PORT:String(port)},stdio:'pipe'});
  const base=`http://127.0.0.1:${port}`; let browser;
  try {
    let ready=false;for(let i=0;i<100;i++){try{if((await fetch(base+'/api/status')).ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,40));}assert(ready);
    browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
    const parent=await browser.newPage({viewport:{width:1280,height:900}});parent.setDefaultTimeout(10000);
    const errors=[];parent.on('pageerror',e=>errors.push(e.message));
    await parent.goto(base);await parent.locator('#parentTab').click();await parent.locator('#pin').fill('catalog-parent-passphrase');await parent.locator('#loginForm button.primary').click();
    await parent.locator('#consentCheck').check();await parent.locator('#consentButton').click();await parent.locator('#newProfile').click();
    await parent.locator('#profileForm input[name=nickname]').fill('Comet');await parent.locator('#childAge').fill('12');await parent.locator('#applyAgeDefaults').click();
    assert.equal(await parent.locator('#profileForm input[name=require_approval]').isChecked(),true);
    await parent.locator('#profileForm input[name=budget]').fill('100');
    await parent.locator('#advancedControls summary').click();await parent.locator('#ratingPermissions input[value=M]').check();await parent.locator('#profileForm input[name=allow_unverified_games]').check();
    await parent.locator('#profileForm button.primary').click();await parent.locator('#issuedCode').waitFor({state:'visible'});const code=await parent.locator('#issuedCode').textContent();
    const child=await browser.newPage({viewport:{width:390,height:844}});child.setDefaultTimeout(10000);child.on('pageerror',e=>errors.push(e.message));
    await child.goto(base);await child.locator('#childCode').fill(code);await child.locator('#childLogin button').click();
    await child.locator('#kidCatalog article').first().waitFor();
    assert.equal(await child.locator('#kidCatalog article').count(),10); // T game excluded; M explicitly allowed.
    await child.locator('#categoryFilter').selectOption('Video Games');await child.locator('#catalogSearch').fill('Shadow');
    assert.equal(await child.locator('#kidCatalog article').count(),1);
    assert((await child.locator('#kidCatalog').textContent()).includes('ESRB M · unverified sample rating'));
    assert((await child.locator('#kidCatalog').textContent()).includes('Outside your age suggestions'));
    const image=child.locator('#kidCatalog img');await image.scrollIntoViewIfNeeded();await image.evaluate(i=>i.decode());assert(await image.evaluate(i=>i.naturalWidth>0));
    await child.locator('#kidCatalog').getByRole('button',{name:'Add to My Wish List',exact:true}).click();
    await child.locator('#wishRequests').getByText('Shadow Quest (Demo Game) · Waiting for approval',{exact:true}).waitFor();
    assert.equal(await child.locator('#kidCards article').count(),0);
    assert((await child.locator('#budgetSummary').textContent()).includes('$0.00'));
    await parent.locator('#requestsTab').click();await parent.locator('#parentCards').getByRole('button',{name:'Approve wish',exact:true}).click();
    await parent.locator('#parentCards article').waitFor({state:'hidden'});
    await child.locator('#kidTab').click();await child.locator('#kidCards h3').waitFor();
    assert((await child.locator('#budgetSummary').textContent()).includes('$50.01 remaining'));
    assert.equal(await child.locator('#kidView a').count(),0);
    assert(await child.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await child.screenshot({path:'/tmp/wishnest-catalog-mobile.png',fullPage:true});
    // Receiving a share does not fetch a retailer or import anything before adult review.
    const shared=await browser.newPage();shared.setDefaultTimeout(10000);shared.on('pageerror',e=>errors.push(e.message));
    await shared.goto(base+'/share?url='+encodeURIComponent('https://www.target.com/p/art/-/A-123?tracking=old'));
    assert.equal(new URL(shared.url()).pathname,'/');
    await shared.locator('#parentTab').click();await shared.locator('#pin').fill('catalog-parent-passphrase');await shared.locator('#loginForm button.primary').click();
    await shared.locator('#importForm input[name=url]').waitFor({state:'visible'});
    assert((await shared.locator('#importForm input[name=url]').inputValue()).includes('target.com'));
    await shared.locator('#importForm input[name=name]').fill('Parent-reviewed art kit');await shared.locator('#importForm input[name=price]').fill('15.99');await shared.locator('#importForm button').click();
    await shared.locator('#parentCatalog h3').getByText('Parent-reviewed art kit',{exact:true}).waitFor();
    assert.deepEqual(errors,[]);
    console.log('PASS: unified sample catalog, local illustrations, category/search, parental M override at 12, pending/approved wishes, budget, gated share/manual import, mobile layout.');
  } finally {if(browser)await browser.close();server.kill();await new Promise(r=>server.once('close',r));rmSync(data,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
