const fs = require('fs');
const path = require('path');

const root = 'D:/Work/from-material-to-report-ppt/ppt';
const templatePath = 'C:/Users/zooma/.codex/skills/guizang-ppt-skill/assets/template-swiss.html';
let tpl = fs.readFileSync(templatePath, 'utf8');
tpl = tpl.replace(/<title>[\s\S]*?<\/title>/, '<title>从材料到汇报 · 用知识库和 AI 完成 PPT 生产闭环</title>');

const total = 29;
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const no = (n) => String(n).padStart(2, '0');
const chrome = (n, label = 'MATERIAL TO REPORT') => `
  <div class="chrome-min">
    <div class="l">${label}</div>
    <div class="r">${no(n)} / ${total}</div>
  </div>`;

function cover() {
  return `
<section class="slide accent" data-layout="SWISS-COVER-ASCII" data-animate="hero">
  <div class="canvas-card">
    <canvas class="ascii-bg" aria-hidden="true"></canvas>
    ${chrome(1, 'KNOWLEDGE BASE × AI')}
    <div style="flex:1;padding:0;display:grid;grid-template-rows:auto 1fr auto;gap:2.8vh">
      <div data-anim="kicker" class="t-meta" style="color:rgba(255,255,255,.78);letter-spacing:.18em">用知识库和 AI 完成 PPT 生产闭环</div>
      <h1 data-anim="title" style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(10.4vw,18vh);line-height:.98;letter-spacing:0;color:#fff">从材料<br>到汇报</h1>
      <div data-anim="bottom" style="display:grid;grid-template-rows:auto auto;gap:1.6vh;border-top:1px solid rgba(255,255,255,.24);padding-top:2.2vh">
        <div class="lead" style="max-width:56ch;color:rgba(255,255,255,.88);font-size:max(20px,1.45vw)">知识库真正的价值，不是存资料，而是在关键时刻产出成果。</div>
        <div style="display:flex;justify-content:space-between;align-items:end">
          <div class="t-meta" style="color:rgba(255,255,255,.62)">COURSE NOTE</div>
          <div class="t-meta" style="color:rgba(255,255,255,.62)">ARROW KEYS / SWIPE</div>
        </div>
      </div>
    </div>
  </div>
</section>`;
}

function listSlide(n, title, items, quote, label = 'METHOD') {
  return `
<section class="slide" data-layout="S19" data-animate="grid-reveal">
  <div class="canvas-card">
    ${chrome(n, label)}
    <div style="flex:1;padding:0;display:grid;grid-template-rows:auto 1fr auto;gap:4vh">
      <div data-anim="head" style="display:flex;flex-direction:column;gap:1.4vh">
        <div class="t-meta" style="color:var(--text-helper);letter-spacing:.18em">${label}</div>
        <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.4vw,9.8vh);line-height:1.08;letter-spacing:0">${esc(title)}</h2>
      </div>
      <div data-anim="grid" style="display:grid;grid-template-columns:repeat(${items.length > 4 ? 3 : items.length},1fr);gap:16px;align-content:start">
        ${items.map((it, i) => `<div class="card-fill" style="min-height:17vh;padding:2.2vh 1.4vw;display:flex;flex-direction:column;justify-content:space-between;border-top:3px solid ${i === 0 ? 'var(--accent)' : 'var(--border-subtle)'}">
          <div style="font-family:var(--sans);font-weight:200;font-size:min(3.2vw,5.7vh);line-height:1;color:${i === 0 ? 'var(--accent)' : 'var(--text-placeholder)'}">${no(i + 1)}</div>
          <div style="font-family:var(--sans),var(--sans-zh);font-size:max(18px,1.2vw);line-height:1.42;font-weight:500;color:var(--text-primary)">${esc(it)}</div>
        </div>`).join('')}
      </div>
      ${quote ? `<div data-anim="bottom" style="border-top:1px solid var(--border-subtle);padding-top:2vh"><p class="lead" style="font-size:max(20px,1.35vw);color:var(--text-primary)">${esc(quote)}</p></div>` : ''}
    </div>
  </div>
</section>`;
}

