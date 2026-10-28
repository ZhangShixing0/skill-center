(function(){
  "use strict";

  const S=window.SkillCenter;
  document.querySelector("#sidebar").innerHTML=S.nav("my");
  const name=new URLSearchParams(location.search).get("id")||"";
  let current=null;

  const outcomeLabels={solved:"已解决",partial:"部分解决",failed:"未解决"};
  const experienceTags=[
    ["clear-steps","步骤清楚"],
    ["stable-result","结果稳定"],
    ["time-saving","节省时间"],
    ["easy-to-use","很顺手"],
    ["wrong-trigger","误触发"],
    ["missing-context","缺少项目上下文"],
    ["script-failed","脚本失败"],
    ["unstable-result","结果不稳定"],
    ["too-verbose","输出太啰嗦"]
  ];
  const tagLabel=value=>Object.fromEntries(experienceTags)[value]||value;

  const list=items=>`<ul class="plain-list">${(items||[]).map(item=>`<li>${S.esc(item)}</li>`).join("")}</ul>`;

  function resources(groups){
    const order=[
      ["scripts","脚本"],
      ["assets","素材"],
      ["references","参考资料"],
      ["agents","Agent 配置"],
      ["other","其他文件"]
    ];
    const html=order
      .filter(([key])=>(groups[key]||[]).length)
      .map(([key,label])=>`
        <details class="resource-group" ${key==="scripts"?"open":""}>
          <summary>${label} · ${groups[key].length}</summary>
          <ul>${groups[key].map(item=>`
            <li><span>${S.esc(item.path)}</span><span>${Math.max(1,Math.round(item.size/1024))} KB</span></li>
          `).join("")}</ul>
        </details>
      `).join("");
    return html||'<p class="subtitle">这个 Skill 只有 SKILL.md，没有附加资源目录。</p>';
  }

  function locations(skill){
    return (skill.locations||[]).map(location=>`
      <div class="location">
        <strong>${S.esc(S.labels.source[location.source_kind]||location.source_kind)}</strong><br>
        ${S.esc(location.path||"")}
      </div>
    `).join("");
  }

  function legacyFeedback(items){
    const legacy=(items||[]).filter(item=>!item.usage_event_id);
    if(!legacy.length)return "";
    return `
      <details class="legacy-feedback">
        <summary>查看 ${legacy.length} 条旧版未关联反馈</summary>
        <div class="feedback-list">${legacy.slice(0,8).map(item=>`
          <article class="feedback-item">
            <strong>${S.esc(outcomeLabels[item.outcome]||item.outcome)}${item.rating?` · ${item.rating}/5`:""}</strong>
            ${item.issue_tags?.length?`<div>${item.issue_tags.map(tag=>S.badge(tagLabel(tag))).join(" ")}</div>`:""}
            ${item.note?`<p>${S.esc(item.note)}</p>`:""}
          </article>
        `).join("")}</div>
      </details>
    `;
  }

  function feedbackEditor(event,autoOpen=false){
    const tags=new Set(event.issue_tags||[]);
    const hasFeedback=Boolean(event.feedback_id);
    return `
      <details class="event-feedback-editor" ${!hasFeedback&&autoOpen?"open":""}>
        <summary>${hasFeedback?"修改这次感受":"记录这次感受"}</summary>
        <form class="event-feedback-form" data-event-id="${event.id}">
          <label>
            结果
            <select class="field" name="outcome" required>
              <option value="">请选择</option>
              ${Object.entries(outcomeLabels).map(([value,label])=>`
                <option value="${value}" ${event.outcome===value?"selected":""}>${label}</option>
              `).join("")}
            </select>
          </label>
          <fieldset class="tag-fieldset">
            <legend>使用感受（可多选）</legend>
            <div class="experience-tags">
              ${experienceTags.map(([value,label])=>`
                <label>
                  <input type="checkbox" name="experience" value="${value}" ${tags.has(value)?"checked":""}>
                  <span>${label}</span>
                </label>
              `).join("")}
            </div>
          </fieldset>
          <details class="optional-feedback" ${event.rating||event.note?"open":""}>
            <summary>补充评分或一句话备注（可选）</summary>
            <div class="optional-feedback-fields">
              <label>
                评分
                <select class="field" name="rating">
                  <option value="0">不评分</option>
                  ${[1,2,3,4,5].map(value=>`
                    <option value="${value}" ${Number(event.rating)===value?"selected":""}>${value} / 5</option>
                  `).join("")}
                </select>
              </label>
              <label>
                简短备注
                <textarea class="field textarea textarea-small" name="note" maxlength="300" placeholder="只写这次使用感受，不要粘贴提示词、对话或敏感数据。">${S.esc(event.note||"")}</textarea>
              </label>
            </div>
          </details>
          <button class="button button-primary" type="submit">${hasFeedback?"更新反馈":"保存反馈"}</button>
        </form>
      </details>
    `;
  }

  function usageEvents(events){
    if(!events?.length){
      return S.empty(
        "还没有调用记录",
        "下次通过 Skill Manager 日志调用后，这里会显示本地项目别名、时间、版本与反馈入口。"
      );
    }
    return `<div class="usage-timeline">${events.slice(0,12).map((event,index)=>`
      <article class="usage-event">
        <header>
          <div>
            <strong>${S.dateTime(event.used_at)}</strong>
            <span>${S.esc(event.workspace_label||"未关联项目")}</span>
          </div>
          <div class="usage-event-badges">
            ${S.badge(event.task_category||"其他")}
            ${S.badge(event.invocation_type==="explicit"?"明确指定":"自动触发")}
            ${S.badge(`版本 ${(event.version_hash||"").slice(0,8)||"未知"}`)}
          </div>
        </header>
        ${event.feedback_id?`
          <div class="event-outcome ${S.esc(event.outcome)}">
            <strong>${S.esc(outcomeLabels[event.outcome]||event.outcome)}</strong>
            ${event.rating?`<span>${event.rating}/5</span>`:""}
            ${(event.issue_tags||[]).map(tag=>S.badge(tagLabel(tag))).join(" ")}
            ${event.note?`<p>${S.esc(event.note)}</p>`:""}
          </div>
        `:""}
        ${feedbackEditor(event,index===0)}
      </article>
    `).join("")}</div>`;
  }

  function usageSummary(events){
    const workspaceCount=new Set((events||[]).map(event=>event.workspace_id).filter(Boolean)).size;
    const versionCount=new Set((events||[]).map(event=>event.version_hash).filter(Boolean)).size;
    const feedbackCount=(events||[]).filter(event=>event.feedback_id).length;
    return {workspaceCount,versionCount,feedbackCount};
  }

  function relatedWorkflows(items){
    if(!items?.length){
      return `
        <section class="panel">
          <div class="section-head compact"><div><h2>参与的跨 Skill 工作流</h2><p>当前还没有作者建议组合或可靠共同运行记录。</p></div></div>
          <a class="button button-ghost" href="workflows.html">浏览全部工作流</a>
        </section>
      `;
    }
    return `
      <section class="panel">
        <div class="section-head compact"><div><h2>参与的跨 Skill 工作流</h2><p>“作者建议”回答应该怎样组合；“共同运行”只统计共享运行编号的真实记录。</p></div></div>
        <div class="related-workflows">${items.map(workflow=>{
          const currentStep=workflow.steps.find(step=>step.skill===current.skill.name);
          return `
            <a href="workflows.html#${S.esc(workflow.id)}">
              <div>
                <span>${S.esc(workflow.source_label)}</span>
                <strong>${S.esc(workflow.title)}</strong>
                <p>第 ${currentStep?.position||"—"} 步：${S.esc(currentStep?.role||"参与流程")}</p>
              </div>
              <small>${workflow.available_count}/${workflow.step_count} 步可用${workflow.multi_skill_runs?` · ${workflow.multi_skill_runs} 次共同运行`:" · 尚无共同运行记录"}</small>
            </a>
          `;
        }).join("")}</div>
      </section>
    `;
  }

  function lifecyclePanel(data){
    const skill=data.skill;
    const events=[
      ["平台首次发现",skill.discovered_at,"这是 Skill Center 第一次扫描到它，不等于作者创作时间。"],
      ["文件最近修改",skill.modified_at,"来自当时 SKILL.md 的文件修改时间。"],
      ["最后确认存在",skill.last_seen_at,"最近一次扫描或启动核对确认文件仍然存在。"],
      ["确认移除",skill.removed_at,"扫描首次确认 SKILL.md 已不存在。"],
      ["最近已记录调用",skill.last_used,skill.last_workspace_label?`项目：${skill.last_workspace_label}`:"没有关联项目别名。"]
    ].filter(([,value])=>value);
    const versions=(data.versions||[]).slice(0,8);
    return `
      <section class="panel lifecycle-panel">
        <div class="section-head compact"><div><h2>Skill 生命周期</h2><p>只展示平台能够证明的观察时间；真实创作时间没有证据时保持未记录。</p></div></div>
        <div class="lifecycle-timeline">
          ${events.map(([label,value,copy])=>`<article><i aria-hidden="true"></i><div><span>${S.esc(label)}</span><strong>${S.esc(S.dateTime(value))}</strong><p>${S.esc(copy)}</p></div></article>`).join("")}
          ${!events.length?S.empty("还没有生命周期记录","完成一次本地扫描后会开始记录。") : ""}
        </div>
        <details class="version-history" ${versions.length>1?"":"hidden"}>
          <summary>查看观察到的 ${versions.length} 个内容版本</summary>
          <div>${versions.map(version=>`<div><code>${S.esc((version.content_hash||"").slice(0,12))}</code><span>${S.esc(S.dateTime(version.first_seen_at))}</span><small>最后见于 ${S.esc(S.dateTime(version.last_seen_at))}</small></div>`).join("")}</div>
        </details>
      </section>
    `;
  }

  function classificationPanel(skill){
    if(!skill.is_present){
      return `<section class="panel"><h2>历史记录只读</h2><p class="subtitle">该 Skill 已从本机移除。可以查看来源、版本和已记录使用，但不能改进、同步或重新归类不存在的文件。</p></section>`;
    }
    if(skill.source_kind==="project"){
      return `
        <section class="panel">
          <h2>来源身份</h2>
          <p class="subtitle">这是项目孵化 Skill，项目目录继续作为事实来源。需要跨项目使用时，请先查看全局推广计划，不必再确认作者归类。</p>
        </section>
      `;
    }
    return `
      <section class="panel">
        <h2>来源归类</h2>
        <p class="subtitle">路径不等于作者身份。选择“公开安装”后，这个 Skill 会移入公开库，但本地文件不会被删除或修改。</p>
        <form id="classification-form" class="feedback-form">
          <label for="classification">作者与安装来源</label>
          <select class="field" id="classification">
            <option value="self-authored" ${skill.classification==="self-authored"?"selected":""}>我的原创</option>
            <option value="public-installed" ${skill.classification==="public-installed"?"selected":""}>公开安装</option>
            <option value="adapted" ${skill.classification==="adapted"?"selected":""}>自定义改造</option>
            <option value="unknown" ${skill.classification==="unknown"?"selected":""}>来源待核对</option>
          </select>
          <div id="classification-upstream">
            <label for="upstream">上游 URL <span id="upstream-requirement">（公开安装可选，改造版必填）</span></label>
            <input class="field" id="upstream" type="url" placeholder="https://github.com/owner/repo" value="${S.esc(skill.upstream_source||"")}">
            <label for="author">上游作者（可选）</label>
            <input class="field" id="author" placeholder="作者或组织" value="${S.esc(skill.upstream_author||"")}">
          </div>
          <button class="button" type="submit">保存来源归类</button>
        </form>
      </section>
    `;
  }

  function render(data){
    current=data;
    const skill=data.skill;
    const guide=data.guide;
    const eventSummary=usageSummary(data.usage_events);
    const removed=!skill.is_present;
    const rawTagline=String(guide.tagline||"").trim();
    const tagline=removed&&(!rawTagline||["|",">","|-",">-"].includes(rawTagline))
      ?"该 Skill 已卸载，当前仅保留生命周期与来源记录。"
      :rawTagline;
    const back=document.querySelector(".back");
    if(removed){back.href="removed-skills.html";back.textContent="← 返回已移除历史"}
    document.title=`${skill.display_name} · Skill 详情`;
    const show=!removed&&guide.showcase_url?`
      <section class="panel showcase">
        <div class="showcase-head">
          <div><h2>真实交互演示</h2></div>
          <a class="button button-small" href="${S.esc(guide.showcase_url)}" target="_blank" rel="noopener">全屏查看 →</a>
        </div>
        <iframe src="${S.esc(guide.showcase_url)}" title="${S.esc(skill.display_name)} 交互演示" loading="lazy"></iframe>
        <p class="showcase-caption">${S.esc(guide.showcase_caption||"本地交互演示")}</p>
      </section>
    `:"";

    document.querySelector("#detail").innerHTML=`
      <header class="detail-hero">
        <div class="detail-badges">
          ${S.sourceBadge(skill)} ${S.syncBadge(skill)}
          ${skill.category?S.badge(skill.category):""}
          ${skill.showcase_level==="rich"?S.badge("丰富展示","rich"):""}
          ${skill.duplicate_count?S.badge(`${skill.duplicate_count+1} 个位置`):""}
          ${removed?S.badge("已移除","removed"):S.badge("当前可用","ready")}
        </div>
        <h1 class="detail-title">${S.esc(skill.display_name)}</h1>
        <p class="detail-tech">$${S.esc(skill.name)}</p>
        <p class="detail-tagline">${S.esc(tagline)}</p>
      </header>
      ${removed?`<section class="removed-detail-banner" role="status"><div><strong>这个 Skill 已从本机卸载</strong><p>它不会出现在现有或待认领列表中。这里仅保留可验证的来源、版本和已记录使用历史。</p></div><span>${S.esc(skill.removed_at?S.dateTime(skill.removed_at):"移除时间未记录")}</span></section>`:""}
      <div class="detail-layout">
        <div class="detail-main">
          ${lifecyclePanel(data)}
          ${show}
          ${removed?"":`<section class="panel">
            <div class="split">
              <div><h2>适合做什么</h2>${list(guide.best_for)}</div>
              <div><h2>不适合做什么</h2><ul class="plain-list avoid">${guide.not_for.map(item=>`<li>${S.esc(item)}</li>`).join("")}</ul></div>
            </div>
          </section>`}
          ${removed?"":`<section class="panel">
            <h2>可以直接复制的用法</h2>
            <div class="prompt-list">${guide.prompts.map(prompt=>`
              <div class="prompt"><code>${S.esc(prompt)}</code><button class="copy-button" type="button" data-copy="${S.esc(prompt)}">复制</button></div>
            `).join("")}</div>
          </section>`}
          <section class="panel">
            <div class="section-head compact">
              <div>

                <h2>最近调用与使用感受</h2>
                <p>项目只保存本地别名和盐化指纹，不保存绝对路径、提示词或任务文件。</p>
              </div>
            </div>
            ${usageEvents(data.usage_events)}
            ${legacyFeedback(data.feedback)}
          </section>
          ${removed?"":`${relatedWorkflows(data.related_workflows)}<section class="panel">
            <h2>这个 Skill 自己怎么执行</h2>
            <p class="subtitle">这里是单个 Skill 内部的工作步骤，不等于跨 Skill 流水线。</p>
            <div class="workflow">${guide.workflow.map(step=>`<div class="step">${S.esc(step)}</div>`).join("")}</div>
            <div class="split"><div><h3>需要的输入</h3>${list(guide.inputs)}</div><div><h3>交付的输出</h3>${list(guide.outputs)}</div></div>
          </section>
          <section class="panel"><h2>资源清单</h2>${resources(data.resources)}</section>`}
        </div>
        <aside class="detail-aside">
          <section class="panel">
            <h2>已记录使用信号</h2>
            <p class="subtitle">只统计已写入本地日志的调用，不代表全部使用次数。</p>
            <div class="meta-list">
              <div class="meta-item"><span>近 30 天已记录</span><strong>${skill.uses_30} 次</strong></div>
              <div class="meta-item"><span>累计已记录</span><strong>${skill.uses_all} 次</strong></div>
              <div class="meta-item"><span>涉及项目</span><strong>${eventSummary.workspaceCount} 个</strong></div>
              <div class="meta-item"><span>记录版本</span><strong>${eventSummary.versionCount} 个</strong></div>
              <div class="meta-item"><span>已关联反馈</span><strong>${eventSummary.feedbackCount} 条</strong></div>
              <div class="meta-item"><span>最近记录</span><strong>${S.date(skill.last_used)}</strong></div>
              <div class="meta-item"><span>最近项目</span><strong>${S.esc(skill.last_workspace_label||"未关联项目")}</strong></div>
              <div class="meta-item"><span>平均评分</span><strong>${skill.average_rating==null?"尚无评分":`${Number(skill.average_rating).toFixed(1)} / 5`}</strong></div>
              <div class="meta-item"><span>改进优先级</span><strong>${skill.improvement_priority}</strong></div>
            </div>
            ${removed?"":'<button class="button button-ghost" id="proposal" type="button" style="width:100%;margin-top:1rem">生成待审改进提案</button>'}
          </section>
          <section class="panel">
            <h2>来源与同步</h2>
            <div class="meta-list">
              <div class="meta-item"><span>主要来源</span><strong>${S.esc(S.labels.source[skill.source_kind]||skill.source_kind)}</strong></div>
              <div class="meta-item"><span>同步状态</span><strong>${S.esc(S.labels.sync[skill.sync_status]||skill.sync_status||"未关联")}</strong></div>
              <div class="meta-item"><span>存在状态</span><strong>${S.esc(skill.presence_label)}</strong></div>
              <div class="meta-item"><span>内容指纹</span><code>${S.esc((skill.content_hash||skill.version_hash||"").slice(0,16))}</code></div>
              ${skill.origin_path?`<div class="meta-item"><span>项目事实来源</span><code>${S.esc(skill.origin_path)}</code></div>`:""}
            </div>
            ${locations(skill)}
            ${skill.is_present&&skill.source_kind==="project"?'<button class="button button-ghost" id="promotion" type="button" style="width:100%;margin-top:1rem">查看全局推广计划</button>':""}
            ${skill.is_present&&skill.origin_path?'<button class="button button-ghost" id="diff" type="button" style="width:100%;margin-top:.6rem">比较项目差异</button>':""}
            <div id="source-result" style="margin-top:1rem"></div>
          </section>
          ${classificationPanel(skill)}
        </aside>
      </div>
    `;
    bind();
  }

  function sourceResult(html){
    document.querySelector("#source-result").innerHTML=html;
  }

  function bind(){
    document.querySelectorAll("[data-copy]").forEach(button=>button.addEventListener("click",()=>S.copy(button.dataset.copy)));

    document.querySelectorAll(".event-feedback-form").forEach(form=>form.addEventListener("submit",async event=>{
      event.preventDefault();
      const button=event.submitter;
      const data=new FormData(form);
      button.disabled=true;
      try{
        await S.api("/api/feedback",{
          method:"POST",
          body:JSON.stringify({
            skill_id:current.skill.id,
            usage_event_id:Number(form.dataset.eventId),
            outcome:data.get("outcome"),
            rating:Number(data.get("rating")||0),
            issue_tags:data.getAll("experience"),
            note:data.get("note")||""
          })
        });
        S.toast("这次使用感受已保存，可用于比较项目和版本效果");
        await load();
      }catch(error){
        S.toast(error.message,true);
      }finally{
        button.disabled=false;
      }
    }));

    document.querySelector("#proposal")?.addEventListener("click",async event=>{
      event.currentTarget.disabled=true;
      try{
        const proposal=await S.api("/api/proposals",{
          method:"POST",
          body:JSON.stringify({skill_id:current.skill.id})
        });
        S.toast("待审提案已生成，不会自动修改文件");
        event.currentTarget.textContent=`已生成提案 #${proposal.id}`;
      }catch(error){
        S.toast(error.message,true);
        event.currentTarget.disabled=false;
      }
    });

    const classificationForm=document.querySelector("#classification-form");
    const classificationSelect=document.querySelector("#classification");
    const syncClassificationFields=()=>{
      if(!classificationSelect)return;
      const source=document.querySelector("#upstream");
      const needsSource=classificationSelect.value==="adapted";
      source.required=needsSource;
      document.querySelector("#classification-upstream").hidden=!["adapted","public-installed"].includes(classificationSelect.value);
      document.querySelector("#upstream-requirement").textContent=needsSource?"（必填）":"（可选）";
    };
    classificationSelect?.addEventListener("change",syncClassificationFields);
    syncClassificationFields();
    classificationForm?.addEventListener("submit",async event=>{
      event.preventDefault();
      const button=event.submitter;
      const classification=classificationSelect.value;
      button.disabled=true;
      try{
        await S.api("/api/classification",{
          method:"POST",
          body:JSON.stringify({
            skill_id:current.skill.id,
            classification,
            upstream_source:["adapted","public-installed"].includes(classification)?document.querySelector("#upstream").value:"",
            upstream_author:["adapted","public-installed"].includes(classification)?document.querySelector("#author").value:""
          })
        });
        if(classification==="public-installed"){
          S.toast("已归入公开安装；本地 Skill 文件保持不变");
          window.location.href="public-skills.html";
        }else{
          S.toast("来源归类已更新");
          await load();
        }
      }catch(error){
        S.toast(error.message,true);
      }finally{
        button.disabled=false;
      }
    });

    document.querySelector("#promotion")?.addEventListener("click",async event=>{
      event.currentTarget.disabled=true;
      sourceResult('<p class="subtitle">正在生成只读计划…</p>');
      try{
        const plan=await S.api(`/api/promotion-preview?skill_id=${encodeURIComponent(current.skill.id)}`);
        sourceResult(`
          <div class="meta-list">
            <div class="meta-item"><span>结论</span><strong>${S.esc(plan.verdict)}</strong></div>
            <div class="meta-item"><span>目标</span><code>${S.esc(plan.target)}</code></div>
            <div class="meta-item"><span>文件</span><strong>${plan.files.length} 个</strong></div>
            <div class="meta-item"><span>是否写入</span><strong>${plan.writes_performed?"是":"否，只读预览"}</strong></div>
          </div>
        `);
      }catch(error){
        sourceResult(`<div class="error">${S.esc(error.message)}</div>`);
      }finally{
        event.currentTarget.disabled=false;
      }
    });

    document.querySelector("#diff")?.addEventListener("click",async event=>{
      event.currentTarget.disabled=true;
      sourceResult('<p class="subtitle">正在比较…</p>');
      try{
        const diff=await S.api(`/api/snapshot-diff?skill_id=${encodeURIComponent(current.skill.id)}`);
        const changed=diff.changed?.length||0;
        sourceResult(`
          <div class="meta-list">
            <div class="meta-item">
              <span>比较结果</span>
              <strong>${diff.identical?"完全一致":`${changed} 个修改，${diff.added.length} 个新增，${diff.removed.length} 个删除`}</strong>
            </div>
          </div>
          ${changed?`<pre style="white-space:pre-wrap;max-height:18rem;overflow:auto;font-size:.62rem;color:#aeb7c5">${S.esc(diff.changed[0].diff||"二进制或无文本差异")}</pre>`:""}
        `);
      }catch(error){
        sourceResult(`<div class="error">${S.esc(error.message)}</div>`);
      }finally{
        event.currentTarget.disabled=false;
      }
    });
  }

  async function load(){
    if(!name){
      document.querySelector("#detail").innerHTML='<div class="error">地址中缺少 Skill 名称。</div>';
      return;
    }
    try{
      const [summary,data]=await Promise.all([
        S.api("/api/summary"),
        S.api(`/api/skill?name=${encodeURIComponent(name)}`)
      ]);
      S.setCounts(summary);
      render(data);
    }catch(error){
      document.querySelector("#detail").innerHTML=`
        <div class="error">
          <strong>无法打开这个本地详情页</strong>
          <p>${S.esc(error.message)}</p>
          <a class="button" href="public-skills.html">前往公开 Skill 库</a>
        </div>
      `;
      S.toast(error.message,true);
    }
  }

  load();
})();
