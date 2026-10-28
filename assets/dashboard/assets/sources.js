(function(){
  "use strict";
  const S=window.SkillCenter;
  document.querySelector("#sidebar").innerHTML=S.nav("sources");

  const automaticLabels={
    personal:["个人 Skills","当前 Codex 的全局个人能力"],
    system:["系统 Skills","Codex 自带、只读的系统能力"],
    plugins:["插件缓存","已安装插件提供的公开能力"],
    agents_global:["Agents 兼容目录","兼容 ~/.agents/skills 标准位置"]
  };
  const state={config:null,sources:[],previewToken:"",savedConfig:null,savedSources:[],dirty:false};
  const clone=value=>JSON.parse(JSON.stringify(value));

  function setDirty(value){
    state.dirty=Boolean(value);
    document.querySelector("#dirty-banner").hidden=!state.dirty;
  }

  function invalidate(){
    state.previewToken="";
    setDirty(true);
    document.querySelector("#save").disabled=true;
    document.querySelector("#preview-result").innerHTML=`<div class="empty"><strong>配置有变化，请重新预览</strong><p>预览始终只读，不会修改索引或 Skill 文件。</p></div>`;
  }

  function statusBadge(source){
    const labels={ready:"可扫描",empty:"未发现 Skill",missing:"目录不存在",disabled:"已停用",error:"需要修正"};
    const kind=source.status==="ready"?"ready":source.status==="error"||source.status==="missing"?"update":"";
    return S.badge(labels[source.status]||source.status,kind);
  }

  function renderAutomatic(){
    const items=state.sources.filter(source=>!source.configurable);
    document.querySelector("#automatic-sources").innerHTML=items.map(source=>{
      const managed=source.managed_by==="environment";
      const [title,copy]=automaticLabels[source.key]||[
        source.label,
        managed?"由 SKILL_PROJECT_ROOTS 提供；网页只能查看，不能修改。":"标准扫描来源"
      ];
      return `<article class="source-card">
        <div class="source-card-head">
          <div><strong>${S.esc(title)}</strong><p>${S.esc(copy)}</p></div>
          ${managed?S.badge("环境变量管理","ready"):`<label class="toggle">
            <input type="checkbox" data-auto="${S.esc(source.key)}" ${state.config.automatic[source.key]?"checked":""}>
            <span>启用</span>
          </label>`}
        </div>
        <code class="source-path">${S.esc(source.path)}</code>
        <footer>${statusBadge(source)}<span>${source.found_count} 个候选</span></footer>
      </article>`;
    }).join("");
    document.querySelectorAll("[data-auto]").forEach(input=>input.addEventListener("change",event=>{
      state.config.automatic[event.target.dataset.auto]=event.target.checked;
      invalidate();
    }));
  }

  function projectStatus(source){
    return state.sources.find(item=>item.configurable&&item.id===source.id);
  }

  function renderProjects(){
    const host=document.querySelector("#project-sources");
    if(!state.config.project_sources.length){
      host.innerHTML=`<div class="empty"><strong>还没有项目来源</strong><p>其他人下载后会从这里配置自己的项目路径，不会继承你的本机路径。</p></div>`;
      return;
    }
    host.innerHTML=state.config.project_sources.map((source,index)=>{
      const status=projectStatus(source);
      return `<article class="project-source" data-project="${index}">
        <div class="project-source-index">${String(index+1).padStart(2,"0")}</div>
        <div class="project-source-fields">
          <label class="source-field"><span>显示名称</span><input class="field" type="text" value="${S.esc(source.label)}" data-field="label" maxlength="120"></label>
          <label class="source-field source-path-field"><span>绝对路径</span><input class="field" type="text" value="${S.esc(source.path)}" data-field="path" spellcheck="false" placeholder="D:\\projects\\my-skills"></label>
          <label class="source-field"><span>扫描模式</span><select class="field" data-field="mode"><option value="skill-container" ${source.mode==="skill-container"?"selected":""}>Skill 容器（直接子目录）</option><option value="single-skill" ${source.mode==="single-skill"?"selected":""}>单个 Skill（当前目录）</option></select></label>
          <label class="toggle project-toggle"><input type="checkbox" data-field="enabled" ${source.enabled?"checked":""}><span>启用</span></label>
        </div>
        <div class="project-source-meta">
          ${status?`${statusBadge(status)}<span>${status.found_count} 个候选</span>`:`${S.badge("待预览")}<span>尚未验证</span>`}
          <button class="button button-small button-danger" type="button" data-remove="${index}">移除</button>
        </div>
      </article>`;
    }).join("");
    host.querySelectorAll("[data-project]").forEach(card=>{
      const index=Number(card.dataset.project);
      card.querySelectorAll("[data-field]").forEach(field=>field.addEventListener("input",event=>{
        const key=event.target.dataset.field;
        state.config.project_sources[index][key]=key==="enabled"?event.target.checked:event.target.value;
        invalidate();
      }));
    });
    host.querySelectorAll("[data-remove]").forEach(button=>button.addEventListener("click",()=>{
      state.config.project_sources.splice(Number(button.dataset.remove),1);
      state.sources=state.sources.filter(source=>!source.configurable);
      renderProjects();
      invalidate();
    }));
  }

  function collectConfig(){
    const customIgnore=document.querySelector("#ignore-parts").value.split(/\r?\n/).map(value=>value.trim()).filter(Boolean);
    return {
      schema_version:2,
      automatic:{...state.config.automatic},
      project_sources:state.config.project_sources.map(source=>({...source})),
      custom_ignore_parts:customIgnore
    };
  }

  function renderPreview(result){
    const host=document.querySelector("#preview-result");
    const sourceRows=result.sources.map(source=>`
      <div class="preview-row">
        <div><strong>${S.esc(source.label)}</strong><code>${S.esc(source.mode)}</code></div>
        <div>${statusBadge(source)}<span>${source.found_count} 个候选</span></div>
        ${source.sample.length?`<p>${source.sample.map(name=>`<span>$${S.esc(name)}</span>`).join("")}</p>`:""}
        ${source.candidate_files?.length?`<details class="candidate-files"><summary>查看具体扫描的 ${source.candidate_files.length} 个 SKILL.md</summary><div>${source.candidate_files.map(item=>`<p><strong>$${S.esc(item.name)}</strong><code>${S.esc(item.skill_file)}</code></p>`).join("")}</div></details>`:""}
        ${source.warnings.length?`<ul>${source.warnings.map(message=>`<li>${S.esc(message)}</li>`).join("")}</ul>`:""}
      </div>`).join("");
    host.innerHTML=`<div class="preview-summary ${result.valid?"valid":"invalid"}"><div><span>去重后候选</span><strong>${result.total_candidates}</strong></div><div><span>配置状态</span><strong>${result.valid?"可以保存":"需要修正"}</strong></div><div><span>写入动作</span><strong>0</strong></div></div>
      ${result.errors.length?`<div class="source-errors" role="alert" tabindex="-1">${result.errors.map(error=>`<p>${S.esc(error)}</p>`).join("")}</div>`:""}
      <div class="preview-rows">${sourceRows}</div>`;
  }

  async function load(){
    try{
      const [overview,summary]=await Promise.all([S.api("/api/scan-sources"),S.api("/api/summary?scope=all")]);
      state.config=overview.config;
      state.sources=overview.sources;
      state.savedConfig=clone(overview.config);
      state.savedSources=clone(overview.sources);
      state.previewToken="";
      setDirty(false);
      S.setCounts(summary);
      document.querySelector("#config-state").textContent=overview.configured?"本机配置已建立":overview.legacy_config_detected?"发现旧配置，保存后自动迁移":"首次配置";
      document.querySelector("#config-path").textContent=overview.config_path;
      const defaults=state.config.ignore_parts.filter(value=>!state.config.custom_ignore_parts.includes(value));
      document.querySelector("#default-ignore-parts").innerHTML=defaults.map(value=>`<code>${S.esc(value)}</code>`).join("");
      document.querySelector("#ignore-parts").value=state.config.custom_ignore_parts.join("\n");
      renderAutomatic();
      renderProjects();
    }catch(error){
      document.querySelector("#automatic-sources").innerHTML=`<div class="error">${S.esc(error.message)}</div>`;
      S.toast(error.message,true);
    }
  }

  document.querySelector("#add-source").addEventListener("click",()=>{
    state.config.project_sources.push({id:"",label:"新项目来源",path:"",enabled:true,mode:"skill-container"});
    renderProjects();
    invalidate();
    document.querySelector("#project-sources article:last-child input[data-field='label']")?.focus();
  });
  document.querySelector("#ignore-parts").addEventListener("input",invalidate);
  document.querySelector("#revert").addEventListener("click",()=>{
    state.config=clone(state.savedConfig);
    state.sources=clone(state.savedSources);
    document.querySelector("#ignore-parts").value=state.config.custom_ignore_parts.join("\n");
    state.previewToken="";
    setDirty(false);
    document.querySelector("#save").disabled=true;
    renderAutomatic();
    renderProjects();
    document.querySelector("#preview-result").innerHTML=`<div class="empty"><strong>已撤销本次修改</strong><p>当前表单已恢复为上一次保存的配置。</p></div>`;
    S.toast("已恢复上一次保存的配置");
  });
  document.querySelector("#preview").addEventListener("click",async event=>{
    const button=event.currentTarget;
    button.disabled=true;
    button.textContent="正在验证…";
    try{
      const result=await S.api("/api/scan-sources/preview",{method:"POST",body:JSON.stringify({config:collectConfig()})});
      renderPreview(result);
      state.sources=result.sources;
      if(result.valid){
        state.config=result.config;
        state.previewToken=result.preview_token;
        document.querySelector("#save").disabled=false;
        renderAutomatic();
        renderProjects();
        S.toast(`预览完成：发现 ${result.total_candidates} 个 Skill 候选`);
      }else{
        state.previewToken="";
        document.querySelector("#save").disabled=true;
        S.toast("预览发现需要修正的来源",true);
        document.querySelector(".source-errors")?.focus?.();
      }
    }catch(error){
      S.toast(`预览失败：${error.message}`,true);
    }finally{
      button.disabled=false;
      button.textContent="预览扫描";
    }
  });
  document.querySelector("#save").addEventListener("click",async event=>{
    const button=event.currentTarget;
    button.disabled=true;
    button.textContent="正在保存并扫描…";
    try{
      const result=await S.api("/api/scan-sources",{method:"POST",body:JSON.stringify({config:collectConfig(),preview_token:state.previewToken,scan:true})});
      const scan=result.scan;
      const changes=Number(scan.added_count)+Number(scan.updated_count)+Number(scan.removed_count);
      S.toast(changes?`已保存，索引发现 ${changes} 项变化`:"已保存，Skills 索引没有变化");
      await load();
      button.textContent="保存并扫描";
      document.querySelector("#preview-result").innerHTML=`<div class="empty"><strong>配置已保存并完成更新</strong><p>本机路径只保存在运行目录；分享模板仍不包含任何绝对路径。</p></div>`;
    }catch(error){
      S.toast(`保存失败：${error.message}`,true);
      button.disabled=false;
      button.textContent="保存并扫描";
    }
  });
  document.querySelector("#download-template").addEventListener("click",async()=>{
    try{
      const result=await S.api("/api/scan-sources/template");
      const blob=new Blob([JSON.stringify(result.config,null,2)+"\n"],{type:"application/json"});
      const link=document.createElement("a");
      link.href=URL.createObjectURL(blob);
      link.download=result.filename;
      link.click();
      URL.revokeObjectURL(link.href);
      S.toast("已下载不含本机路径的分享模板");
    }catch(error){
      S.toast(`下载失败：${error.message}`,true);
    }
  });

  window.addEventListener("beforeunload",event=>{
    if(!state.dirty)return;
    event.preventDefault();
    event.returnValue="";
  });

  load();
})();
