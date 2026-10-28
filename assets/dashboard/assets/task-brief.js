(function(root,factory){
  const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.TaskBrief=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  // Guides for the original, optional examples shipped in examples/skills.
  const profiles={
  "project-readme": {
    "when": [
      "需要为项目补齐介绍、安装步骤与使用示例。"
    ],
    "inputs": [
      "项目源码与当前 README",
      "目标读者、已验证的启动命令和功能边界"
    ],
    "outputs": [
      "与实际代码一致的 README",
      "安装与使用步骤的验证记录"
    ],
    "example": "为我的开源工具完善 README，让第一次使用的人能够安装、启动并完成第一个任务。",
    "deliverable": "README、可复现的安装与使用说明，以及尚未验证的事项。"
  },
  "web-ui-review": {
    "when": [
      "需要检查现有网页在桌面、手机和键盘操作下的表现。"
    ],
    "inputs": [
      "可访问的本地页面与启动方式",
      "关键操作、目标屏幕尺寸与需要保留的功能"
    ],
    "outputs": [
      "有页面位置与复现步骤的问题清单",
      "按影响排序的改进建议"
    ],
    "example": "检查项目首页的手机布局和键盘操作，优先指出会妨碍使用的问题。",
    "deliverable": "问题、复现步骤、影响与建议；区分实际检查结果和待验证项。"
  },
  "market-research": {
    "when": [
      "需要梳理一个市场中的产品、替代方案与机会。"
    ],
    "inputs": [
      "市场范围、目标用户和要支持的决策",
      "已知产品与比较维度"
    ],
    "outputs": [
      "附来源的产品与替代方案对比",
      "事实、推断与待验证问题"
    ],
    "example": "调研面向独立开发者的项目管理工具，比较主要产品与替代方案，帮助确定优先验证的需求。",
    "deliverable": "带来源的对比表、关键发现与待验证问题。"
  }
};
  const clean=(value,max=8000)=>typeof value==='string'?value.trim().slice(0,max):'';
  const lines=value=>Array.isArray(value)?value.filter(v=>typeof v==='string'&&v.trim()).slice(0,4).map(v=>clean(v,1200)):[];
  function guideFor(skill,detail){
    const profile=profiles[skill.name],g=detail?.guide||{};
    const when=profile?.when||lines(g.best_for);
    const name=skill.display_name_zh||skill.display_name||skill.name;
    const genericInputs=['明确的目标','相关上下文或素材','输出限制'];
    const inputs=lines(g.inputs),outputs=lines(g.outputs);
    const hasSpecificInputs=inputs.length&&JSON.stringify(inputs)!==JSON.stringify(genericInputs);
    const hasSpecificOutputs=outputs.length&&outputs[0]!=='符合 Skill 工作流的可验证结果';
    return {
      when:when.length?when:[clean(skill.use_when_zh||skill.description_zh||skill.description,1200)||'根据原始说明核对这项能力是否适合你的任务。'],
      inputs:profile?.inputs||(hasSpecificInputs?inputs:['具体目标和使用场景','相关文件、链接或现有内容','期望格式与验收要求']),
      outputs:profile?.outputs||(hasSpecificOutputs?outputs:['按本次任务约定的交付物；开始前确认范围与验收要求。']),
      example:profile?.example||`使用「${name}」处理我提供的材料。先确认需要补充的信息，再按约定的格式交付结果。`,
      deliverable:profile?.deliverable||(hasSpecificOutputs?outputs.join('；'):''),
      kind:profile?'curated':hasSpecificInputs||hasSpecificOutputs?'catalog':'generic',
      note:profile?'按本地说明整理；示例可按你的任务修改。':hasSpecificInputs||hasSpecificOutputs?'材料和交付要求来自本地用途目录。':'材料、交付和示例为通用准备建议，具体要求以 Skill 原始说明为准。'
    };
  }
  function normalize(values){
    return {goal:clean(values?.goal,2000),project:clean(values?.project,1000),materials:clean(values?.materials,8000),deliverable:clean(values?.deliverable,3000),constraints:clean(values?.constraints,3000)};
  }
  function validate(values){return clean(values?.goal)?'':'请先写下这次想完成的具体目标。';}
  function build(skill,values){
    const v=normalize(values);if(validate(v))return '';
    const identity=[`请使用 $${skill.name} 完成以下任务。开始前读取该 Skill 的说明，核对适用范围与所需材料。`];
    if(skill.path)identity.push(`Skill 位置：${skill.path}`);
    if(skill.content_hash||skill.version_hash)identity.push(`任务准备时的索引版本：${skill.content_hash||skill.version_hash}`);
    return [identity.join('\n'),`任务目标\n${v.goal}`,`项目与上下文\n${v.project||'未指定项目，请按任务需要确认工作目录。'}`,`输入材料\n${v.materials||'尚未提供，请先确认需要哪些材料。'}`,`交付与验收\n${v.deliverable||'请根据任务目标提出交付物和验收方式，开始前确认。'}`,v.constraints?`补充要求\n${v.constraints}`:'', '执行要求\n按该 Skill 的工作流推进；材料不足或事实不确定时明确指出。交付时说明完成内容、验证结果与尚待处理的问题。'].filter(Boolean).join('\n\n');
  }
  return {guideFor,normalize,validate,build};
});
