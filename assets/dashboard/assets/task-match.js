(function(root,factory){
  const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.TaskMatch=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const norm=value=>String(value||'').normalize('NFKC').toLowerCase().trim();
  const base=skill=>norm(skill.name).split(':').at(-1);
  // Explicit task routes, not model inference. Keep reasons tied to the matched operation.
  const routes=[
    {test:/github|readme|开源项目|发布仓库/,skills:['project-readme','publish-github-project'],reason:'任务涉及项目发布或仓库介绍，请先核对这项能力能覆盖的文档或发布环节。'},
    {test:/网页|网站|前端|界面|首页|frontend|\bui\b/,skills:['web-ui-review','frontend-app-builder','impeccable'],reason:'任务涉及网页或产品界面，可先核对界面与交互要求，再选择检查或实现能力。'},
    {test:/市场|竞品|竞争者|market|competitive/,skills:['market-research','market-landscape-scan'],reason:'任务涉及市场或竞品比较，这项能力梳理参与者、替代方案与待验证机会。'},
    {test:/检索.*论文|查找.*论文|搜.*文献|文献检索|paper.*search|find.*papers/,skills:['paper-lookup'],reason:'任务涉及论文或文献检索，这项能力查找研究来源与开放全文。'},
    {test:/调研|调查|研究|research|investigation/,skills:['autonomous-investigation'],reason:'任务涉及调查研究，这项能力组织检索与证据，区分事实和推断。'},
    {test:/excel|xlsx|csv|表格|电子表/,skills:['spreadsheets'],reason:'任务涉及表格数据，可使用表格能力整理、计算或分析。'},
    {test:/ppt|幻灯片|演示文稿|slides|presentation/,skills:['presentations'],reason:'任务涉及幻灯片或演示文稿，可使用演示制作能力组织内容与页面。'},
    {test:/word|docx|word文档/,skills:['documents'],reason:'任务涉及 Word 文档，可使用文档能力制作、修改与检查排版。'},
    {test:/部署|服务器|deploy/,skills:['safe-server-deploy'],reason:'任务涉及服务器发布，这项能力处理验证、备份、切换与回退。'}
  ];
  function positiveText(query){
    return norm(query).replace(/(?:不需要|不要|不用|无需|不做|不生成|不发布|不想|do not|don't|without)[^，。；,;！？!?]*?(?=只要|只需|而是|改为|但要|[，。；,;！？!?]|$)/g,' ');
  }
  function tokens(query){
    const stop=new Set(['帮我','帮助','我们','一个','一些','需要','想要','希望','完成','一下','任务','可以','什么','使用','制作','整理','please','help','with','make','want','create','task']);
    const set=new Set();
    if(typeof Intl.Segmenter==='function')for(const part of new Intl.Segmenter('zh',{granularity:'word'}).segment(query))if(part.isWordLike&&part.segment.length>1&&!stop.has(part.segment))set.add(part.segment);
    for(const t of query.match(/[a-z][a-z0-9_-]{2,}/g)||[])if(!stop.has(t))set.add(t);
    return [...set].slice(0,40);
  }
  function recommend(skills,query){
    const q=positiveText(String(query||'').slice(0,2000));if(!q)return [];
    const available=new Set((skills||[]).filter(s=>s?.is_present).map(base));
    const terms=tokens(q),matched=routes.filter(r=>r.test.test(q)&&(!r.guard||r.guard(q))&&r.skills.some(name=>available.has(name))),byName=new Map();
    for(const skill of skills||[]){
      if(!skill||!skill.is_present||!skill.id||!skill.name)continue;
      const name=base(skill),full=norm(skill.name),title=norm(skill.display_name_zh||skill.display_name),description=norm([skill.description_zh,skill.use_when_zh,skill.description].filter(Boolean).join(' '));
      const direct=matched.filter(r=>r.skills.includes(name));
      const nameHits=terms.filter(t=>full.includes(t)||title.includes(t));
      const hits=terms.filter(t=>description.includes(t));
      const exact=q===full||q===name||q===title;
      // Explicit names and known routes outrank broad description mentions. Unmatched routes
      // do not pull in unrelated skills merely because their long description shares words.
      if(!exact&&!direct.length&&(matched.length||!nameHits.length&&hits.length<2))continue;
      const routeScore=direct.reduce((best,r)=>Math.max(best,120-r.skills.indexOf(name)*8-(r.skills[0]==='autonomous-investigation'?30:0)),0);
      const score=(exact?300:0)+routeScore+nameHits.length*8+Math.min(hits.length,4)*2;
      if(score<4)continue;
      const reason=exact?'任务直接指定了这项能力。':direct.length?direct[0].reason:`名称或用途包含「${[...new Set([...nameHits,...hits])].slice(0,3).join('、')}」，请核对是否适合本次任务。`;
      const candidate={skill,score,reason,basis:exact?'指定能力':direct.length?'已整理的用途匹配':'名称与用途文字匹配'};
      // Catalog duplicates should not consume candidate slots; retain a concrete current id.
      const previous=byName.get(name);if(!previous||score>previous.score)byName.set(name,candidate);
    }
    return [...byName.values()].sort((a,b)=>b.score-a.score||String(a.skill.name).localeCompare(String(b.skill.name))).slice(0,3);
  }
  return {recommend,positiveText};
});
