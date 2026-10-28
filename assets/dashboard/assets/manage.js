(function(){
  "use strict";
  const S=window.SkillCenter;
  document.querySelector("#sidebar").innerHTML=S.nav("manage");

  const state={
    skills:[],workflows:[],query:"",goalQuery:"",source:"",category:"",identity:"",sort:"usage30",
    review:null,reviewOpen:false,reviewPreviewToken:""
  };
  const featuredOrder=["cinematic-brand-html","editorial-brand-html","living-data-story-html","spatial-character-exhibit-html"];
  const featuredMeta={
    "cinematic-brand-html":{theme:"cinematic",no:"01",label:"Scroll as editing",copy:"把品牌观点变成一幕幕推进的场景：滚动即剪辑，克制 HUD 只负责方向。"},
    "editorial-brand-html":{theme:"editorial",no:"02",label:"Evidence-led issue",copy:"用暖纸、墨黑、一个强调色，把结论、证据与当前决定编成品牌特刊。"},
    "living-data-story-html":{theme:"living",no:"03",label:"Behavior becomes proof",copy:"让真实行为记录成为会呼吸、会累积、能证明变化的数据生命体。"},
    "spatial-character-exhibit-html":{theme:"spatial",no:"04",label:"Object as exhibit",copy:"把角色产品放进展柜、光影和触碰仪式里，像一件值得靠近的空间展品。"}
  };
  const classificationLabels={
    "self-authored":"我的原创",
    "public-installed":"公开安装",
    "adapted":"自定义改造"
  };
  const confidenceLabels={high:"高置信度",medium:"需要复核",low:"线索不足"};

  const url=skill=>`skill.html?id=${encodeURIComponent(skill.name)}`;
  const identityOf=skill=>skill.source_kind==="project"?"project":skill.classification;
  const scanCount=(scan,key)=>Number(scan?.[`${key}_count`]??scan?.delta?.[key]?.length??0);

  function goalSkillMatches(query){
    const normalized=query.trim().toLowerCase();
    const items=normalized
      ?state.skills.filter(skill=>`${skill.name} ${skill.display_name} ${skill.description} ${skill.category}`.toLowerCase().includes(normalized))
      :[...state.skills].sort((a,b)=>b.uses_30-a.uses_30||(b.last_used||"").localeCompare(a.last_used||""));
    return items.slice(0,4);
  }

  function goalWorkflowMatches(query){
    const normalized=query.trim().toLowerCase();
    return state.workflows.filter(workflow=>{
      const haystack=`${workflow.title} ${workflow.description} ${workflow.best_for} ${workflow.steps.map(step=>`${step.skill} ${step.role}`).join(" ")}`.toLowerCase();
      return !normalized||haystack.includes(normalized);
    }).slice(0,2);
  }

  function renderGoalResults(){
    const query=state.goalQuery.trim();
    const skills=goalSkillMatches(query);
    const workflows=goalWorkflowMatches(query);
    const heading=query?`找到 ${skills.length} 个 Skill、${workflows.length} 条工作流`:"根据已记录使用和当前可用性，可以从这里开始";
    const skillHtml=skills.map(skill=>`
      <a class="goal-result" href="${url(skill)}">
        <span>${S.esc(skill.category||"其他")}</span>
        <strong>${S.esc(skill.display_name)}</strong>
        <p>${S.esc(skill.description)}</p>
        <small>${skill.uses_30?`近 30 天已记录 ${skill.uses_30} 次`:"尚无已记录调用"}</small>
      </a>
    `).join("");
    const workflowHtml=workflows.map(workflow=>`
      <a class="goal-result workflow-result" href="workflows.html#${S.esc(workflow.id)}">
        <span>${workflow.source_label}</span>
        <strong>${S.esc(workflow.title)}</strong>
        <p>${S.esc(workflow.best_for||workflow.description)}</p>
        <small>${workflow.available_count}/${workflow.step_count} 个步骤当前可用</small>
      </a>
    `).join("");
    document.querySelector("#goal-results").innerHTML=`
      <p class="goal-result-copy">${S.esc(heading)}</p>
      <div class="goal-result-grid">${skillHtml}${workflowHtml}</div>
      ${!skills.length&&!workflows.length?S.empty("暂时没有直接匹配","可以换成任务类型、交付物或问题描述搜索。"):""}
    `;
  }

  function renderResume(){
    const skill=[...state.skills].filter(item=>item.last_used).sort((a,b)=>b.last_used.localeCompare(a.last_used))[0];
    const node=document.querySelector("#resume-card");
    if(!skill){
      node.innerHTML=`

        <h2>还没有可继续的记录</h2>
        <p>开始记录调用后，这里会显示最近使用的 Skill 和项目别名。</p>
        <a class="button button-ghost" href="#all-title">浏览当前能力</a>
      `;
      return;
    }
    node.innerHTML=`

      <h2>继续 ${S.esc(skill.display_name)}</h2>
      <p>${S.esc(skill.last_workspace_label||"未关联项目")} · ${S.date(skill.last_used)}</p>
      <div class="resume-meta"><span>近 30 天 ${skill.uses_30} 次</span><span>${skill.average_rating==null?"尚无评分":`${Number(skill.average_rating).toFixed(1)} / 5`}</span></div>
      <a class="button button-primary" href="${url(skill)}">打开用法与最近记录</a>
    `;
  }

  function renderWorkflowShortcuts(){
    const workflows=[...state.workflows]
      .sort((a,b)=>Number(b.ready)-Number(a.ready)||b.available_count-a.available_count)
      .slice(0,3);
    document.querySelector("#workflow-shortcuts").innerHTML=workflows.length?workflows.map(workflow=>`
      <a class="workflow-shortcut" href="workflows.html#${S.esc(workflow.id)}">
        <div><strong>${S.esc(workflow.title)}</strong><span>${S.esc(workflow.source_label)}</span></div>
        <small>${workflow.available_count}/${workflow.step_count} 步可用${workflow.multi_skill_runs?` · 已观察 ${workflow.multi_skill_runs} 次共同运行`:""}</small>
      </a>
    `).join(""):S.empty("还没有工作流模板","可以先从单个 Skill 详情开始。");
  }

  function formatScanTime(value){
    if(!value)return "尚未执行更新";
    const date=new Date(value);
    if(Number.isNaN(date.getTime()))return value;
    return new Intl.DateTimeFormat("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit"}).format(date);
  }

  function lifecycleDate(value){
    return value?S.date(value):"未记录";
  }

  function renderUpdate(scan){
    const panel=document.querySelector("#update-panel");
    if(!scan){panel.hidden=true;return}
    panel.hidden=false;
    const added=scanCount(scan,"added");
    const changed=scanCount(scan,"updated");
    const removed=scanCount(scan,"removed");
    const total=Number(scan.total_locations??scan.scanned??0);
    const changeTotal=added+changed+removed;
    document.querySelector("#update-title").textContent=changeTotal?`发现 ${changeTotal} 项来源变化`:"上次扫描未发现变化";
    document.querySelector("#update-time").textContent=`扫描时间：${formatScanTime(scan.scanned_at)}`;
    document.querySelector("#update-added").textContent=added;
    document.querySelector("#update-changed").textContent=changed;
    document.querySelector("#update-removed").textContent=removed;
    document.querySelector("#update-total").textContent=total;
    document.querySelector("#update-state").textContent=changeTotal?"已完成差异更新":"没有发现变化";

    const groups=[
      ["added","新增",scan.delta?.added||[]],
      ["updated","内容更新",scan.delta?.updated||[]],
      ["removed","已移除位置",scan.delta?.removed||[]]
    ].filter(([, ,items])=>items.length);
    document.querySelector("#update-details").innerHTML=groups.length?groups.map(([kind,label,items])=>{
      const visible=items.slice(0,12);
      const rest=items.length-visible.length;
      return `<div class="update-group ${kind}"><strong>${S.esc(label)} · ${items.length}</strong><div class="update-tags">${visible.map(item=>`<span><b>${S.esc(item.display_name||item.name)}</b><code>$${S.esc(item.name)}</code></span>`).join("")}${rest?`<span><b>还有 ${rest} 个</b></span>`:""}</div></div>`;
    }).join(""):`<p class="update-empty">本次没有发现新增、内容更新或已移除位置。</p>`;
  }

  function renderFeatured(){
    const items=featuredOrder.map(name=>state.skills.find(skill=>skill.name===name)).filter(Boolean);
    document.querySelector("#featured").innerHTML=items.length?items.map(skill=>{
      const meta=featuredMeta[skill.name];
      return `<a class="feature ${meta.theme}" href="${url(skill)}"><div class="feature-top"><span>${S.esc(meta.label)}</span><span class="feature-no">${meta.no}</span></div><div><h3>${S.esc(skill.display_name)}</h3><p>${S.esc(meta.copy)}</p><div class="technical">$${S.esc(skill.name)}</div></div><span class="feature-arrow" aria-hidden="true">→</span></a>`;
    }).join(""):S.empty("暂未发现四个网页展示 Skill","请确认它们位于全局或已配置的项目 Skill 目录。");
  }

  function sortItems(items){
    const copy=[...items];
    const methods={
      usage30:(a,b)=>b.uses_30-a.uses_30||a.display_name.localeCompare(b.display_name,"zh-CN"),
      priority:(a,b)=>b.improvement_priority-a.improvement_priority||b.uses_30-a.uses_30,
      recent:(a,b)=>(b.last_used||"").localeCompare(a.last_used||""),
      name:(a,b)=>a.display_name.localeCompare(b.display_name,"zh-CN")
    };
    return copy.sort(methods[state.sort]||methods.usage30);
  }

  function filtered(){
    const query=state.query.trim().toLowerCase();
    return sortItems(state.skills.filter(skill=>
      (!state.source||skill.source_kind===state.source)&&
      (!state.category||skill.category===state.category)&&
      (!state.identity||identityOf(skill)===state.identity)&&
      (!query||`${skill.name} ${skill.display_name} ${skill.description} ${skill.category}`.toLowerCase().includes(query))
    ));
  }

  function renderList(){
    const items=filtered();
    document.querySelector("#result-copy").textContent=`显示 ${items.length} 个已确认且当前存在的 Skill；调用和项目仅来自已写入的本地日志`;
    document.querySelector("#skills").innerHTML=items.length?items.map(skill=>`
      <a class="skill-card" href="${url(skill)}">
        <div class="skill-name">
          <div>${S.sourceBadge(skill)} ${S.syncBadge(skill)} ${skill.duplicate_count?S.badge(`${skill.duplicate_count+1} 个位置`):""}</div>
          <strong>${S.esc(skill.display_name)}</strong>
          <code>$${S.esc(skill.name)}</code>
          <p>${S.esc(skill.description)}</p>
          <span class="skill-first-seen">平台首次发现：${S.esc(lifecycleDate(skill.discovered_at))}</span>
        </div>
        <div><span class="mini-label">近 30 天已记录</span><span class="mini-value">${skill.uses_30} 次</span></div>
        <div><span class="mini-label">最近记录</span><span class="mini-value">${S.date(skill.last_used)}</span></div>
        <div><span class="mini-label">最近项目</span><span class="mini-value">${S.esc(skill.last_workspace_label||"未关联项目")}</span></div>
        <div class="card-end">${skill.average_rating!=null?S.badge(`${Number(skill.average_rating).toFixed(1)} / 5`):""}<span class="arrow" aria-hidden="true">→</span></div>
      </a>`).join(""):S.empty("没有匹配的 Skill","换一个关键词或清除筛选条件。");
  }

  function renderCategories(){
    const counts=new Map();
    state.skills.forEach(skill=>counts.set(skill.category||"其他",(counts.get(skill.category||"其他")||0)+1));
    const buttons=[["",`全部 ${state.skills.length}`],...[...counts.entries()].sort((a,b)=>a[0].localeCompare(b[0],"zh-CN")).map(([name,count])=>[name,`${name} ${count}`])];
    document.querySelector("#categories").innerHTML=buttons.map(([value,label])=>`<button class="chip" type="button" data-category="${S.esc(value)}" aria-pressed="${String(state.category===value)}">${S.esc(label)}</button>`).join("");
    document.querySelectorAll("[data-category]").forEach(button=>button.addEventListener("click",()=>{
      state.category=button.dataset.category;
      renderCategories();
      renderList();
    }));
  }

  function renderOwnership(){
    const counts=new Map();
    state.skills.forEach(skill=>counts.set(identityOf(skill),(counts.get(identityOf(skill))||0)+1));
    const definitions=[
      ["",`全部 ${state.skills.length}`],
      ["self-authored",`已确认原创 ${counts.get("self-authored")||0}`],
      ["adapted",`自定义改造 ${counts.get("adapted")||0}`],
      ["project",`项目孵化 ${counts.get("project")||0}`]
    ];
    document.querySelector("#ownership").innerHTML=definitions.map(([value,label])=>`<button class="chip identity-chip" type="button" data-identity="${S.esc(value)}" aria-pressed="${String(state.identity===value)}">${S.esc(label)}</button>`).join("");
    document.querySelectorAll("[data-identity]").forEach(button=>button.addEventListener("click",()=>{
      state.identity=button.dataset.identity;
      renderOwnership();
      renderList();
    }));
  }

  function reviewCard(candidate){
    const suggestion=candidate.suggested_classification;
    const options=[
      ["","请选择"],
      ["self-authored","我的原创"],
      ["public-installed","公开安装"],
      ["adapted","自定义改造"]
    ];
    const evidence=(candidate.evidence||[]).map(item=>`<li>${S.esc(item)}</li>`).join("");
    return `
      <article class="review-candidate" data-skill-id="${S.esc(candidate.skill_id)}" data-confidence="${S.esc(candidate.confidence)}">
        <header>
          <label class="review-check">
            <input class="review-select" type="checkbox" ${candidate.selected_by_default?"checked":""}>
            <span>
              <strong>${S.esc(candidate.display_name)}</strong>
              <code>$${S.esc(candidate.name)}</code>
            </span>
          </label>
          <div class="review-badges">
            ${S.badge(confidenceLabels[candidate.confidence]||candidate.confidence,candidate.confidence)}
            ${suggestion&&suggestion!=="unknown"?S.badge(`建议：${classificationLabels[suggestion]||suggestion}`):S.badge("暂无建议")}
          </div>
        </header>
        <div class="review-candidate-body">
          <div>
            <p>${S.esc(candidate.description)}</p>
            <ul class="review-evidence">${evidence}</ul>
          </div>
          <div class="review-decision">
            <label>
              <span>确认归类</span>
              <select class="field review-classification" aria-label="${S.esc(candidate.display_name)} 的确认归类">
                ${options.map(([value,label])=>`<option value="${value}" ${value===suggestion?"selected":""}>${label}</option>`).join("")}
              </select>
            </label>
            <details class="review-upstream" ${suggestion==="adapted"?"open":""}>
              <summary>上游来源与作者（公开安装可选，改造版必填）</summary>
              <div>
                <label><span>上游 URL</span><input class="field review-source" type="url" value="${S.esc(candidate.upstream_source||"")}" placeholder="https://github.com/owner/repo"></label>
                <label><span>上游作者</span><input class="field review-author" value="${S.esc(candidate.upstream_author||"")}" placeholder="作者或组织"></label>
              </div>
            </details>
          </div>
        </div>
      </article>
    `;
  }

  function invalidateReviewPreview(){
    state.reviewPreviewToken="";
    const confirmation=document.querySelector("#review-confirmation");
    confirmation.hidden=true;
    confirmation.innerHTML="";
  }

  function updateReviewSelection(){
    const selected=document.querySelectorAll(".review-select:checked").length;
    document.querySelector("#review-selected").textContent=selected;
    document.querySelector("#review-selection-copy").textContent=selected?`已选择 ${selected} 个，尚未写入`:"尚未选择";
    document.querySelector("#review-preview").disabled=selected===0;
  }

  function syncReviewSourceFields(card){
    const classification=card.querySelector(".review-classification").value;
    const details=card.querySelector(".review-upstream");
    const source=card.querySelector(".review-source");
    source.required=classification==="adapted";
    if(classification==="adapted")details.open=true;
  }

  function bindReviewCandidates(){
    document.querySelectorAll(".review-candidate").forEach(card=>{
      syncReviewSourceFields(card);
      card.querySelector(".review-select").addEventListener("change",()=>{
        invalidateReviewPreview();
        updateReviewSelection();
      });
      card.querySelector(".review-classification").addEventListener("change",()=>{
        syncReviewSourceFields(card);
        invalidateReviewPreview();
      });
      card.querySelectorAll(".review-source,.review-author").forEach(input=>input.addEventListener("input",invalidateReviewPreview));
    });
  }

  function renderReviewGroup(title,copy,candidates){
    if(!candidates.length)return "";
    return `
      <section class="review-group">
        <div class="review-group-head"><div><h3>${S.esc(title)}</h3><p>${S.esc(copy)}</p></div><span>${candidates.length} 个</span></div>
        <div class="review-list">${candidates.map(reviewCard).join("")}</div>
      </section>
    `;
  }

  function renderSourceReview(review){
    state.review=review;
    state.reviewPreviewToken="";
    const panel=document.querySelector("#source-review");
    const total=Number(review?.summary?.total||0);
    panel.hidden=total===0;
    if(!total)return;
    document.querySelector("#review-total").textContent=total;
    document.querySelector("#review-high").textContent=review.summary.high_confidence;
    document.querySelector("#review-needs").textContent=review.summary.needs_review;
    const high=review.candidates.filter(item=>item.confidence==="high");
    const needs=review.candidates.filter(item=>item.confidence!=="high");
    document.querySelector("#review-candidates").innerHTML=
      renderReviewGroup("高置信度建议","证据较完整，已默认选中；提交前仍可逐项修改。",high)+
      renderReviewGroup("需要你复核","线索不足以自动确认，默认不选中。",needs);
    const workspace=document.querySelector("#review-workspace");
    workspace.hidden=!state.reviewOpen;
    const toggle=document.querySelector("#review-toggle");
    toggle.setAttribute("aria-expanded",String(state.reviewOpen));
    toggle.textContent=state.reviewOpen?"收起整理向导":"开始整理";
    bindReviewCandidates();
    updateReviewSelection();
  }

  function reviewDecisions(){
    const decisions=[];
    for(const checkbox of document.querySelectorAll(".review-select:checked")){
      const card=checkbox.closest(".review-candidate");
      const classification=card.querySelector(".review-classification");
      const source=card.querySelector(".review-source");
      if(!classification.value){
        classification.setCustomValidity("请先选择归类");
        classification.reportValidity();
        classification.setCustomValidity("");
        throw new Error("有选中的 Skill 尚未选择归类");
      }
      if(classification.value==="adapted"&&!source.value.trim()){
        source.setCustomValidity("改造版必须填写上游 URL");
        source.reportValidity();
        source.setCustomValidity("");
        throw new Error("改造版必须填写上游 URL");
      }
      decisions.push({
        skill_id:card.dataset.skillId,
        classification:classification.value,
        upstream_source:["adapted","public-installed"].includes(classification.value)?source.value.trim():"",
        upstream_author:["adapted","public-installed"].includes(classification.value)?card.querySelector(".review-author").value.trim():""
      });
    }
    return decisions;
  }

  function renderReviewConfirmation(preview){
    state.reviewPreviewToken=preview.preview_token;
    const confirmation=document.querySelector("#review-confirmation");
    const summary=preview.summary;
    confirmation.innerHTML=`
      <div class="review-confirmation-head">
        <div>

          <h3 id="review-confirmation-title">确认这 ${preview.change_count} 项来源归类</h3>
          <p>我的原创 ${summary["self-authored"]||0} 个 · 公开安装 ${summary["public-installed"]||0} 个 · 自定义改造 ${summary.adapted||0} 个</p>
        </div>
        <span class="badge ready">尚未写入</span>
      </div>
      <div class="review-change-list">${preview.changes.map(item=>`
        <div><strong>${S.esc(item.display_name)}</strong><code>$${S.esc(item.name)}</code><span>${S.esc(classificationLabels[item.classification]||item.classification)}</span></div>
      `).join("")}</div>
      <div class="review-final-actions">
        <p>应用后会更新本地分类索引和个人来源回执，不会编辑、移动或删除 Skill 文件。</p>
        <button class="button button-primary" id="review-apply" type="button">确认应用 ${preview.change_count} 项</button>
      </div>
    `;
    confirmation.hidden=false;
    confirmation.focus();
    document.querySelector("#review-apply").addEventListener("click",applyReview);
  }

  async function applyReview(event){
    const button=event.currentTarget;
    button.disabled=true;
    button.textContent="正在应用…";
    try{
      const decisions=reviewDecisions();
      const result=await S.api("/api/classifications",{
        method:"POST",
        body:JSON.stringify({decisions,preview_token:state.reviewPreviewToken})
      });
      S.toast(`已完成 ${result.applied_count} 项来源归类；Skill 文件没有被修改`);
      state.reviewOpen=true;
      await load();
      document.querySelector("#source-review").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"start"});
    }catch(error){
      S.toast(error.message,true);
      button.disabled=false;
      button.textContent="重新确认应用";
    }
  }

  async function load(){
    document.querySelector("#skills").innerHTML=S.skeletons(5);
    try{
      const [summary,payload,review,workflowPayload,insightPayload]=await Promise.all([
        S.api("/api/summary?scope=my"),
        S.api("/api/skills?scope=my&ownership=owned&sort=showcase"),
        S.api("/api/classification-review"),
        S.api("/api/workflows"),
        S.api("/api/insights?scope=my")
      ]);
      state.skills=payload.skills;
      state.workflows=workflowPayload.workflows||[];
      S.setCounts(summary);
      document.querySelector("#stat-total").textContent=payload.skills.length;
      document.querySelector("#stat-inbox").textContent=summary.inbox_skills??0;
      document.querySelector("#stat-removed").textContent=summary.removed_skills??0;
      document.querySelector("#stat-uses").textContent=insightPayload.recorded_events;
      document.querySelector("#usage-coverage").textContent=`部分记录：${insightPayload.tracked_skills}/${insightPayload.eligible_skills} 个已确认 Skill 有日志`;
      const projects=payload.skills.filter(skill=>skill.source_kind==="project");
      document.querySelector("#proposal-copy").textContent=summary.pending_proposals?`另有 ${summary.pending_proposals} 条待审改进提案`:"原创、改造与项目孵化";
      document.querySelector("#project-count").textContent=projects.length;
      document.querySelector("#project-section").hidden=!projects.length;
      renderUpdate(summary.latest_scan);
      renderSourceReview(review);
      renderGoalResults();
      renderResume();
      renderWorkflowShortcuts();
      renderFeatured();
      renderOwnership();
      renderCategories();
      renderList();
    }catch(error){
      document.querySelector("#skills").innerHTML=`<div class="error">${S.esc(error.message)}</div>`;
      S.toast(error.message,true);
    }
  }

  document.querySelector("#search").addEventListener("input",event=>{state.query=event.target.value;renderList()});
  document.querySelector("#goal-search").addEventListener("input",event=>{state.goalQuery=event.target.value;renderGoalResults()});
  document.querySelector("#goal-find").addEventListener("click",()=>{
    state.query=state.goalQuery;
    document.querySelector("#search").value=state.query;
    renderList();
    document.querySelector("#all-title").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});
  });
  document.querySelector("#source-filter").addEventListener("change",event=>{state.source=event.target.value;renderList()});
  document.querySelector("#sort").addEventListener("change",event=>{state.sort=event.target.value;renderList()});
  document.querySelector("#project-filter").addEventListener("click",()=>{
    state.identity=state.identity==="project"?"":"project";
    renderOwnership();
    renderList();
    document.querySelector("#all-title").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});
  });
  document.querySelector("#review-toggle").addEventListener("click",()=>{
    state.reviewOpen=!state.reviewOpen;
    const workspace=document.querySelector("#review-workspace");
    workspace.hidden=!state.reviewOpen;
    const toggle=document.querySelector("#review-toggle");
    toggle.setAttribute("aria-expanded",String(state.reviewOpen));
    toggle.textContent=state.reviewOpen?"收起整理向导":"开始整理";
    if(state.reviewOpen)document.querySelector("#review-candidates").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"start"});
  });
  document.querySelector("#review-select-high").addEventListener("click",()=>{
    document.querySelectorAll('.review-candidate[data-confidence="high"] .review-select').forEach(input=>{input.checked=true});
    invalidateReviewPreview();
    updateReviewSelection();
  });
  document.querySelector("#review-clear").addEventListener("click",()=>{
    document.querySelectorAll(".review-select").forEach(input=>{input.checked=false});
    invalidateReviewPreview();
    updateReviewSelection();
  });
  document.querySelector("#review-preview").addEventListener("click",async event=>{
    const button=event.currentTarget;
    button.disabled=true;
    button.textContent="正在预览…";
    try{
      const decisions=reviewDecisions();
      const preview=await S.api("/api/classifications/preview",{
        method:"POST",
        body:JSON.stringify({decisions})
      });
      renderReviewConfirmation(preview);
    }catch(error){
      S.toast(error.message,true);
    }finally{
      button.disabled=false;
      button.textContent="预览所选归类";
    }
  });
  document.querySelector("#scan").addEventListener("click",async event=>{
    const button=event.currentTarget;
    button.disabled=true;
    button.textContent="正在扫描…";
    try{
      const result=await S.api("/api/scan",{method:"POST",body:"{}"});
      renderUpdate(result);
      const changes=scanCount(result,"added")+scanCount(result,"updated")+scanCount(result,"removed");
      S.toast(changes?`扫描完成：发现 ${changes} 项本地来源变化`:"扫描完成：没有发现变化");
      await load();
      document.querySelector("#update-panel").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"nearest"});
    }catch(error){
      S.toast(`扫描失败：${error.message}`,true);
    }finally{
      button.disabled=false;
      button.textContent="重新扫描本地 Skills";
    }
  });

  load();
})();
