let DATA=null, TAB='buffett', YEARS=10, C1=null, C2=null;
const UP='#f45b5b', DN='#4d8ef7';

const META={
  buffett:{name:'한국 버핏지수', unit:'%', base:100,
    note:'시가총액 ÷ 명목GDP(4개 분기 합) × 100. 점선은 표시 구간 평균, 가로선은 100% 기준입니다.'},
  cape:{name:'한국 CAPE (쉴러 PE)', unit:'배', base:null,
    note:'KOSPI ÷ 최근 10년 물가조정 평균 EPS. 점선은 표시 구간 평균입니다.'}
};

fetch('data.json?v='+Date.now()).then(r=>r.json()).then(d=>{DATA=d;draw();})
  .catch(()=>document.getElementById('k-now').textContent='로딩 실패');

const cut=a=>YEARS?a.slice(-YEARS*12):a;

function draw(){
  const m=META[TAB], all=DATA[TAB]||[];
  document.getElementById('title').textContent=m.name;
  document.getElementById('updated').textContent=DATA.updated;
  document.getElementById('note').innerHTML='<b>지표 설명</b><p>'+m.note+'</p>';
  if(!all.length){document.getElementById('k-now').textContent='데이터 없음';return;}

  const s=cut(all), v=s.map(p=>p.v), L=s.map(p=>p.d);
  const now=v[v.length-1], prev=v[v.length-2]??now, chg=now-prev;
  const avg=v.reduce((a,b)=>a+b,0)/v.length;
  const sd=Math.sqrt(v.reduce((a,b)=>a+(b-avg)**2,0)/v.length);
  const z=(now-avg)/(sd||1);

  document.getElementById('k-date').textContent=s[s.length-1].d;
  document.getElementById('k-now').textContent=now.toFixed(2)+m.unit;
  const ce=document.getElementById('k-chg');
  ce.textContent=(chg>=0?'+':'')+chg.toFixed(2)+'p';
  ce.style.color=chg>=0?UP:DN;

  let zt,zc;
  if(z>1.5){zt='과열 영역';zc=UP}
  else if(z>0.5){zt='평균 상회';zc='#e8b339'}
  else if(z>-0.5){zt='평균 수준';zc='#e6edf3'}
  else if(z>-1.5){zt='평균 하회';zc=DN}
  else{zt='침체 영역';zc=DN}
  const ze=document.getElementById('k-zone');
  ze.textContent=zt; ze.style.color=zc;

  const grid={color:'#232b36'}, tick={color:'#8b949e',font:{size:10},maxTicksLimit:9};
  const ds=[{data:v,borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:.3,
    borderColor:UP,
    segment:{borderColor:c=>c.p1.parsed.y>=c.p0.parsed.y?UP:DN}},
   {data:v.map(()=>avg),borderColor:'#6e7681',borderWidth:1,
    borderDash:[5,5],pointRadius:0}];
  if(m.base!==null) ds.push({data:v.map(()=>m.base),borderColor:'#8b949e',
    borderWidth:1,borderDash:[2,3],pointRadius:0});

  C1&&C1.destroy();
  C1=new Chart(document.getElementById('main'),{type:'line',
    data:{labels:L,datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,animation:{duration:300},
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:c=>c.datasetIndex===0
          ?m.name+' '+c.parsed.y.toFixed(2)+m.unit:null}}},
      scales:{x:{ticks:tick,grid:grid},
        y:{ticks:{...tick,callback:x=>x+m.unit},grid:grid}}}});

  const dl=v.map((x,i)=>i?+(x-v[i-1]).toFixed(2):0);
  C2&&C2.destroy();
  C2=new Chart(document.getElementById('delta'),{type:'bar',
    data:{labels:L,datasets:[{data:dl,
      backgroundColor:dl.map(x=>x>=0?UP+'cc':DN+'cc'),
      borderWidth:0,barPercentage:1,categoryPercentage:1}]},
    options:{responsive:true,maintainAspectRatio:false,animation:{duration:300},
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:c=>(c.parsed.y>=0?'+':'')+c.parsed.y+'p'}}},
      scales:{x:{ticks:tick,grid:grid},y:{ticks:tick,grid:grid}}}});
}

document.querySelector('.tabs').onclick=e=>{
  if(e.target.tagName!=='BUTTON')return;
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.remove('on'));
  e.target.classList.add('on'); TAB=e.target.dataset.tab; draw();
};
document.querySelector('.ranges').onclick=e=>{
  if(e.target.tagName!=='BUTTON')return;
  document.querySelectorAll('.ranges button').forEach(b=>b.classList.remove('on'));
  e.target.classList.add('on'); YEARS=+e.target.dataset.y; draw();
};
