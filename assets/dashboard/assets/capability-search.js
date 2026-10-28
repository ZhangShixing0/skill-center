(function(root){
  'use strict';
  const groups=[
    ['github','git','仓库','发布','上传','开源','release','repository','readme'],
    ['视频','短视频','video','remotion','剪辑'],
    ['口播','配音','声音','音频','voiceover','tts','audio'],
    ['网页','页面','界面','前端','设计','网站','frontend','design','ui','ux','html'],
    ['研究','调研','调查','research','investigation'],
    ['论文','文献','学术','paper','scholar','scientific'],
    ['市场','竞品','market','competitive','landscape'],
    ['定位','产品','用户','positioning','product','customer'],
    ['公众号','文章','写作','文案','writing','wechat','copy'],
    ['表格','excel','spreadsheet','xlsx','csv'],
    ['演示','幻灯片','ppt','presentation','slides'],
    ['文档','word','docx','document'],
    ['图片','图像','绘图','image','figure','illustration'],
    ['部署','服务器','deploy','server'],
    ['技能','skill','管理','manager']
  ];
  const stop=new Set(['我','我们','帮我','帮助','一下','一个','一些','需要','想要','希望','完成','使用','进行','请','的','了','在','把','和','与','to','a','the','for','me','help','with','and','make','use']);
  const norm=s=>String(s||'').normalize('NFKC').toLowerCase();
  function terms(query){
    const q=norm(query);const out=new Set();
    if(typeof Intl.Segmenter==='function')for(const part of new Intl.Segmenter('zh',{granularity:'word'}).segment(q))if(part.isWordLike&&!stop.has(part.segment)&&part.segment.length>1)out.add(part.segment);
    for(const term of q.match(/[a-z0-9]+|[\u4e00-\u9fff]{2,}/g)||[])if(!stop.has(term))out.add(term);
    for(const group of groups)for(const term of group)if(q.includes(term))out.add(term);
    return [...out].slice(0,40);
  }
  function match(item,query){
    if(!query.trim())return {score:1,reasons:[]};
    const name=norm(`${item.name||''} ${item.display_name||''} ${item.title||''}`);
    const hay=norm([name,item.description,item.description_original,item.description_zh,item.use_when_zh,item.category,item.best_for,(item.steps||[]).map(x=>`${x.skill} ${x.display_name} ${x.role}`).join(' ')].join(' '));
    const q=norm(query).trim();let score=name===q?200:hay.includes(q)?75:0;const reasons=[];
    for(const term of terms(query)){
      if(hay.includes(term)){score+=name.includes(term)?15:7;reasons.push(term);continue;}
      const group=groups.find(g=>g.includes(term));
      if(group&&group.some(alias=>hay.includes(alias))){score+=2;reasons.push(term);}
    }
    return {score,reasons:[...new Set(reasons)].slice(0,3)};
  }
  const api={match,terms};root.CapabilitySearch=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