function flowSlide(n, title, steps, quote) {
  return `
<section class="slide" data-layout="S14" data-animate="timeline-walk">
  <div class="canvas-card">
    ${chrome(n, 'FLOW')}
    <div style="flex:1;padding:0;display:grid;grid-template-rows:auto 1fr auto;gap:4vh">
      <div data-anim="head" style="display:flex;flex-direction:column;gap:1.4vh">
        <div class="t-meta" style="color:var(--text-helper);letter-spacing:.18em">FLOW</div>
        <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.2vw,9.2vh);line-height:1.08;letter-spacing:0">${esc(title)}</h2>
      </div>
      <div data-anim="timeline" style="display:grid;grid-template-columns:repeat(${steps.length},1fr);gap:0;align-items:center;border-top:1px solid var(--border-subtle);border-bottom:1px solid var(--border-subtle)">
        ${steps.map((s, i) => `<div style="min-height:28vh;padding:3vh 1.2vw;border-right:${i === steps.length - 1 ? '0' : '1px solid var(--border-subtle)'};display:flex;flex-direction:column;justify-content:space-between">
          <div style="width:12px;height:12px;background:${i === steps.length - 1 ? 'var(--accent)' : 'var(--ink)'}"></div>
          <div><div style="font-family:var(--sans);font-weight:200;font-size:min(3.8vw,6.8vh);line-height:1;color:${i === steps.length - 1 ? 'var(--accent)' : 'var(--text-placeholder)'}">${no(i + 1)}</div><div style="margin-top:1.2vh;font-size:max(17px,1.05vw);font-weight:500;line-height:1.35">${esc(s)}</div></div>
        </div>`).join('')}
      </div>
      <div data-anim="bottom" style="border-top:2px solid var(--accent);padding-top:2vh"><p class="lead" style="font-size:max(20px,1.35vw)">${esc(quote)}</p></div>
    </div>
  </div>
</section>`;
}

function compareSlide(n, title, leftTitle, leftItems, rightTitle, rightItems, quote) {
  return `
<section class="slide" data-layout="S11" data-animate="duo-mirror">
  <div class="canvas-card">
    ${chrome(n, 'COMPARE')}
    <div style="flex:1;padding:0;display:grid;grid-template-rows:auto 1fr auto;gap:3.4vh">
      <div data-anim="head" style="display:flex;flex-direction:column;gap:1.2vh">
        <div class="t-meta" style="color:var(--text-helper);letter-spacing:.18em">COMPARE</div>
        <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(4.9vw,8.8vh);line-height:1.08;letter-spacing:0">${esc(title)}</h2>
      </div>
      <div data-anim="duo" style="display:grid;grid-template-columns:1fr 1px 1fr;gap:3vw;align-items:start">
        <div><div class="t-cat" style="margin-bottom:2vh;color:var(--text-helper)">${esc(leftTitle)}</div>${leftItems.map((x) => `<div style="padding:1.7vh 0;border-top:1px solid var(--border-subtle);font-size:max(18px,1.18vw);font-weight:400;color:var(--text-secondary)">${esc(x)}</div>`).join('')}</div>
        <div style="height:100%;background:var(--border-subtle)"></div>
        <div><div class="t-cat" style="margin-bottom:2vh;color:var(--accent)">${esc(rightTitle)}</div>${rightItems.map((x, i) => `<div style="padding:1.7vh 0;border-top:1px solid ${i === 0 ? 'var(--accent)' : 'var(--border-subtle)'};font-size:max(18px,1.18vw);font-weight:500;color:var(--text-primary)">${esc(x)}</div>`).join('')}</div>
      </div>
      <div data-anim="bottom" style="border-top:2px solid var(--accent);padding-top:2vh"><p class="lead" style="font-size:max(20px,1.35vw)">${esc(quote)}</p></div>
    </div>
  </div>
</section>`;
}

