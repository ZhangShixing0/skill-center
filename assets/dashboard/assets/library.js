(function(){
  'use strict';
  const S=window.SkillCenter, M=window.CapabilitySearch, $=s=>document.querySelector(s), E=S.esc;
  $('#sidebar').innerHTML=S.nav('my');$('#search-icon').innerHTML=S.icon('search');$('#scan').innerHTML=S.icon('refresh')+'刷新本地索引';
  const FAVORITES='skill-center:favorites:v1';
  let initialFavorites=[];try{const value=JSON.parse(localStorage.getItem(FAVORITES)||'[]');if(Array.isArray(value))initialFavorites=value.filter(x=>typeof x==='string');}catch{}
  const state={skills:[],flows:[],summary:null,query:'',scope:'all',category:'',source:'',sort:'relevance',selected:'',favorites:new Set(initialFavorites),detailVersion:0,detail:null,loading:false};
  const labels={
    'project-readme':['项目介绍与使用说明','核对源码并编写可复现的项目文档'],
    'web-ui-review':['网页体验检查','检查手机布局、键盘操作和关键交互'],
    'market-research':['市场与竞品调研','比较产品与替代方案，记录证据与未知项'],
    'market-landscape-scan':['市场全景扫描','梳理市场、竞品与尚未满足的需求'],
    'jobs-to-be-done':['用户任务洞察','理解用户任务、阻力和期望的进步'],
    'positioning-statement':['产品定位陈述','明确目标用户、问题和差异化定位'],
    'storybrand-messaging':['品牌故事表达','把定位变成用户容易理解的品牌表达'],
    'autonomous-investigation':['自主调查','建立搜索计划，区分事实、推断与假设'],
    'paper-lookup':['论文检索','检索论文、预印本、引文和开放全文'],
    'scientific-writing':['科学写作','以可追溯证据组织研究论文与报告'],
    'scholar-evaluation':['学术质量复核','检查研究论证、证据与报告质量'],
    'frontend-design':['前端界面设计','建立明确的视觉方向与界面层级'],
    'frontend-app-builder':['前端应用搭建','制作可使用的网页应用与产品界面'],
    'impeccable':['界面设计与打磨','设计、审查和完善界面体验'],
    'ui-ux-pro-max':['UI / UX 设计参考','查找配色、排版和交互设计方案'],
    'web-design-guidelines':['网页体验检查','检查可访问性、交互与界面规范'],
    'mobile-web-responsive-rebuild':['移动端响应式重建','重新组织手机端布局与交互'],
    'copy-editing':['文案编辑','审阅、润色与优化已有文案'],
    'humanizer-zh':['中文自然表达','去除模板化表达，让文字更自然'],
    'made-to-stick':['让表达被记住','提炼具体、可信、容易记忆的信息'],
    'contagious':['传播机制设计','分析内容为何被分享并优化传播'],
    'execution-cockpit':['执行过程看板','展示多步骤任务的进展、证据与验证'],
    'skill-manager':['Skill 管理中心','维护能力来源，回顾使用与反馈'],
    'skill-creator':['创建与更新 Skill','编写可复用的技能说明和支持资源'],
    'skill-installer':['安装 Skill','发现并安装需要的技能包'],
    'find-skills':['查找新 Skill','从任务发现可用的技能与扩展'],
    'imagegen':['图像生成与编辑','生成图片、修改图像和制作透明素材'],
    'nature-figure':['科研图表','制作和检查可投稿的科学图表'],
    'safe-server-deploy':['服务器安全部署','验证发布包、备份、部署和回退'],
    'test-driven-development':['测试驱动开发','用行为测试验证复杂逻辑与回归修复'],
    'remotion-best-practices':['Remotion 开发参考','编写和渲染基于代码的视频'],
    'discovery-interview-prep':['用户访谈准备','明确访谈目标、对象与验证问题'],
    'create-original-ip':['原创角色 IP','建立角色体系与产品呈现'],
    'social':['社交内容运营','创作和优化社交平台内容'],
    'manim-video':['数学与技术动画','制作公式推导与算法讲解视频'],
    'openai-docs':['OpenAI 产品文档','查阅 Codex 与 OpenAI 产品的官方资料']
  };
  const baseName=s=>s.name.split(':').at(-1);
  const label=s=>labels[s.name]||labels[baseName(s)];
  const title=s=>s.display_name_zh||label(s)?.[0]||s.display_name||s.name;
  const description=s=>s.description_zh||label(s)?.[1]||s.description||'查看完整说明了解适用范围';
  const isPublic=s=>['system','plugin','public-installed'].includes(s.classification)||['system','plugin'].includes(s.source_kind);
  const owned=s=>s.source_kind==='project'||['self-authored','adapted'].includes(s.classification);
  const inbox=s=>!owned(s)&&!isPublic(s)&&s.classification==='unknown';
  const status=s=>s.source_kind==='project'?'项目能力':S.labels.classification[s.classification]||'待确认';
  const icon=s=>/voice|audio/.test(s.name)?'mic':/video|image|html|figure/.test(s.name)?'image':/research|investigation|market|paper/.test(s.name)?'compass':/github|code|app|frontend/.test(s.name)?'code':'book';
  const safeURL=value=>{try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:'';}catch{return '';}};
  function searchItem(s){return {...s,display_name:`${title(s)} ${s.display_name||''}`,description:`${description(s)} ${s.description||''}`};}
  function match(s){return M.match(searchItem(s),state.query);}
  function filtered(){
    const result=state.skills.filter(s=>{
      const scope=state.scope==='all'||(state.scope==='owned'&&owned(s))||(state.scope==='inbox'&&inbox(s))||(state.scope==='public'&&isPublic(s))||(state.scope==='favorites'&&state.favorites.has(s.name));
      return scope&&(!state.category||s.category===state.category)&&(!state.source||s.source_kind===state.source)&&match(s).score>0;
    });
    return result.sort((a,b)=>{
      if(state.sort==='relevance'){
        if(state.query.trim()){const diff=match(b).score-match(a).score;if(diff)return diff;}
        const fav=Number(state.favorites.has(b.name))-Number(state.favorites.has(a.name));if(fav)return fav;
        const usage=(b.uses_30||0)-(a.uses_30||0);if(usage)return usage;
      }
      if(state.sort==='recent'){const time=(b.last_used||'').localeCompare(a.last_used||'');if(time)return time;}
      if(state.sort==='usage'){const count=(b.uses_all||0)-(a.uses_all||0);if(count)return count;}
      return title(a).localeCompare(title(b),'zh-CN');
    });
  }
  function persistFavorites(){try{localStorage.setItem(FAVORITES,JSON.stringify([...state.favorites]));return true;}catch{S.toast('当前浏览器无法保存收藏，本次会话仍可使用。',true);return false;}}
  function favoriteButton(s){const on=state.favorites.has(s.name);return `<button class="favorite" data-favorite="${E(s.id)}" type="button" aria-label="${on?'取消收藏':'收藏'} ${E(title(s))}" aria-pressed="${on}">${S.icon('star')}</button>`;}
  function renderRows(){
    const items=filtered();
    $('#skills-list').innerHTML=items.length?items.map(s=>{
      const result=match(s);return `<div class="cap-row ${state.selected===s.id?'selected':''}" data-row="${E(s.id)}"><button class="cap-select" data-select="${E(s.id)}" type="button" aria-pressed="${state.selected===s.id}"><span class="cap-icon">${S.icon(icon(s))}</span><span><strong>${E(title(s))}</strong><small ${state.query?'class="search-reason"':''}>${E(state.query?`匹配：${result.reasons.join('、')||'完整关键词'}`:description(s))}</small></span></button><span class="cap-category">${E(s.category||'其他')}</span><span class="cap-state" data-kind="${inbox(s)?'inbox':owned(s)?'owned':'public'}">${E(status(s))}</span>${favoriteButton(s)}</div>`;
    }).join(''):`<div class="list-message"><strong>${state.scope==='favorites'?'这里还没有匹配的收藏':'没有找到匹配的能力'}</strong><p>${state.scope==='favorites'?'点击能力旁的星形按钮收藏；收藏仅保存在当前浏览器。':'试试更短的任务词，例如“视频”“调研”或“GitHub”，也可以清除筛选。'}</p></div>`;
    $('#skills-list').setAttribute('aria-busy','false');
    $('#result-count').textContent=`显示 ${items.length} 项 · 共 ${state.skills.length} 项当前能力`;
    document.querySelectorAll('[data-scope]').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.scope===state.scope)));
    const flows=state.query.trim()?state.flows.filter(f=>M.match(f,state.query).score>0).sort((a,b)=>M.match(b,state.query).score-M.match(a,state.query).score).slice(0,2):[];
    $('#workflow-matches').hidden=!flows.length;$('#workflow-matches').innerHTML=flows.length?`<strong>也可以用工作流完成</strong>${flows.map(f=>`<a href="workflows.html#${encodeURIComponent(f.id)}">${E(f.title)} · ${f.available_count}/${f.step_count} 可用</a>`).join('')}`:'';
    if(!items.some(s=>s.id===state.selected)){
      state.selected='';state.detailVersion++;state.detail=null;
      $('#capability-detail').classList.remove('mobile-open');
      if(items.length)select(items[0].id,false);else $('#capability-detail').innerHTML='<div class="detail-placeholder">换一个筛选条件，再选择能力查看详情。</div>';
    }
  }
  function renderSummary(){
    const s=state.summary;S.setCounts(s);
    $('#overview').innerHTML=`<span><strong>${state.skills.length}</strong>当前能力</span><span><strong>${s.my_skills}</strong>已确认归属</span><span><strong>${s.inbox_skills}</strong>待认领</span><span><strong>${s.duplicate_locations}</strong>重复位置</span><a href="manage.html">查看归属与维护</a>`;
    const scanned=s.latest_scan?.scanned_at;
    $('#scan-status').textContent=scanned?`上次扫描 ${S.dateTime(scanned)}`:'尚无扫描记录';
    const stale=scanned&&Date.now()-new Date(scanned).getTime()>7*86400000;
    if(stale){$('#load-notice').hidden=false;$('#load-notice').textContent='本地索引已超过 7 天未扫描，点击“刷新本地索引”发现新安装的能力。';}else $('#load-notice').hidden=true;
  }
  function usageGuideHTML(s,detail){
    const g=window.TaskBrief.guideFor(s,detail),list=items=>`<ul>${items.map(v=>`<li>${E(v)}</li>`).join('')}</ul>`;
    return `<h3>适合什么时候用</h3>${list(g.when)}<h3>需要准备什么</h3>${list(g.inputs)}<h3>会交付什么</h3>${list(g.outputs)}<details><summary>看一个示例任务</summary><p>${E(g.example)}</p><button class="button button-small guide-example-button" type="button" id="start-example">用这个示例准备任务</button></details><p class="guide-note">${E(g.note)}</p>`;
  }
  function detailHTML(s,detail){
    const flows=state.flows.filter(f=>f.steps.some(step=>step.skill===s.name));
    const source=s.source_status_label||'来源尚待确认';
    const upstream=s.source_clickable?safeURL(s.upstream_source):'';
    const fullLink=!isPublic(s)?`<a class="button" href="skill.html?id=${encodeURIComponent(s.name)}">完整说明、版本与反馈</a>`:upstream?`<a class="button" href="${E(upstream)}" target="_blank" rel="noopener noreferrer">打开已验证上游</a>`:'<a class="button" href="public-skills.html">查看公开能力索引</a>';
    return `<div class="peek-header"><div class="peek-top"><span>当前已发现</span><button class="detail-close" id="close-detail" type="button">返回列表</button>${favoriteButton(s)}</div><h2>${E(title(s))}</h2><code>${E(s.name)}</code></div><div class="peek-body"><button class="button button-primary task-start" id="start-task" type="button">开始任务 ${S.icon('arrow')}</button><button class="button quick-copy" id="copy-invocation" type="button">${S.icon('copy')} 仅复制调用提示</button><div id="skill-usage-guide" class="usage-guide">${usageGuideHTML(s,detail)}</div>${fullLink}<details class="skill-evidence"><summary>来源、版本与使用记录</summary><dl><dt>安装来源</dt><dd>${E(s.source_label||S.labels.source[s.source_kind]||'未知')}</dd><dt>作者归属</dt><dd>${E(status(s))}</dd><dt>上游来源</dt><dd>${E(source)}</dd><dt>索引版本</dt><dd class="version">${E(s.content_hash||s.version_hash||'未记录')}</dd><dt>已记录调用</dt><dd>${Number(s.uses_all||0)} 次 · 部分覆盖</dd>${s.duplicate_count?`<dt>其他位置</dt><dd>${s.duplicate_count} 个副本</dd>`:''}</dl><span id="detail-status" class="peek-note" role="status">${detail?`${detail.versions?.length||0} 条版本记录 · ${detail.feedback?.length||0} 条反馈`:''}</span></details><details><summary>查看原始描述</summary><p>${E(s.description_original||s.description||'没有原始描述')}</p></details></div>${flows.length?`<div class="peek-links">${flows.map(f=>`<a href="workflows.html#${encodeURIComponent(f.id)}"><span>${E(f.title)}<br>${f.available_count}/${f.step_count} 步骤可用</span>${S.icon('arrow')}</a>`).join('')}</div>`:''}`;
  }
  async function select(id,focus){
    const s=state.skills.find(x=>x.id===id);if(!s)return;
    state.selected=id;state.detail=null;const version=++state.detailVersion;
    document.querySelectorAll('[data-row]').forEach(el=>{const on=el.dataset.row===id;el.classList.toggle('selected',on);el.querySelector('[data-select]').setAttribute('aria-pressed',String(on));});
    $('#capability-detail').innerHTML=detailHTML(s,null);
    if(focus&&matchMedia('(max-width:820px)').matches){$('#capability-detail').classList.add('mobile-open');$('#capability-detail').focus({preventScroll:true});$('#capability-detail').scrollIntoView({block:'start',behavior:'auto'});}
    if(isPublic(s))return;
    try{const detail=await S.api('/api/skill?id='+encodeURIComponent(id));if(version!==state.detailVersion)return;state.detail=detail;$('#detail-status').textContent=`${detail.versions?.length||0} 条版本记录 · ${detail.feedback?.length||0} 条反馈`;const guide=$('#skill-usage-guide');if(!guide.contains(document.activeElement))guide.innerHTML=usageGuideHTML(s,detail);}catch{if(version===state.detailVersion)$('#detail-status').textContent='详细记录暂不可用，可重试选择或刷新页面。';}
  }
  function reset(){state.query='';state.scope='all';state.category='';state.source='';state.sort='relevance';$('#search').value='';$('#category').value='';$('#source').value='';$('#sort').value='relevance';renderRows();}
  async function load(){
    const [summary,skills,flows]=await Promise.all([S.api('/api/summary'),S.api('/api/skills?scope=all'),S.api('/api/workflows')]);
    state.summary=summary;state.skills=(skills.skills||[]).filter(s=>s.is_present);state.flows=flows.workflows||[];
    const categories=[...new Set(state.skills.map(s=>s.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
    if(!categories.includes(state.category))state.category='';
    $('#category').innerHTML='<option value="">所有领域</option>'+categories.map(c=>`<option value="${E(c)}">${E(c)}</option>`).join('');$('#category').value=state.category;
    state.selected='';renderSummary();renderRows();
  }
  function loadError(err){$('#skills-list').setAttribute('aria-busy','false');$('#skills-list').innerHTML='<p class="list-message">能力库暂时无法读取，请重试。</p>';$('#load-notice').hidden=false;$('#load-notice').innerHTML=`本地服务暂时不可用。${E(err.message)} <button type="button" id="retry">重试加载</button>`;$('#result-count').textContent='加载失败';$('#capability-detail').innerHTML='<div class="detail-placeholder">恢复连接后，能力信息会显示在这里。</div>';}
  window.TaskFinder.configure({skills:()=>state.skills,title});
  $('#open-task-finder').addEventListener('click',()=>window.TaskFinder.open(state.query));
  $('#search').addEventListener('input',e=>{state.query=e.target.value;renderRows();});
  for(const key of ['category','source','sort'])$('#'+key).addEventListener('change',e=>{state[key]=e.target.value;renderRows();});
  $('#reset').addEventListener('click',reset);
  document.addEventListener('keydown',e=>{const preparing=!$('#task-workspace').hidden,finding=!$('#task-finder').hidden;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();const input=$(preparing?'#task-goal':finding?'#finder-goal':'#search');input.focus();input.select();}if(!preparing&&!finding&&e.key==='Escape'&&$('#capability-detail').classList.contains('mobile-open')){$('#capability-detail').classList.remove('mobile-open');document.querySelector(`[data-select="${CSS.escape(state.selected)}"]`)?.focus();}});
  document.addEventListener('click',async e=>{
    const scope=e.target.closest('[data-scope]');if(scope){state.scope=scope.dataset.scope;renderRows();return;}
    const task=e.target.closest('[data-task]');if(task){reset();state.query=task.dataset.task;$('#search').value=state.query;renderRows();return;}
    const row=e.target.closest('[data-select]');if(row){select(row.dataset.select,true);return;}
    if(e.target.closest('#start-task,#start-example')){const s=state.skills.find(x=>x.id===state.selected);if(s)window.TaskWorkspace.open(s,window.TaskBrief.guideFor(s,state.detail),title(s),{example:Boolean(e.target.closest('#start-example'))});return;}
    const fav=e.target.closest('[data-favorite]');if(fav){
      const s=state.skills.find(x=>x.id===fav.dataset.favorite);if(!s)return;
      const region=fav.closest('#capability-detail')?'#capability-detail':'#skills-list';
      const on=!state.favorites.has(s.name);on?state.favorites.add(s.name):state.favorites.delete(s.name);
      const saved=persistFavorites(),selected=state.selected,scroll=$('#skills-list').scrollTop;
      renderRows();$('#skills-list').scrollTop=scroll;
      if(state.selected===selected){const current=state.skills.find(x=>x.id===selected);if(current)$('#capability-detail').innerHTML=detailHTML(current,state.detail);}
      const next=document.querySelector(`${region} [data-favorite="${CSS.escape(s.id)}"]`)||document.querySelector('#skills-list [data-select]')||document.querySelector('[data-scope=favorites]');
      next?.focus({preventScroll:true});
      if(saved)S.toast(on?'已收藏 · 保存在当前浏览器':'已取消收藏');return;
    }
    if(e.target.closest('#copy-invocation')){const s=state.skills.find(x=>x.id===state.selected);if(s)S.copy(`请使用 $${s.name}，先确认任务目标、输入材料和交付要求，再按 Skill 的工作流完成任务。`);}
    if(e.target.closest('#close-detail')){$('#capability-detail').classList.remove('mobile-open');document.querySelector(`[data-select="${CSS.escape(state.selected)}"]`)?.focus();}
    if(e.target.closest('#retry')){try{await load();}catch(err){loadError(err);}}
  });
  $('#scan').addEventListener('click',async()=>{
    if(state.loading)return;state.loading=true;const btn=$('#scan');btn.disabled=true;btn.textContent='扫描中…';
    try{const result=await S.api('/api/scan',{method:'POST',body:'{}'});await load();S.toast(`索引已刷新：新增 ${result.added_count??result.delta?.added?.length??0}，更新 ${result.updated_count??result.delta?.updated?.length??0}，移除 ${result.removed_count??result.delta?.removed?.length??0}`);}catch(err){S.toast(`扫描未完成：${err.message}`,true);}finally{state.loading=false;btn.disabled=false;btn.innerHTML=S.icon('refresh')+'刷新本地索引';}
  });
  load().catch(loadError);
})();
