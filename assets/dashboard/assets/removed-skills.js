(function(){
  "use strict";
  const S=window.SkillCenter;
  document.querySelector("#sidebar").innerHTML=S.nav("removed");
  const state={skills:[],query:"",source:""};

  const knownDate=(value,fallback="未记录")=>value?S.dateTime(value):fallback;

  function filtered(){
    const query=state.query.trim().toLowerCase();
    return state.skills.filter(skill=>(
      (!state.source||skill.source_kind===state.source)&&
      (!query||`${skill.name} ${skill.display_name} ${skill.description} ${skill.source_label}`.toLowerCase().includes(query))
    ));
  }

  function render(){
    const items=filtered();
    document.querySelector("#removed-copy").textContent=`显示 ${items.length} 条已移除历史；它们不属于当前可用 Skills`;
    document.querySelector("#removed-list").innerHTML=items.length?items.map(skill=>`
      <a class="removed-card" href="skill.html?id=${encodeURIComponent(skill.name)}">
        <div class="removed-card-main">
          <div>${S.badge("已移除","removed")} ${S.sourceBadge(skill)}</div>
          <strong>${S.esc(skill.display_name)}</strong>
          <code>$${S.esc(skill.name)}</code>
          <p>${S.esc(skill.description||"未保留介绍")}</p>
        </div>
        <div><span class="mini-label">平台首次发现</span><span class="mini-value">${S.esc(knownDate(skill.discovered_at))}</span></div>
        <div><span class="mini-label">确认移除</span><span class="mini-value">${S.esc(knownDate(skill.removed_at))}</span></div>
        <div><span class="mini-label">最近已记录调用</span><span class="mini-value">${S.esc(skill.last_used?S.date(skill.last_used):"无记录")}</span></div>
        <div><span class="mini-label">最近项目</span><span class="mini-value">${S.esc(skill.last_workspace_label||"未关联项目")}</span></div>
        <span class="arrow" aria-hidden="true">→</span>
      </a>
    `).join(""):S.empty("没有已移除记录","当前库存与磁盘中的 Skill 文件一致。")
  }

  async function load(){
    document.querySelector("#removed-list").innerHTML=S.skeletons(4);
    try{
      const [summary,payload]=await Promise.all([
        S.api("/api/summary"),
        S.api("/api/skills?presence=removed&sort=removed")
      ]);
      state.skills=payload.skills;
      S.setCounts(summary);
      const used=state.skills.filter(skill=>skill.uses_all>0);
      const projects=new Set(state.skills.map(skill=>skill.last_workspace_label).filter(Boolean));
      document.querySelector("#removed-total").textContent=state.skills.length;
      document.querySelector("#removed-used").textContent=used.length;
      document.querySelector("#removed-projects").textContent=projects.size;
      document.querySelector("#removed-latest").textContent=state.skills[0]?.removed_at?S.date(state.skills[0].removed_at):"未记录";
      render();
    }catch(error){
      document.querySelector("#removed-list").innerHTML=`<div class="error">${S.esc(error.message)}</div>`;
      S.toast(error.message,true);
    }
  }

  document.querySelector("#removed-search").addEventListener("input",event=>{state.query=event.target.value;render()});
  document.querySelector("#removed-source").addEventListener("change",event=>{state.source=event.target.value;render()});
  load();
})();