function closedLoop() {
  const nodes = [
    ['知识库沉淀', '资料、案例、数据、观点'],
    ['AI 重构', '提炼、归类、压缩、结构化'],
    ['汇报交付', 'PPT、报告、简报、讲话稿'],
  ];
  return `
<section class="slide" data-layout="S17" data-animate="system-diagram">
  <div class="canvas-card">
    ${chrome(9, 'CLOSED LOOP')}
    <div style="flex:1;padding:0;display:grid;grid-template-rows:auto 1fr auto;gap:3.4vh">
      <div data-anim="head" style="display:flex;flex-direction:column;gap:1.2vh">
        <div class="t-meta" style="color:var(--text-helper);letter-spacing:.18em">CLOSED LOOP</div>
        <h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5.3vw,9.5vh);line-height:1.08;letter-spacing:0">从存资料，到出成果</h2>
      </div>
      <div data-anim="diagram" style="display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:1.4vw;align-items:stretch">
        ${nodes.map(([h, b], i) => `<div class="${i === 1 ? 'card-accent' : 'card-fill'}" style="padding:3vh 1.8vw;min-height:34vh;display:flex;flex-direction:column;justify-content:space-between"><div class="t-meta" style="color:${i === 1 ? 'var(--accent-on)' : 'var(--text-helper)'}">0${i + 1}</div><div><h3 style="font-size:max(24px,2vw);font-weight:400;line-height:1.2;margin-bottom:2vh">${h}</h3><p style="font-size:max(18px,1.1vw);line-height:1.65;color:${i === 1 ? 'var(--accent-on)' : 'var(--text-secondary)'}">${b}</p></div></div>`).join('<div style="display:flex;align-items:center;font-size:min(3vw,5vh);font-weight:200;color:var(--accent)">→</div>')}
      </div>
      <div data-anim="bottom" style="border-top:2px solid var(--accent);padding-top:2vh"><p class="lead" style="font-size:max(20px,1.35vw)">知识库解决素材问题，AI 解决重构问题，人解决判断问题。</p></div>
    </div>
  </div>
</section>`;
}

function promptSlide(n, title, prompt) {
  return `
<section class="slide grey" data-layout="S13" data-animate="field-notes">
  <div class="canvas-card">
    ${chrome(n, 'PROMPT')}
    <div style="flex:1;padding:0;display:grid;grid-template-columns:.88fr 1.12fr;gap:3vw;align-items:stretch">
      <div data-anim="head" style="display:flex;flex-direction:column;justify-content:space-between;border-right:1px solid var(--border-subtle);padding-right:2.6vw">
        <div><div class="t-meta" style="color:var(--accent);letter-spacing:.18em">PROMPT TEMPLATE</div><h2 style="margin-top:1.8vh;font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(4.6vw,8.2vh);line-height:1.1;letter-spacing:0">${esc(title)}</h2></div>
        <div style="width:52px;height:52px;background:var(--accent)"></div>
      </div>
      <div data-anim="note" style="background:var(--paper);padding:3vh 2vw;border-top:3px solid var(--accent);display:flex;align-items:center">
        <p style="font-family:var(--sans),var(--sans-zh);font-size:max(18px,1.16vw);line-height:1.75;font-weight:400;color:var(--text-primary)">${esc(prompt)}</p>
      </div>
    </div>
  </div>
</section>`;
}

