(function(){
  "use strict";
  const labels={
    classification:{"self-authored":"我的原创","adapted":"改造版","unknown":"待认领","public-installed":"公开安装","system":"系统内置","plugin":"插件提供"},
    source:{personal:"全局个人",project:"项目级",system:"系统",plugin:"插件"},
    sync:{current:"与项目一致","promotion-ready":"可推广","review-required":"需审查","name-collision":"同名冲突","update-available":"项目有更新","snapshot-modified":"全局已修改",diverged:"两端均修改","source-missing":"来源缺失","identical-copy":"重复副本"}
  };
  let toastTimer;
  const esc=value=>String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
  async function api(path,options={}){const response=await fetch(path,{headers:{"Content-Type":"application/json"},...options});const body=await response.json().catch(()=>({}));if(!response.ok){const message=body.error||`请求失败：${response.status}`;throw new Error(body.recovery?`${message} ${body.recovery}`:message)}return body}
  function toast(message,error=false){const node=document.querySelector('#toast');if(!node)return;clearTimeout(toastTimer);node.textContent=message;node.classList.toggle('error',error);node.classList.add('show');toastTimer=setTimeout(()=>node.classList.remove('show'),3200)}
  async function copy(value){try{await navigator.clipboard.writeText(value);toast('已复制到剪贴板')}catch{const area=document.createElement('textarea');area.value=value;document.body.append(area);area.select();document.execCommand('copy');area.remove();toast('已复制到剪贴板')}}
  function date(value){if(!value)return '尚未使用';const d=new Date(value);if(Number.isNaN(d.getTime()))return '—';const days=Math.floor((Date.now()-d.getTime())/86400000);if(days<=0)return '今天';if(days===1)return '昨天';if(days<30)return `${days} 天前`;return new Intl.DateTimeFormat('zh-CN',{month:'short',day:'numeric'}).format(d)}
  function dateTime(value){if(!value)return '时间未知';const d=new Date(value);if(Number.isNaN(d.getTime()))return '时间未知';return new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(d)}
  function badge(text,kind=''){return `<span class="badge ${esc(kind)}">${esc(text)}</span>`}
  function sourceBadge(skill){if(skill.source_kind==='project')return badge('项目级','project');if(skill.classification==='self-authored')return badge('我的原创','self');if(!skill.is_present&&skill.classification==='unknown')return badge('来源未确认');return badge(labels.classification[skill.classification]||skill.classification)}
  function syncBadge(skill){const label=labels.sync[skill.sync_status];if(!label)return '';const kind=['current','promotion-ready','identical-copy'].includes(skill.sync_status)?'ready':['update-available','snapshot-modified','diverged'].includes(skill.sync_status)?'update':'';return badge(label,kind)}
  function setCounts(summary){document.querySelectorAll('[data-count="all"]').forEach(n=>n.textContent=summary.total_skills??'—');document.querySelectorAll('[data-count="inbox"]').forEach(n=>n.textContent=summary.inbox_skills??'—');document.querySelectorAll('[data-count="my"]').forEach(n=>n.textContent=summary.my_skills??'—');document.querySelectorAll('[data-count="public"]').forEach(n=>n.textContent=summary.public_skills??'—');document.querySelectorAll('[data-count="removed"]').forEach(n=>n.textContent=summary.removed_skills??'—')}
  function skeletons(count=4){return Array.from({length:count},()=>'<div class="skeleton" aria-hidden="true"></div>').join('')}
  function empty(title,copyText=''){return `<div class="empty"><strong>${esc(title)}</strong>${copyText?`<p>${esc(copyText)}</p>`:''}</div>`}
  const iconPaths={
    book:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 3v18M12 8h4M12 12h4"/>',
    flow:'<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M6 9v9h9M9 6h9v9"/>',
    compass:'<circle cx="12" cy="12" r="9"/><path d="m16 8-3 5-5 3 3-5 5-3Z"/>',
    chart:'<path d="M4 3v17h17M8 15v-4M13 15V6M18 15V9"/>',
    folder:'<path d="M3 7V5h7l2 3h9v12H3Z"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    star:'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z"/>',
    search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    code:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
    mic:'<rect x="8" y="3" width="8" height="12" rx="4"/><path d="M5 11v1a7 7 0 0 0 14 0v-1M12 19v3M8 22h8"/>',
    image:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
    refresh:'<path d="M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 13-3l2 2M4 17l2 2a8 8 0 0 0 13-3"/>',
    copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    check:'<path d="m5 12 4 4L20 5"/>'
  };
  function icon(name){return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name]||iconPaths.book}</svg>`}
  function nav(page){
    const link=(id,path,label,glyph,count)=>`<a href="${path}" ${page===id?'aria-current="page"':''}><span class="nav-icon">${icon(glyph)}</span><span>${label}</span>${count?`<span class="count" data-count="${count}">—</span>`:''}</a>`;
    return `<aside class="sidebar"><a class="brand" href="my-skills.html"><span class="brand-mark">${icon('book')}</span><span class="brand-copy"><strong>Skill Center</strong><small>个人能力工作空间</small></span></a><nav class="nav" aria-label="Skill Center 主导航">${link('my','my-skills.html','能力库','book','all')}${link('workflows','workflows.html','工作流','flow')}${link('discover','discover.html','探索能力','compass')}${link('public','public-skills.html','公开与系统','folder','public')}</nav><p class="nav-label">管理与回顾</p><nav class="nav nav-secondary" aria-label="管理与回顾">${link('manage','manage.html','归属与维护','folder','inbox')}${link('sources','sources.html','扫描来源','compass')}${link('insights','insights.html','使用洞察','chart')}${link('removed','removed-skills.html','移除历史','clock','removed')}</nav><div class="sidebar-note"><div class="local-status">本地工作空间</div><p>你的能力、来源与使用记录，<br>都留在这台设备上。</p><code>${esc(location.host||'本机文件')}</code></div></aside>`;
  }
  window.SkillCenter={icon,api,badge,copy,date,dateTime,empty,esc,labels,nav,setCounts,skeletons,sourceBadge,syncBadge,toast};
})();
