(function(){
  'use strict';
  const S=window.SkillCenter,B=window.TaskBrief,E=S.esc,$=s=>document.querySelector(s);
  const memory=new Map(),prefix='skill-center:task-draft:v1:';
  let current=null,returnTo=null,roots=null,rootsRequest=null;
  const key=id=>prefix+encodeURIComponent(id);
  const fields=['goal','project','materials','deliverable','constraints'];
  function values(){return B.normalize(Object.fromEntries(fields.map(k=>[k,$('#task-'+k)?.value||''])));}
  function status(message,error=false){const n=$('#task-status');n.textContent=message;n.classList.toggle('task-error',error);}
  function update(){
    const v=values();memory.set(current.skill.id,v);
    const prompt=B.build(current.skill,v);$('#task-preview').value=prompt;
    $('#task-copy').disabled=!prompt;$('#task-download').disabled=!prompt;
    $('#task-preview-empty').hidden=Boolean(prompt);$('#task-preview').hidden=!prompt;
    $('#task-progress').textContent=prompt?'已按你的填写整理，可继续修改':'填写目标后，执行说明会显示在这里';
    $('#task-goal').removeAttribute('aria-invalid');$('#task-goal-error').textContent='';
  }
  function fill(v){for(const k of fields)$('#task-'+k).value=v[k]||'';update();}
  function readDraft(skill){
    try{
      const saved=JSON.parse(localStorage.getItem(key(skill.id))||'null');
      if(!saved||saved.schema!==1||saved.skillId!==skill.id||typeof saved.values!=='object')return null;
      return {...saved,values:B.normalize(saved.values)};
    }catch{return null;}
  }
  function remember(){if(current)memory.set(current.skill.id,values());}
  function close(){
    remember();$('#task-workspace').hidden=true;$('#library-view').hidden=false;
    $('#workspace-label').textContent='能力库';document.title='能力库 · Skill Center';
    if(!returnTo){
      if(matchMedia('(max-width:820px)').matches)$('#capability-detail').classList.add('mobile-open');
      window.scrollTo(0,current?.scroll||0);
      const button=document.querySelector('#start-task');button?.focus({preventScroll:true});
    }
    current=null;returnTo?.();
  }
  function renderProjects(){
    const list=$('#task-projects');if(!list||!current)return;
    list.innerHTML=(roots||[]).map(p=>`<option value="${E(p)}"></option>`).join('');
  }
  async function loadProjects(){
    if(roots){renderProjects();return;}
    if(!rootsRequest)rootsRequest=S.api('/api/project-roots').then(d=>{roots=(d.roots||[]).filter(p=>typeof p==='string');}).finally(()=>{rootsRequest=null;});
    try{await rootsRequest;renderProjects();}catch{if(current)$('#project-help').textContent='项目列表暂不可用，可以直接填写目录或项目名称。';}
  }
  function open(skill,guide,title,{example=false,onClose,goal='',backLabel='返回能力库'}={}){
    remember();returnTo=onClose;const existing=memory.get(skill.id),saved=readDraft(skill);
    const initial=existing||saved?.values||{goal:'',project:skill.project_root||'',materials:'',deliverable:guide.deliverable,constraints:''};
    const incoming=B.normalize({goal}).goal,conflict=Boolean(incoming&&initial.goal&&incoming!==initial.goal);
    if(incoming&&!initial.goal)initial.goal=incoming;
    current={skill,guide,title,incoming,scroll:window.scrollY};
    $('#library-view').hidden=true;$('#task-workspace').hidden=false;
    $('#workspace-label').textContent='准备任务';document.title='准备任务 · Skill Center';
    $('#task-workspace').innerHTML=`
      <div class="task-backline"><button type="button" id="task-back" class="task-back">${E(backLabel)}</button><span>填写目标，准备交给 Codex 的执行说明</span></div>
      <header class="task-heading"><div><h1 tabindex="-1" id="task-heading">准备任务</h1><p>使用 <strong>${E(title)}</strong> <code>$${E(skill.name)}</code></p></div><button type="button" class="button" id="task-save">保存草稿</button></header>
      <div id="task-status" class="task-status" role="status" aria-live="polite"></div>
      <section class="task-incoming" id="task-incoming" ${conflict?'':'hidden'} aria-label="刚才描述的新任务"><h2>已保留这项能力原来的草稿</h2><p>${E(incoming)}</p><button type="button" class="button" id="task-use-incoming">改用这个新目标</button><small>只替换目标，其他填写保留。请核对原材料与交付要求是否仍适用；保存草稿后才更新浏览器中的记录。</small></section>
      <div class="task-grid"><form id="task-form" class="task-form" novalidate>
        <label for="task-goal">这次要完成什么 <span>必填</span></label><textarea id="task-goal" rows="3" maxlength="2000" required aria-describedby="task-goal-error" placeholder="写下具体目标、对象和希望解决的问题"></textarea><p id="task-goal-error" class="task-error" role="alert"></p>
        <div class="task-example"><button type="button" id="task-example" class="text-action" aria-expanded="false" aria-controls="task-example-text task-use-example">查看示例任务</button><p id="task-example-text" hidden>${E(guide.example)}</p><button type="button" class="button button-small" id="task-use-example" hidden>填入示例目标</button></div>
        <label for="task-project">项目或工作目录 <span>选填</span></label><input id="task-project" list="task-projects" maxlength="1000" placeholder="选择已有项目，或填写项目名称与目录"><datalist id="task-projects"></datalist><p id="project-help" class="task-help">仅写入任务说明，执行时再确认工作目录。</p>
        <label for="task-materials">输入材料 <span>选填</span></label><textarea id="task-materials" rows="3" maxlength="8000" placeholder="填写文件路径、链接或材料说明；也可以稍后在 Codex 中补充"></textarea><p class="task-help">建议准备：${E(guide.inputs.join('；'))}。这里不上传或读取文件。</p>
        <label for="task-deliverable">希望交付什么 <span>选填</span></label><textarea id="task-deliverable" rows="3" maxlength="3000" placeholder="例如文件格式、需要完成的内容，以及怎样算完成"></textarea>
        <label for="task-constraints">补充要求 <span>选填</span></label><textarea id="task-constraints" rows="2" maxlength="3000" placeholder="例如目标平台、时长、风格、需要保留的内容"></textarea>
        <div class="task-form-footer"><button type="submit" class="button">检查任务说明</button><button type="button" id="task-clear" class="text-action">清空此任务</button></div>
        <p class="task-help">点击“保存草稿”后，内容才会保存在当前浏览器。返回列表会暂时保留本次填写。</p>
      </form><section class="task-preview-panel" aria-labelledby="task-preview-title">
        <h2 id="task-preview-title">执行说明</h2><p id="task-progress" class="task-help" role="status"></p>
        <div id="task-preview-empty" class="task-preview-empty"><strong>先写下一件具体的事</strong><p>我们会把目标、材料与交付要求整理成一份说明。</p></div>
        <label class="sr-only" for="task-preview">可复制的完整执行说明</label><textarea id="task-preview" readonly rows="18" hidden></textarea>
        <div class="task-preview-actions"><button type="button" class="button button-primary" id="task-copy" disabled>${S.icon('copy')} 复制执行说明</button><button type="button" class="button" id="task-download" disabled>下载 TXT</button></div>
        <p class="task-handoff">复制后粘贴到 Codex，补充材料并开始执行。此处只准备说明，尚未执行任务。</p>
      </section></div>`;
    fill(initial);renderProjects();loadProjects();
    if(example){
      // Do not silently overwrite an existing draft when choosing an example from the library.
      if(existing||saved){showExample();status('已保留原来的填写。示例已展开，需要时可填入目标。');}
      else{fill({...initial,goal:guide.example});status('已填入示例目标，请改成你这次的实际任务。');}
    }else if(existing){status('已恢复本次会话的填写内容。');}
    else if(saved){status(saved.version!==(skill.content_hash||skill.version_hash||'')?'已恢复浏览器草稿；Skill 索引版本已变化，请重新核对要求。':'已恢复当前浏览器保存的草稿。');}
    else if(incoming){status('已带入刚才的任务目标，可以继续补充材料与要求。');}
    $('#task-form').addEventListener('input',()=>{update();status('');});
    $('#task-form').addEventListener('submit',e=>{e.preventDefault();const error=B.validate(values());if(error){$('#task-goal-error').textContent=error;$('#task-goal').setAttribute('aria-invalid','true');$('#task-goal').focus();return;}status('执行说明已就绪。复制到 Codex 后可开始任务。');$('#task-preview').focus();});
    $('#task-heading').focus({preventScroll:true});window.scrollTo(0,0);
  }
  function showExample(){const open=$('#task-example-text').hidden;$('#task-example-text').hidden=!open;$('#task-use-example').hidden=!open;$('#task-example').setAttribute('aria-expanded',String(open));}
  $('#task-workspace').addEventListener('click',async e=>{
    if(!current)return;const button=e.target.closest('button');if(!button)return;
    if(button.id==='task-back'){close();return;}
    if(button.id==='task-example'){showExample();return;}
    if(button.id==='task-use-incoming'){fill({...values(),goal:current.incoming});$('#task-incoming').hidden=true;status('已替换目标，其他填写保留。请核对材料与交付要求是否适用于新任务。');$('#task-goal').focus();return;}
    if(button.id==='task-use-example'){fill({...values(),goal:current.guide.example});status('已填入示例目标，请修改成你的实际任务。');$('#task-goal').focus();return;}
    if(button.id==='task-clear'){
      let removed=true;try{localStorage.removeItem(key(current.skill.id));}catch{removed=false;}
      fill({});status(removed?'已清空填写和此能力保存的草稿。':'已清空本次填写；浏览器限制导致已存草稿未能删除。',!removed);$('#task-goal').focus();return;
    }
    if(button.id==='task-save'){
      try{localStorage.setItem(key(current.skill.id),JSON.stringify({schema:1,skillId:current.skill.id,version:current.skill.content_hash||current.skill.version_hash||'',savedAt:new Date().toISOString(),values:values()}));status('草稿已保存到当前浏览器，可在这项能力中继续填写。');}catch{status('浏览器无法保存草稿。当前填写仍在，可复制或下载执行说明。',true);}return;
    }
    if(button.id==='task-copy'){
      const prompt=B.build(current.skill,values());if(!prompt)return;
      try{await navigator.clipboard.writeText(prompt);if(current)status('已复制。到 Codex 粘贴这份说明并补充材料。');}
      catch{if(current){$('#task-preview').focus();$('#task-preview').select();status('自动复制未成功，已选中执行说明。按 Ctrl+C 或长按文本复制，也可下载 TXT。',true);}}return;
    }
    if(button.id==='task-download'){
      const prompt=B.build(current.skill,values());if(!prompt)return;
      const url=URL.createObjectURL(new Blob([prompt],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=current.skill.name.replace(/[^a-z0-9_-]/gi,'-')+'-task.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status('已请求下载执行说明，任务尚未执行。');
    }
  });
  window.TaskWorkspace={open};
})();
