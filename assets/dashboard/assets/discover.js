(function(){'use strict';const S=window.SkillCenter;document.querySelector('#sidebar').innerHTML=S.nav('discover');S.api('/api/summary').then(S.setCounts).catch(()=>{});})();
