(function(){
  "use strict";
  const S=window.SkillCenter;
  document.querySelector("#sidebar").innerHTML=S.nav("workflows");
  const state={workflows:[],insights:null,query:"",status:""};

  function skillLink(step){
    return step.available
      ?`<a href="skill.html?id=${encodeURIComponent(step.skill)}"><strong>${S.esc(step.display_name)}</strong><code>$${S.esc(step.skill)}</code></a>`
      :`<div><strong>${S.esc(step.display_name)}</strong><code>$${S.esc(step.skill)}</code></div>`;
  }

  function workflowCard(workflow){
    const prompt=workflow.copy_prompt||`请依次使用：${workflow.steps.map(step=>`$${step.skill}`).join(" → ")}`;
    return `
      <article class="workflow-card" id="${S.esc(workflow.id)}">
        <header>
          <div>
            <span class="badge ${workflow.ready?"ready":"update"}">${workflow.ready?"当前可完整执行":"仍缺少步骤"}</span>
            <span class="badge">${S.esc(workflow.source_label)}</span>
          </div>
          <span class="workflow-availability">${workflow.available_count}/${workflow.step_count}</span>
        </header>
        <h3>${S.esc(workflow.title)}</h3>
        <p>${S.esc(workflow.description)}</p>
        <div class="workflow-purpose"><span>适合</span><strong>${S.esc(workflow.best_for||"按既定顺序完成多步交付")}</strong></div>
        <ol class="pipeline-steps">
          ${workflow.steps.map(step=>`
            <li class="${step.available?"available":"missing"}">
              <span class="step-index">${String(step.position).padStart(2,"0")}</span>
              <div class="pipeline-step-copy">
                ${skillLink(step)}
                <p>${S.esc(step.role||"完成该阶段交付")}</p>
                <small>${step.available?"当前已安装":"当前未发现"}${step.optional?" · 可选步骤":""}</small>
              </div>
            </li>
          `).join("")}
        </ol>
        <footer>
          <div>
            <span>模板记录</span>
            <strong>${workflow.multi_skill_runs?`已观察 ${workflow.multi_skill_runs} 次多 Skill 运行`:"尚无可靠共同运行记录"}</strong>
          </div>
          <button class="button button-primary" type="button" data-copy-workflow="${S.esc(prompt)}">复制整条工作流用法</button>
        </footer>
      </article>
    `;
  }

  function renderWorkflows(){
    const query=state.query.trim().toLowerCase();
    const items=state.workflows.filter(workflow=>{
      const matchStatus=!state.status||(state.status==="ready"?workflow.ready:!workflow.ready);
      const haystack=`${workflow.title} ${workflow.description} ${workflow.best_for} ${workflow.steps.map(step=>`${step.skill} ${step.role}`).join(" ")}`.toLowerCase();
      return matchStatus&&(!query||haystack.includes(query));
    });
    document.querySelector("#workflow-list").innerHTML=items.length
      ?items.map(workflowCard).join("")
      :S.empty("没有匹配的工作流","换一个目标词，或查看全部状态。");
    document.querySelectorAll("[data-copy-workflow]").forEach(button=>button.addEventListener("click",()=>S.copy(button.dataset.copyWorkflow)));
    const hash=decodeURIComponent(location.hash.slice(1));
    if(hash){
      const target=document.getElementById(hash);
      if(target){
        target.classList.add("workflow-highlight");
        requestAnimationFrame(()=>target.scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"start"}));
      }
    }
  }

  function renderObserved(){
    const run=state.insights.run_tracking;
    document.querySelector("#workflow-observed").textContent=run.multi_skill_runs;
    const node=document.querySelector("#observed-list");
    if(!run.co_use.length){
      node.innerHTML=S.empty(
        "还没有可靠的共同运行记录",
        "后续在同一任务中为多个 Skill 写入相同运行编号后，这里才会出现组合频率。现有历史不会被猜测补齐。"
      );
      return;
    }
    node.innerHTML=`
      <div class="co-use-list">${run.co_use.map(edge=>`
        <article class="co-use-row">
          <a href="skill.html?id=${encodeURIComponent(edge.from_skill)}">${S.esc(edge.from_display)}</a>
          <span aria-label="流向">→</span>
          <a href="skill.html?id=${encodeURIComponent(edge.to_skill)}">${S.esc(edge.to_display)}</a>
          <strong>${edge.run_count} 次共同运行</strong>
          <small>${S.esc(edge.evidence)}</small>
        </article>
      `).join("")}</div>
      <p class="data-footnote">${S.esc(run.detail)}</p>
    `;
  }

  async function load(){
    try{
      const [summary,workflows,insights]=await Promise.all([
        S.api("/api/summary"),
        S.api("/api/workflows"),
        S.api("/api/insights?scope=my")
      ]);
      S.setCounts(summary);
      state.workflows=workflows.workflows||[];
      state.insights=insights;
      document.querySelector("#workflow-total").textContent=state.workflows.length;
      document.querySelector("#workflow-ready").textContent=state.workflows.filter(item=>item.ready).length;
      renderWorkflows();
      renderObserved();
    }catch(error){
      document.querySelector("#workflow-list").innerHTML=`<div class="error">${S.esc(error.message)}</div>`;
      document.querySelector("#observed-list").innerHTML=`<div class="error">${S.esc(error.message)}</div>`;
      S.toast(error.message,true);
    }
  }

  document.querySelector("#workflow-search").addEventListener("input",event=>{state.query=event.target.value;renderWorkflows()});
  document.querySelector("#workflow-status").addEventListener("change",event=>{state.status=event.target.value;renderWorkflows()});
  load();
})();
