(function(){
  "use strict";
  const S=window.SkillCenter;
  document.querySelector("#sidebar").innerHTML=S.nav("insights");

  function ratio(value){
    return `${Math.round(Number(value||0)*100)}%`;
  }

  function skillRows(items,emptyTitle,limit=6){
    if(!items?.length)return S.empty(emptyTitle);
    const visible=items.slice(0,limit);
    return `<div class="insight-skill-list">${visible.map(item=>`
      <a href="skill.html?id=${encodeURIComponent(item.name)}">
        <span><strong>${S.esc(item.display_name)}</strong><code>$${S.esc(item.name)}</code></span>
        <small>${item.uses_30} 次 / 30 天${item.average_rating==null?"":` · ${Number(item.average_rating).toFixed(1)}/5`}</small>
      </a>
    `).join("")}</div>${items.length>visible.length?`<p class="data-footnote">还有 ${items.length-visible.length} 个，前往“开始使用”查看完整列表。</p>`:""}`;
  }

  function distribution(items,labelKey,valueKey,emptyCopy){
    if(!items?.length)return S.empty(emptyCopy);
    const max=Math.max(...items.map(item=>Number(item[valueKey]||0)),1);
    return `<div class="distribution-list">${items.map(item=>`
      <div class="distribution-row">
        <div><strong>${S.esc(item[labelKey])}</strong><span>${item[valueKey]}</span></div>
        <div class="distribution-track" aria-hidden="true"><i style="width:${Math.max(4,Number(item[valueKey]||0)/max*100)}%"></i></div>
      </div>
    `).join("")}</div>`;
  }

  function renderTrend(trend){
    const max=Math.max(...trend.map(item=>item.count),1);
    const total=trend.reduce((sum,item)=>sum+item.count,0);
    const peak=trend.reduce((best,item)=>item.count>best.count?item:best,trend[0]||{day:"",count:0});
    const chart=document.querySelector("#trend-chart");
    chart.classList.toggle("is-empty",total===0);
    chart.setAttribute("aria-label",total?`近 30 天共记录 ${total} 次调用；峰值为 ${peak.day} 的 ${peak.count} 次`:"近 30 天暂无已记录调用；日志仅部分覆盖，不代表没有实际使用。");
    chart.innerHTML=total?trend.map((item,index)=>`
      <div class="trend-bar" title="${S.esc(item.day)}：${item.count} 次">
        <i style="height:${item.count/max*100}%"></i>
        ${index%5===0||index===trend.length-1?`<span>${S.esc(item.day.slice(5))}</span>`:""}
      </div>
    `).join(""):'<div class="trend-empty"><strong>近 30 天暂无已记录调用</strong><p>日志仅部分覆盖，不代表没有实际使用。</p></div>';
    document.querySelector("#trend-table").innerHTML=`<table><thead><tr><th>日期</th><th>已记录调用</th></tr></thead><tbody>${trend.map(item=>`<tr><td>${S.esc(item.day)}</td><td>${item.count}</td></tr>`).join("")}</tbody></table>`;
  }

  function renderOutcomes(outcomes){
    const sample=outcomes.sample_size;
    document.querySelector("#outcome-copy").textContent=sample?`基于 ${sample} 条已关联结果反馈`:"还没有足够的结果反馈";
    if(!sample){
      document.querySelector("#outcome-breakdown").innerHTML=S.empty("尚无结果样本","在 Skill 详情页为一次具体调用记录感受后，这里才会计算。");
      return;
    }
    const definitions=[
      ["solved","已解决",outcomes.solved],
      ["partial","部分解决",outcomes.partial],
      ["failed","未解决",outcomes.failed]
    ];
    document.querySelector("#outcome-breakdown").innerHTML=`
      <div class="outcome-stack" aria-label="结果反馈分布">
        ${definitions.map(([kind,label,value])=>`<div class="${kind}" style="width:${value/sample*100}%" title="${label} ${value} 条"><span>${label} ${value}</span></div>`).join("")}
      </div>
      <div class="outcome-legend">${definitions.map(([kind,label,value])=>`<div><i class="${kind}"></i><span>${label}</span><strong>${value}</strong></div>`).join("")}</div>
      <p class="data-footnote">样本少时不显示“成功率”结论，只展示真实条数。</p>
    `;
  }

  function renderCoUse(run){
    const node=document.querySelector("#co-use-insights");
    if(!run.co_use.length){
      node.innerHTML=S.empty("暂无可靠组合数据","新的日志可以携带同一运行编号；积累至少一次多 Skill 运行后，这里才会出现顺序关系。");
      return;
    }
    node.innerHTML=`<div class="co-use-list">${run.co_use.map(edge=>`
      <article class="co-use-row">
        <a href="skill.html?id=${encodeURIComponent(edge.from_skill)}">${S.esc(edge.from_display)}</a>
        <span>→</span>
        <a href="skill.html?id=${encodeURIComponent(edge.to_skill)}">${S.esc(edge.to_display)}</a>
        <strong>${edge.run_count} 次</strong>
        <small>${S.esc(edge.evidence)}</small>
      </article>
    `).join("")}</div><p class="data-footnote">${S.esc(run.detail)}</p>`;
  }

  function renderInventory(inventory){
    const items=[
      ["当前全部",inventory.total_skills,"当前扫描到的主位置"],
      ["我的已确认",inventory.my_skills,"原创、改造与项目孵化"],
      ["待认领",inventory.inbox_skills,"安装位置不代表作者身份"],
      ["公开 Skills",inventory.public_skills,"系统、插件和公开安装"],
      ["已移除历史",inventory.removed_skills,"不进入当前库"],
      ["重复位置",inventory.duplicate_locations,"保留来源图，不重复计 Skill"],
      ["项目可更新",inventory.updates_available,"需要单独 diff 与批准"],
      ["待审提案",inventory.pending_proposals,"不会自动改 Skill 文件"]
    ];
    document.querySelector("#inventory-grid").innerHTML=items.map(([label,value,copy])=>`<article><span>${S.esc(label)}</span><strong>${value}</strong><small>${S.esc(copy)}</small></article>`).join("");
  }

  async function load(){
    try{
      const [summary,data]=await Promise.all([
        S.api("/api/summary"),
        S.api("/api/insights?scope=my")
      ]);
      S.setCounts(summary);
      document.querySelector("#coverage-banner").innerHTML=`
        <div><h2>${data.tracked_skills}/${data.eligible_skills} 个 Skill 有历史日志</h2><p>${S.esc(data.coverage.detail)}</p></div>
        <div class="coverage-meter"><span><i style="width:${ratio(data.coverage.skill_ratio)}"></i></span><strong>${ratio(data.coverage.skill_ratio)} Skill 覆盖</strong><small>${ratio(data.coverage.run_event_ratio)} 的近 30 天事件带运行编号</small></div>
      `;
      document.querySelector("#kpi-events").textContent=data.recorded_events;
      document.querySelector("#kpi-days").textContent=data.active_days;
      document.querySelector("#kpi-skills").textContent=data.tracked_skills;
      document.querySelector("#kpi-skill-copy").textContent=`共 ${data.eligible_skills} 个当前 Skill`;
      document.querySelector("#kpi-runs").textContent=data.run_tracking.multi_skill_runs;
      document.querySelector("#kpi-feedback").textContent=data.outcomes.sample_size;
      renderTrend(data.trend);
      renderOutcomes(data.outcomes);
      document.querySelector("#attention-friction").innerHTML=skillRows(data.attention.high_use_low_satisfaction,"目前没有已记录的高使用体验问题");
      document.querySelector("#attention-reliable").innerHTML=skillRows(data.attention.reliable,"反馈样本还不足以确认稳定 Skill");
      document.querySelector("#attention-untried").innerHTML=skillRows(data.attention.untried,"所有当前 Skill 都已有调用记录");
      document.querySelector("#project-breakdown").innerHTML=distribution(data.projects,"label","event_count","近 30 天没有已记录项目调用");
      document.querySelector("#category-breakdown").innerHTML=distribution(data.categories,"name","count","近 30 天没有已记录任务分类");
      renderCoUse(data.run_tracking);
      renderInventory(data.inventory);
    }catch(error){
      document.querySelector("#coverage-banner").innerHTML=`<div class="error">${S.esc(error.message)}</div>`;
      S.toast(error.message,true);
    }
  }
  load();
})();
