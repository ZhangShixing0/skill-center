(function(){
  'use strict';
  const S=window.SkillCenter,E=S.esc,$=s=>document.querySelector(s);
  let options=null,candidates=[],lastQuery='',libraryScroll=0,rendered=false;
  function show(){
    $('#library-view').hidden=true;$('#task-finder').hidden=false;
    $('#workspace-label').textContent='按任务找能力';document.title='按任务找能力 · Skill Center';
  }
  function close(){
    $('#task-finder').hidden=true;$('#library-view').hidden=false;
    $('#workspace-label').textContent='能力库';document.title='能力库 · Skill Center';
    window.scrollTo(0,libraryScroll);$('#open-task-finder').focus({preventScroll:true});
  }
  function clearResults(){
    candidates=[];lastQuery='';$('#finder-results').innerHTML='';$('#finder-result-status').textContent='';
  }
  function run(){
    const input=$('#finder-goal'),query=input.value.trim();clearResults();
    $('#finder-error').textContent='';input.removeAttribute('aria-invalid');
    if(!query){$('#finder-error').textContent='先写下你想完成的具体任务。';input.setAttribute('aria-invalid','true');input.focus();return;}
    const skills=options.skills();
    if(!skills.length){$('#finder-results').innerHTML='<div class="finder-empty"><h2>能力索引还没有准备好</h2><p>目标仍保留在上方。返回能力库，等待加载或重试连接后再来。</p><button type="button" class="button" data-finder-back>返回能力库</button></div>';$('#finder-result-status').textContent='暂时无法匹配';return;}
    lastQuery=query;candidates=window.TaskMatch.recommend(skills,query);
    $('#finder-result-status').textContent=candidates.length?`找到 ${candidates.length} 项可先了解的能力`:'暂时没有找到合适的能力';
    if(!candidates.length){
      $('#finder-results').innerHTML='<div class="finder-empty"><h2>再具体一点，能更容易找到</h2><p>试着补充要处理的内容和交付物，例如“检查网页首页在手机上的布局”。也可以返回能力库按名称查找。</p><button type="button" class="button" id="finder-edit">修改任务描述</button><button type="button" class="button" data-finder-back>浏览全部能力</button></div>';return;
    }
    $('#finder-results').innerHTML=`<p class="finder-result-note">先选最适合当前这一步的能力。多个候选可能负责不同环节，请按用途选择。</p><div class="finder-candidates">${candidates.map((c,i)=>{
      const g=window.TaskBrief.guideFor(c.skill),name=options.title(c.skill);
      return `<article class="finder-candidate" aria-labelledby="finder-title-${i}"><div class="finder-candidate-main"><h2 id="finder-title-${i}">${E(name)}</h2><p class="finder-skill-name">${E(c.skill.name)}</p><p class="finder-reason">${E(c.reason)}</p><p class="finder-basis">依据：${E(c.basis)} · 当前本地索引</p><details><summary>核对适用场景与交付</summary><p>${E(g.when.join('；'))}</p><ul>${g.outputs.map(x=>`<li>${E(x)}</li>`).join('')}</ul></details></div><div class="finder-preparation"><h3>开始前准备</h3><ul>${g.inputs.map(x=>`<li>${E(x)}</li>`).join('')}</ul><p class="finder-guide-note">${g.kind==='curated'?'按本地说明整理；可在下一步补充材料。':'通用准备建议，具体要求以原始说明为准。'}</p><button type="button" class="button ${i===0?'button-primary':''}" data-finder-choose="${i}" aria-label="使用${E(name)}准备任务">准备这个任务 ${S.icon('arrow')}</button></div></article>`;
    }).join('')}</div>`;
  }
  function render(){
    $('#task-finder').innerHTML=`<div class="task-backline"><button type="button" class="task-back" data-finder-back>返回能力库</button><span>从目标找到适合当前这一步的能力</span></div>
      <header class="finder-heading"><h1 id="finder-heading" tabindex="-1">按任务找能力</h1><p>不用先记住 Skill 名称，写下你想完成的事。</p></header>
      <form id="finder-form" class="finder-form" novalidate><label for="finder-goal">你想完成什么</label><textarea id="finder-goal" rows="3" maxlength="2000" aria-describedby="finder-help finder-error" placeholder="例如：帮我整理学习工具项目，完善 README，准备发布到 GitHub。"></textarea><p id="finder-error" class="task-error" role="alert"></p><div class="finder-form-footer"><p id="finder-help">在本机按用途与文字匹配，不调用外部模型。</p><button type="submit" class="button button-primary">找适合的能力</button></div></form>
      <div class="finder-examples"><span>试一个任务</span><button type="button" data-finder-example="整理学习工具项目，完善 README，准备发布到 GitHub。">发布项目</button><button type="button" data-finder-example="检查网页的手机布局和键盘操作。">检查网页</button><button type="button" data-finder-example="调研项目管理工具市场，比较竞品与替代方案。">比较竞品</button></div>
      <p id="finder-result-status" class="finder-result-status" role="status" aria-live="polite"></p><div id="finder-results"></div>`;
    $('#finder-form').addEventListener('submit',e=>{e.preventDefault();run();});
    $('#finder-goal').addEventListener('input',()=>{
      // Invalidate old choices immediately when the task changes.
      clearResults();$('#finder-error').textContent='';$('#finder-goal').removeAttribute('aria-invalid');
    });
    $('#task-finder').addEventListener('click',e=>{
      if(e.target.closest('[data-finder-back]')){close();return;}
      const example=e.target.closest('[data-finder-example]');if(example){$('#finder-goal').value=example.dataset.finderExample;run();$('#finder-goal').focus();return;}
      if(e.target.closest('#finder-edit')){$('#finder-goal').focus();return;}
      const button=e.target.closest('[data-finder-choose]');if(!button)return;
      const c=candidates[Number(button.dataset.finderChoose)];if(!c||$('#finder-goal').value.trim()!==lastQuery)return;
      // Recheck against the live catalog to avoid launching a stale, removed item.
      const skill=options.skills().find(s=>s.id===c.skill.id&&s.is_present);if(!skill){run();return;}
      const scroll=window.scrollY;$('#task-finder').hidden=true;
      window.TaskWorkspace.open(skill,window.TaskBrief.guideFor(skill),options.title(skill),{
        goal:lastQuery,backLabel:'返回任务候选',onClose:()=>{show();window.scrollTo(0,scroll);button.focus({preventScroll:true});}
      });
    });
    rendered=true;
  }
  function open(query=''){
    libraryScroll=window.scrollY;if(!rendered)render();show();
    if(query.trim()){$('#finder-goal').value=query.slice(0,2000);run();}
    $('#finder-heading').focus({preventScroll:true});window.scrollTo(0,0);
  }
  window.TaskFinder={configure:config=>{options=config;},open};
})();
