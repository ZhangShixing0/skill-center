(function(){
  "use strict";
  const S=window.SkillCenter;
  document.querySelector("#sidebar").innerHTML=S.nav("public");

  const sourceMeta={
    verified:{
      label:"来源已验证",
      short:"可以打开经过核验的上游介绍"
    },
    candidate:{
      label:"来源待验证",
      short:"已有候选地址，核验前不跳转"
    },
    bundled:{
      label:"Codex 系统内置",
      short:"随 Codex 提供，没有单独上游地址"
    },
    missing:{
      label:"来源尚未找到",
      short:"当前元数据中没有可用地址"
    }
  };
  const storedLanguage=(()=>{
    try{return localStorage.getItem("skill-center-public-language")}
    catch{return ""}
  })();
  const state={
    skills:[],
    query:"",
    kind:"",
    source:"",
    category:"",
    language:storedLanguage==="en"?"en":"zh"
  };

  function sourceHost(value){
    try{return new URL(value).hostname.replace(/^www\./,"")}
    catch{return ""}
  }

  function displayName(skill){
    if(state.language==="en"){
      return skill.display_name_original||skill.display_name||skill.name;
    }
    return skill.display_name_zh||skill.display_name_original||skill.display_name||skill.name;
  }

  function description(skill){
    if(state.language==="en"){
      return skill.description_original||skill.description||"";
    }
    return skill.description_zh||skill.description_original||skill.description||"";
  }

  function searchText(skill){
    return [
      skill.name,
      skill.display_name,
      skill.display_name_original,
      skill.display_name_zh,
      skill.description,
      skill.description_original,
      skill.description_zh,
      skill.use_when_zh,
      skill.source_label,
      skill.source_status_label,
      skill.category
    ].filter(Boolean).join(" ").toLowerCase();
  }

  function filtered(){
    const query=state.query.trim().toLowerCase();
    return state.skills.filter(skill=>
      (!state.kind||skill.source_kind===state.kind)
      &&(!state.category||skill.category===state.category)
      &&(!state.source||skill.source_status===state.source)
      &&(!query||searchText(skill).includes(query))
    );
  }

  function localizationBadge(skill){
    if(state.language==="en"){
      return '<span class="badge language-badge">英文原文</span>';
    }
    if(!skill.localization_available){
      return '<span class="badge localization-missing">暂无中文</span>';
    }
    if(skill.localization_stale){
      return '<span class="badge localization-stale">中文待复核</span>';
    }
    return '<span class="badge localization-ready">中文整理版</span>';
  }

  function sourceFooter(skill){
    const status=skill.source_status||"missing";
    const meta=sourceMeta[status]||sourceMeta.missing;
    const host=sourceHost(skill.upstream_source||"");
    const detail=host
      ? `${host}${status==="candidate"?" · 候选地址":""}`
      : (skill.source_status_help||meta.short);
    const action=status==="verified"&&/^https?:\/\//.test(skill.upstream_source||"")
      ? `<a href="${S.esc(skill.upstream_source)}" target="_blank" rel="noopener noreferrer">打开上游介绍 ↗</a>`
      : `<span class="source-note">${status==="candidate"?"核验后开放链接":status==="bundled"?"随 Codex 更新":"等待补充"}</span>`;
    return `
      <footer>
        <div class="source-provenance">
          <span class="mini-label">来源线索</span>
          <strong>${S.esc(meta.label)}</strong>
          <small title="${S.esc(skill.source_status_help||meta.short)}">${S.esc(detail)}</small>
        </div>
        ${action}
      </footer>
    `;
  }

  function card(skill){
    const status=skill.source_status||"missing";
    const meta=sourceMeta[status]||sourceMeta.missing;
    const useWhen=state.language==="zh"&&skill.use_when_zh
      ? `<div class="public-use-when"><span>适合</span><p>${S.esc(skill.use_when_zh)}</p></div>`
      : "";
    return `
      <article class="public-card source-${S.esc(status)}">
        <header class="public-card-head">
          <div>${S.sourceBadge(skill)} ${skill.category?S.badge(skill.category):""} ${localizationBadge(skill)}</div>
          <span class="source-status source-${S.esc(status)}"><i aria-hidden="true"></i>${S.esc(meta.label)}</span>
        </header>
        <h3>${S.esc(displayName(skill))}</h3>
        <code>$${S.esc(skill.name)}</code>
        <p class="public-description">${S.esc(description(skill))}</p>
        ${useWhen}
        ${sourceFooter(skill)}
      </article>
    `;
  }

  function renderLegend(){
    const counts=new Map(Object.keys(sourceMeta).map(key=>[key,0]));
    state.skills.forEach(skill=>counts.set(skill.source_status,(counts.get(skill.source_status)||0)+1));
    document.querySelector("#source-legend-items").innerHTML=Object.entries(sourceMeta).map(([key,meta])=>`
      <button class="source-legend-item source-${key}" type="button" data-source-status="${key}" aria-pressed="${String(state.source===key)}">
        <span><i aria-hidden="true"></i>${S.esc(meta.label)}</span>
        <strong>${counts.get(key)||0}</strong>
        <small>${S.esc(meta.short)}</small>
      </button>
    `).join("");
    document.querySelectorAll("[data-source-status]").forEach(button=>{
      button.addEventListener("click",()=>{
        state.source=state.source===button.dataset.sourceStatus?"":button.dataset.sourceStatus;
        document.querySelector("#source-filter").value=state.source;
        render();
      });
    });
  }

  function renderLanguage(){
    document.querySelectorAll("[data-language]").forEach(button=>{
      const active=button.dataset.language===state.language;
      button.setAttribute("aria-pressed",String(active));
      button.classList.toggle("button-ghost",!active);
    });
    document.documentElement.lang=state.language==="zh"?"zh-CN":"en";
  }

  function render(){
    const items=filtered();
    const verified=items.filter(skill=>skill.source_status==="verified").length;
    const localized=items.filter(skill=>skill.localization_available).length;
    document.querySelector("#result-copy").textContent=
      `显示 ${items.length} 个公开 Skill · 中文 ${localized} 个 · 已验证来源 ${verified} 个`;
    document.querySelector("#skills").innerHTML=items.length
      ? items.map(card).join("")
      : S.empty("没有匹配的公开 Skill","换一个中英文关键词，或清除类型、来源与分类筛选。");
    renderLegend();
    renderLanguage();
  }

  function renderCategories(){
    const counts=new Map();
    state.skills.forEach(skill=>{
      const category=skill.category||"其他";
      counts.set(category,(counts.get(category)||0)+1);
    });
    const buttons=[
      ["",`全部 ${state.skills.length}`],
      ...[...counts.entries()]
        .sort((a,b)=>b[1]-a[1])
        .map(([name,count])=>[name,`${name} ${count}`])
    ];
    document.querySelector("#categories").innerHTML=buttons.map(([value,label])=>
      `<button class="chip" type="button" data-category="${S.esc(value)}" aria-pressed="${String(value===state.category)}">${S.esc(label)}</button>`
    ).join("");
    document.querySelectorAll("[data-category]").forEach(button=>{
      button.addEventListener("click",()=>{
        state.category=button.dataset.category;
        renderCategories();
        render();
      });
    });
  }

  async function load(){
    document.querySelector("#skills").innerHTML=S.skeletons(6);
    try{
      const [summary,payload]=await Promise.all([
        S.api("/api/summary?scope=public"),
        S.api("/api/skills?scope=public&sort=name")
      ]);
      state.skills=payload.skills;
      S.setCounts(summary);
      document.querySelector("#stat-total").textContent=payload.skills.length;
      document.querySelector("#stat-localized").textContent=payload.skills.filter(skill=>skill.localization_available).length;
      document.querySelector("#stat-verified").textContent=payload.skills.filter(skill=>skill.source_status==="verified").length;
      document.querySelector("#stat-candidate").textContent=payload.skills.filter(skill=>skill.source_status==="candidate").length;
      renderCategories();
      render();
    }catch(error){
      document.querySelector("#skills").innerHTML=`<div class="error">${S.esc(error.message)}</div>`;
      S.toast(error.message,true);
    }
  }

  document.querySelector("#search").addEventListener("input",event=>{
    state.query=event.target.value;
    render();
  });
  document.querySelector("#kind").addEventListener("change",event=>{
    state.kind=event.target.value;
    render();
  });
  document.querySelector("#source-filter").addEventListener("change",event=>{
    state.source=event.target.value;
    render();
  });
  document.querySelectorAll("[data-language]").forEach(button=>{
    button.addEventListener("click",()=>{
      state.language=button.dataset.language==="en"?"en":"zh";
      try{localStorage.setItem("skill-center-public-language",state.language)}
      catch{}
      render();
    });
  });
  document.querySelector("#scan").addEventListener("click",async event=>{
    const button=event.currentTarget;
    button.disabled=true;
    button.textContent="扫描中…";
    try{
      await S.api("/api/scan",{method:"POST",body:"{}"});
      S.toast("公开来源索引与中文状态已更新");
      await load();
    }catch(error){
      S.toast(error.message,true);
    }finally{
      button.disabled=false;
      button.textContent="重新扫描";
    }
  });

  load();
})();