function tableSlide(n, title, rows, quote) {
  return `
<section class="slide" data-layout="S18" data-animate="stacked-ledger">
  <div class="canvas-card">
    ${chrome(n, 'LEDGER')}
    <div style="flex:1;padding:0;display:grid;grid-template-rows:auto 1fr auto;gap:3.2vh">
      <div data-anim="head" style="display:flex;flex-direction:column;gap:1.2vh"><div class="t-meta" style="color:var(--text-helper);letter-spacing:.18em">LEDGER</div><h2 style="font-family:var(--sans),var(--sans-zh);font-weight:200;font-size:min(5vw,9vh);line-height:1.08;letter-spacing:0">${esc(title)}</h2></div>
      <div data-anim="rows" style="display:flex;flex-direction:column;border-top:1px solid var(--border-subtle)">${rows.map((r, i) => `<div style="display:grid;grid-template-columns:1.1fr 1.6fr;gap:2vw;padding:1.55vh 0;border-bottom:1px solid var(--border-subtle);align-items:center"><div style="font-size:max(18px,1.18vw);font-weight:600;color:${i === rows.length - 1 ? 'var(--accent)' : 'var(--text-primary)'}">${esc(r[0])}</div><div style="font-size:max(17px,1.05vw);line-height:1.45;color:var(--text-secondary)">${esc(r[1])}</div></div>`).join('')}</div>
      <div data-anim="bottom" style="border-top:2px solid var(--accent);padding-top:2vh"><p class="lead" style="font-size:max(20px,1.32vw)">${esc(quote)}</p></div>
    </div>
  </div>
</section>`;
}

function closing() {
  return `
<section class="slide split" data-layout="S09" data-animate="split-statement">
  <div class="canvas-card">
    <div class="split-half">
      <div class="half b-accent" style="padding:5.6vh 3.6vw 4.4vh;justify-content:space-between;position:relative;overflow:hidden">
        <canvas class="ascii-bg" aria-hidden="true"></canvas>
        <div class="chrome-min" style="margin-bottom:0;position:relative;z-index:1"><div class="l">29 / 29</div><div class="r">CLOSING</div></div>
        <div data-anim="manifesto" style="display:flex;flex-direction:column;gap:2vh;position:relative;z-index:1">
          <div class="t-meta" style="color:rgba(255,255,255,.78);letter-spacing:.18em;margin-bottom:1.6vh">FINAL LINE</div>
          <h2 style="font-family:var(--sans),var(--sans-zh);font-size:min(7.4vw,13vh);line-height:1;letter-spacing:0;font-weight:200;color:#fff">从材料到汇报，是知识库真正开始工作的地方</h2>
        </div>
        <div data-anim="signature" style="border-top:1px solid rgba(255,255,255,.24);padding-top:2vh;position:relative;z-index:1"><div class="t-meta" style="color:rgba(255,255,255,.62)">END OF DECK</div></div>
      </div>
      <div class="half" style="padding:5.6vh 3.6vw 4.4vh;justify-content:space-between">
        <div class="chrome-min"><div class="l">TAKEAWAY</div><div class="r">FROM SYSTEM</div></div>
        <div data-anim="rules" style="display:flex;flex-direction:column;gap:0">
          ${['平时沉淀材料。', '关键时刻调用材料。', '用 AI 重构材料。', '用人的判断完成表达。'].map((x, i) => `<div style="display:grid;grid-template-columns:auto 1fr;gap:2vw;align-items:start;padding:2.4vh 0;border-top:1px solid var(--border-subtle)"><div style="font-family:var(--sans);font-weight:200;font-size:min(4vw,7vh);line-height:.9;color:${i === 3 ? 'var(--accent)' : 'var(--text-placeholder)'}">${no(i + 1)}</div><div style="font-size:max(22px,1.8vw);line-height:1.25;font-weight:400;color:var(--text-primary)">${x}</div></div>`).join('')}
          <div style="padding:2.4vh 0;border-top:2px solid var(--accent);font-size:max(22px,1.6vw);line-height:1.45;font-weight:500;color:var(--accent)">不要从空白页开始做 PPT，要从自己的知识系统开始。</div>
        </div>
      </div>
    </div>
  </div>
</section>`;
}

