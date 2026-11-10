// Reproducible checks for the unmodified DSH shell and installed MinerU panel.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const [out, executablePath, playwrightModule, phase = 'fresh'] = process.argv.slice(2);
const {chromium} = require(playwrightModule || 'playwright');

(async () => {
  const config = JSON.parse(fs.readFileSync(path.join(out, 'ready.json'), 'utf8'));
  const browser = await chromium.launch({headless: true, executablePath});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  page.setDefaultTimeout(15000);
  const errors = [], warnings = [], checks = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => {if (message.type() === 'error') errors.push(message.text()); if (message.type() === 'warning') warnings.push(message.text());});
  try {
    await page.goto(config.url);
    await page.waitForFunction(() => document.title.includes('DeepSeek Harness'));
    assert.equal(await page.title(), 'DeepSeek Harness');
    if (phase === 'removed') {
      await page.waitForFunction(() => document.body.innerText.trim().length > 30);
      await page.waitForTimeout(1500);
      assert.equal(await page.getByRole('button', {name:'MinerU', exact:true}).count(), 0);
      checks.push('original shell loads after uninstall', 'MinerU entry absent');
      await page.screenshot({path:path.join(out,'removed.png')});
    } else {
      const entry = page.getByRole('button', {name:'MinerU', exact:true});
      await entry.waitFor({timeout:30000});
      const intro = page.getByRole('button', {name:'继续', exact:true});
      const hasIntro = await intro.waitFor({state:'visible',timeout:5000}).then(() => true, () => false);
      if (hasIntro) {
        await intro.click();
      }
      const skipKey = page.getByRole('button', {name:'稍后配置', exact:true});
      if (await skipKey.waitFor({state:'visible',timeout:5000}).then(() => true, () => false)) await skipKey.click();
      await entry.click();
      const panel = page.getByRole('region', {name:'MinerU 文档解析'});
      await panel.waitFor();
      const notice = panel.getByRole('status');
      const select = panel.getByLabel('解析任务');
      const button = name => panel.getByRole('button', {name, exact:true});
      const settled = () => page.waitForFunction(() => !document.querySelector('[aria-label="MinerU 文档解析"] [role="status"]').textContent.includes('处理中'));
      const submit = async source => {
        await panel.getByLabel('文件路径').fill(source);
        await button('提交解析').click();
        await notice.filter({hasText:'任务已提交'}).waitFor();
        await settled();
        return select.inputValue();
      };
      await panel.getByLabel('所属会话').selectOption(config.other);
      await button('刷新任务').click();
      await settled();
      assert.equal(await select.locator('option').count(), 1);
      assert.equal(await panel.getByLabel('解析文本').count(), 0);
      await panel.getByLabel('所属会话').selectOption(config.owner);
      await button('刷新任务').click();
      await settled();
      checks.push('switch owner clears tasks/text', 'other owner has no tasks');
      let task;
      if (phase === 'fresh') {
        await button('检查连接').click();
        await notice.filter({hasText:'已收到健康响应'}).waitFor();
        task = await submit(config.source);
        await button('后台等待').click();
        await notice.filter({hasText:'已开始后台等待'}).waitFor();
        await page.waitForTimeout(2200);
        await button('刷新状态').click();
        await settled();
        assert.match(await select.locator('option:checked').innerText(), /completed/);
        await button('获取结果').click();
        await notice.filter({hasText:/结果已保存|本地缓存/}).waitFor();
        assert.equal(await button('停止本地等待').count(),0);
        checks.push('health', 'upload', 'background wait', 'completed result');
      } else {
        task = config.cached_task;
        await select.selectOption(task);
        await button('获取结果').click();
        await notice.filter({hasText:'本地缓存'}).waitFor();
        checks.push('cold task visible', 'cold cached result');
      }
      await button('阅读 Markdown').click();
      await panel.getByLabel('解析文本').filter({hasText:'# 本地协议验证'}).waitFor();
      assert.equal(await panel.locator('script').count(), 0);
      assert.equal(await page.evaluate(() => window.mineruUnsafe), undefined);
      await button('下一段').click();
      await page.waitForFunction(() => !document.querySelector('pre[aria-label="解析文本"]').textContent.includes('# 本地协议验证'));
      checks.push('read and next window', 'HTML remains inert text');
      if (phase === 'fresh') {
        const slowTask = await submit(config.slow);
        await button('后台等待').click();
        await notice.filter({hasText:'已开始后台等待'}).waitFor();
        await select.selectOption(task);
        assert.equal(await button('停止本地等待').count(),0);
        await select.selectOption(slowTask);
        await button('停止本地等待').click();
        await notice.filter({hasText:'已请求停止本地等待'}).waitFor();
        assert.equal(await button('停止本地等待').count(),0);
        await button('刷新状态').click();
        await settled();
        assert.match(await select.locator('option:checked').innerText(), /processing/);
        const failed = await submit(config.failed);
        await button('获取结果').click();
        await notice.filter({hasText:/task failed|任务失败/}).waitFor();
        await page.screenshot({path:path.join(out,'failure-state.png')});
        page.once('dialog', dialog => dialog.accept());
        await button('忘记本地任务').click();
        await notice.filter({hasText:'本地任务已清理'}).waitFor();
        assert.equal(await select.locator(`option[value="${failed}"]`).count(),0);
        checks.push('stop bound to selected task', 'stop clears finished control', 'remote remains processing', 'failure shown', 'forget confirmed');
        await select.selectOption(task);
        await button('阅读 Markdown').click();
        await panel.getByLabel('解析文本').filter({hasText:'# 本地协议验证'}).waitFor();
      }
      await panel.evaluate(element => {element.scrollTop = 0;});
      await page.screenshot({path:path.join(out,'desktop.png')});
      await page.setViewportSize({width:390,height:844});
      await panel.evaluate(element => {element.scrollTop = 0;});
      const bounds = await panel.boundingBox();
      assert(bounds.x >= 0 && bounds.x + bounds.width <= 390);
      assert(bounds.y >= 0 && bounds.y + bounds.height <= 844);
      await page.screenshot({path:path.join(out,'mobile.png')});
      checks.push('desktop and narrow viewport fit');
    }
    assert.deepEqual(errors, []);
    assert.equal(await page.locator('vite-error-overlay, nextjs-portal').count(),0);
    const report = {passed:true, phase, origin:new URL(page.url()).origin, title:await page.title(), browser:await browser.version(),
      browserPath:'Browser plugin not available; Playwright', checks:[...checks,'not blank','no runtime overlay','console clean'],errors,warnings};
    fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
    console.log('PASS '+phase+': '+checks.join(', '));
  } catch (error) {
    await page.screenshot({path:path.join(out,'browser-failure.png')});
    fs.writeFileSync(path.join(out,'browser-failure.json'),JSON.stringify({passed:false,error:String(error),errors,checks,body:await page.locator('body').innerText()},null,2));
    throw error;
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