const slides = [
  cover(),
  flowSlide(2, '这是知识库应用的最后一公里', ['信息收集', '知识库沉淀', '专题调研', '自动简报', 'PPT 汇报'], '前面几节课做的是“养系统”，这一节课看系统能不能产出东西。'),
  listSlide(3, 'PPT 的问题，首先不是美化问题', ['不是模板不够高级', '不是动画不够丰富', '不是配色不够专业', '不是软件不会操作', '而是材料没有被重新组织'], '很多 PPT 不是不好看，是根本没想清楚。', 'MISUNDERSTANDING'),
  listSlide(4, '很多 PPT 不是做出来的，是拼出来的', ['临时找资料', '复制旧材料', '东拼西凑', '套模板救场', '页面很多，主线很弱'], '材料越多，不等于汇报越清楚。', 'OLD WAY'),
  flowSlide(5, '用知识库生产 PPT，而不是从空白页开始', ['信息收集', '知识库沉淀', '素材调用', '主线提炼', '页面结构', '汇报交付'], '平时收集，关键时刻调用；AI 提炼主线，人工校准定稿。'),
  listSlide(6, 'PPT 不是材料搬家，而是结构化表达', ['给谁看', '为什么看', '看完要形成什么判断', '哪些内容必须前置', '哪些内容必须删除'], '做 PPT 的第一步，不是打开 PowerPoint，而是判断场景。', 'ESSENCE'),
  compareSlide(7, '不同 PPT，不是换模板，而是换逻辑', '类型', ['汇报型', '展示型', '教学型'], '逻辑', ['判断清楚、依据充分', '形象可信、亮点明确', '节奏清楚、便于理解'], '汇报型重结构，展示型重感知，教学型重节奏。'),
  listSlide(8, '知识库不是仓库，是 PPT 的前端生产线', ['事实资产：政策、数据、进展', '案例资产：项目、活动、成果', '观点资产：判断、经验、结论', '表达资产：标题、口径、成熟表述'], '最值钱的不是资料，而是可复用的判断和表达。', 'ASSETS'),
  closedLoop(),
  flowSlide(10, '不要一键生成 PPT，要分步重构材料', ['判断场景', '检索材料', '提炼主线', '设计结构', '生成文案', '审稿校准'], 'AI 负责提效，人负责判断。'),
  listSlide(11, '先问清楚，这份 PPT 要解决什么问题', ['对象是谁', '时间多长', '会上讲还是会后看', '是汇报、展示还是教学', '希望对方形成什么判断'], '场景不清，页面必乱。', 'STEP 01'),
  listSlide(12, '先拿原料，不急着排版', ['背景与问题', '工作基础', '典型案例', '数据成效', '经验判断', '下一步建议'], 'AI 检索出来的是原料，不是成品。', 'STEP 02'),
  listSlide(13, '一份 PPT 必须有一句话的魂', ['这件事本质是什么', '最重要的判断是什么', '最有力的依据是什么', '哪些材料应该删掉'], '没有主线，PPT 就是资料堆。', 'STEP 03'),
  listSlide(14, '每一页都要回答一个问题', ['这一页想让观众相信什么', '这一页支撑哪一个判断', '这一页需要什么材料', '这一页适合什么形式'], '没有页面意图，就会变成材料分页。', 'STEP 04'),
  compareSlide(15, '标题要像判断，不要像目录', '反例', ['AI 应用场景'], '正例', ['不是演示 AI，而是让 AI 进入业务链条。', '标题判断化', '正文短句化', '内容分组化', '数据证据化', '背景口头化'], '页面语言要帮助观众判断，而不是替材料贴标签。'),
  listSlide(16, 'AI 初稿不能直接上会', ['主线是否清楚', '标题是否空泛', '有没有材料搬家', '有没有数据支撑', '有没有超出口径', '表达是否适合对象'], 'AI 可以生成内容，但不能替你承担判断责任。', 'STEP 06'),
  compareSlide(17, '好标题不是概念，是判断', '弱标题', ['工作基础', '主要成效', 'AI 应用', '下一步计划'], '强标题', ['已有基础正在转化为系统能力', '重点项目验证了 AI 应用价值', 'AI 正在进入真实业务链条', '下一步从单点应用走向组织能力'], '标题决定观众如何理解这一页。'),
  listSlide(18, '一页只讲一个判断', ['不要塞满', '不要平均用力', '不要把所有材料都放上去', '只保留最能支撑判断的信息', '复杂背景留给口头讲'], 'PPT 上放的是骨架，不是全文。', 'CONTENT'),
  listSlide(19, '让观众一眼看懂关系', ['并列结构', '递进结构', '因果结构', '对比结构', '时间结构', '问题—方案结构'], '页面不是摆文字，而是呈现关系。', 'STRUCTURE'),
  listSlide(20, '好 PPT 不是花，是稳', ['一页一个判断', '一屏一个重点', '少文字，多结构', '少装饰，多秩序', '少口号，多证据'], '机关场景里，可信比惊艳重要。', 'VISUAL'),
  listSlide(21, '把 PPT 工作拆给 AI，而不是直接丢给 AI', ['场景判断提示词', '知识库素材提取提示词', '主线提炼提示词', '页面策划提示词', '页面文案提示词', '视觉建议提示词', '审稿校准提示词'], '会拆任务，比会写提示词更重要。', 'PROMPT TOOLBOX'),
  promptSlide(22, '先让 AI 帮你判断场景', '请你作为机关工作汇报 PPT 策划顾问，先不要生成 PPT。请根据我提供的材料，判断这份 PPT 的使用场景、汇报对象、核心目的、适合的表达风格，并指出哪些内容应该重点呈现，哪些内容应该压缩或删除。'),
  promptSlide(23, '从知识库中提取可用素材', '请基于我的知识库，围绕主题【XXX】检索和整理可用于 PPT 的材料。请不要直接生成 PPT，而是先按以下类别整理素材：背景与问题、工作基础、典型案例、数据和成效、经验判断、下一步建议。每类请提炼 3 到 5 条关键信息，并说明适合放在哪类 PPT 页面中。'),
  promptSlide(24, '把材料压缩成一句核心判断', '请根据以上素材，为这份 PPT 提炼一条清晰主线。要求回答三个问题：这份 PPT 想让观众形成什么判断？哪些材料最能支撑这个判断？哪些材料虽然相关，但不适合放入 PPT？请给出 3 个不同版本的主线表达。'),
  promptSlide(25, '先生成策划稿，再生成页面', '请基于以上主线，设计一份 6 页以内的 PPT 策划稿。每页包括：页面标题、页面意图、核心信息、对应知识库素材、建议页面形式。要求标题必须是判断句，不要使用空泛概念词；每页只表达一个核心意思；不要把材料直接搬到页面上。'),
  promptSlide(26, '把材料改写成页面语言', '请将每一页改写成可直接放入 PPT 的页面文案。要求每页一个主标题，正文不超过 5 条，每条不超过 20 字，语言稳重、简洁、适合机关汇报，保留必要数据和案例，删除背景铺垫和重复表述。'),
  promptSlide(27, '让 AI 先帮你挑毛病', '请从领导审阅角度审查这份 PPT 策划稿，重点检查主线是否清楚、页面标题是否空泛、是否存在材料搬家、是否缺少案例和数据支撑、是否有页面重复、是否有超出知识库证据范围的判断、表达是否适合当前汇报对象。请逐页提出修改建议，并给出优化后的页面标题。'),
  tableSlide(28, '知识库有没有价值，看它能不能产出成果', [['调研时', '生成报告'], ['跟踪时', '生成简报'], ['汇报时', '生成 PPT'], ['复盘时', '沉淀经验'], ['写作时', '形成文稿']], '知识库不是终点，它是工作成果的发动机。'),
  closing(),
];

const deck = `<div id="deck">\n${slides.join('\n')}\n</div>`;
tpl = tpl.replace(/<div id="deck">[\s\S]*?<\/div>\s*\n\s*<div id="nav"><\/div>/, deck + '\n\n<div id="nav"></div>');
fs.mkdirSync(path.join(root, 'images'), { recursive: true });
fs.writeFileSync(path.join(root, 'index.html'), tpl, 'utf8');
console.log(path.join(root, 'index.html'));
