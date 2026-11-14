(()=>{
'use strict';
const data=window.SHARK_DATA||[], colors={LC:'#58b8df',VU:'#f0cd55',EN:'#f18c45',CR:'#e65b55'};
const slides=[...document.querySelectorAll('.slide')];
const stacked=matchMedia('(max-width: 800px)');
const canvas=document.getElementById('scatter');
const axisLabels=[...document.querySelectorAll('.axis span')];
let scatterRaf=0;
function drawScatter(progress=1){
  const box=canvas.getBoundingClientRect();
  if(!box.width||!box.height)return;
  const dpr=Math.min(devicePixelRatio||1,2);
  canvas.width=Math.max(1,box.width*dpr);canvas.height=Math.max(1,box.height*dpr);
  const c=canvas.getContext('2d'),w=box.width,h=box.height,p=22;c.scale(dpr,dpr);c.clearRect(0,0,w,h);
  axisLabels.forEach((label,i)=>label.style.left=`${p+(w-p*2)*(i*250)/1305}px`);
  c.strokeStyle='rgba(177,220,223,.12)';c.lineWidth=1;
  for(let m=0;m<=1250;m+=250){const x=p+(w-p*2)*m/1305;c.beginPath();c.moveTo(x,0);c.lineTo(x,h);c.stroke()}
  const rows={LC:.14,VU:.38,EN:.62,CR:.86},count=Math.ceil(data.length*progress);
  data.slice(0,count).forEach((d,i)=>{const x=p+(w-p*2)*d.depth_m/1305,y=h*(rows[d.tier]+(((i*47)%23)-11)/250);c.beginPath();c.arc(x,y,Math.max(2.2,Math.min(4,w/260)),0,Math.PI*2);c.fillStyle=colors[d.tier];c.shadowColor=colors[d.tier];c.shadowBlur=8;c.fill()});
  c.shadowBlur=0;Object.entries(rows).forEach(([k,y])=>{c.fillStyle=colors[k];c.font='700 11px sans-serif';c.fillText(k,2,h*y+4)});
}
function revealScatter(){
  cancelAnimationFrame(scatterRaf);
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){drawScatter(1);return}
  const start=performance.now();
  function reveal(now){const progress=Math.min(1,(now-start)/900);drawScatter(progress);if(progress<1)scatterRaf=requestAnimationFrame(reveal)}
  scatterRaf=requestAnimationFrame(reveal);
}
let current=Math.max(0,Math.min(3,Number(location.hash.replace('#slide-',''))-1||0));
function show(i){
  current=(i+slides.length)%slides.length;
  if(stacked.matches){slides.forEach(s=>{s.hidden=false;if('inert' in s)s.inert=false;s.setAttribute('aria-hidden','false')});requestAnimationFrame(revealScatter);return}
  slides.forEach((s,n)=>{const on=n===current;s.classList.toggle('active',on);s.hidden=!on;if('inert' in s)s.inert=!on;s.setAttribute('aria-hidden',String(!on))});
  history.replaceState(null,'',`#slide-${current+1}`);
  if(current===1)requestAnimationFrame(revealScatter);
}
stacked.addEventListener('change',()=>show(current));
document.getElementById('prev').onclick=()=>show(current-1);
document.getElementById('next').onclick=()=>show(current+1);
addEventListener('keydown',e=>{
  if(e.target instanceof Element&&e.target.closest('button,a,input,select,textarea,[contenteditable]'))return;
  if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(current+1)}
  else if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(current-1)}
  else if(e.key==='Home')show(0);else if(e.key==='End')show(3);
});
show(current);
addEventListener('resize',()=>{if(current===1)drawScatter()});
addEventListener('beforeprint',()=>drawScatter(1));

const play=document.getElementById('play'),replay=document.getElementById('replay'),speed=document.getElementById('speed'),phase=document.getElementById('phase'),timer=document.getElementById('timer');
let playing=false,fast=false,elapsed=0,last=0,raf=0;
function setLights(off){window.SagamiModel?.setLights(off)}
function render(t){
  let label,sub;
  if(t<30){label='All 109 species glow';sub=`Opening · ${Math.ceil(30-t)} s remaining`;setLights(()=>false)}
  else if(t<33){const pulse=Math.floor((t-30)/.5)%2===1;label='46 threatened species blink';sub=`Blink ${Math.min(3,Math.floor((t-30)/1)+1)} of 3 · blue stays on`;setLights(k=>k!=='LC'&&pulse)}
  else if(t<35){label='Critically endangered goes dark';sub='4 red lights disappear';setLights((k,rank)=>k==='CR'&&rank<(t-33)*2)}
  else if(t<37){label='Endangered goes dark';sub='19 orange lights disappear';setLights((k,rank)=>k==='CR'||(k==='EN'&&rank<(t-35)*9.5))}
  else if(t<39){label='Vulnerable goes dark';sub='23 yellow lights disappear';setLights((k,rank)=>k==='CR'||k==='EN'||(k==='VU'&&rank<(t-37)*11.5))}
  else if(t<44){label='63 species remain';sub='Only the blue, not threatened species stay lit';setLights(k=>k!=='LC')}
  else if(t<46){label='All 109 lights return';sub='The cycle restores every species';const offsets={CR:0,EN:4,VU:23};setLights((k,rank)=>k!=='LC'&&(rank+offsets[k])/46>(t-44)/2)}
  else{elapsed=0;label='All 109 species glow';sub='The cycle begins again';setLights(()=>false)}
  phase.textContent=label;timer.textContent=sub;
}
function frame(now){if(!last)last=now;if(playing){elapsed+=(now-last)/1000*(fast?8:1);render(elapsed)}last=now;raf=requestAnimationFrame(frame)}
play.onclick=()=>{playing=!playing;play.textContent=playing?'Pause':'Play';last=performance.now()};
replay.onclick=()=>{elapsed=0;playing=true;play.textContent='Pause';last=performance.now();render(0)};
speed.onclick=()=>{fast=!fast;speed.setAttribute('aria-pressed',String(fast))};
render(0);raf=requestAnimationFrame(frame);
if(!matchMedia('(prefers-reduced-motion: reduce)').matches)addEventListener('pointermove',event=>{document.documentElement.style.setProperty('--ray-x',`${event.clientX/innerWidth*100}%`);document.documentElement.style.setProperty('--ray-y',`${event.clientY/innerHeight*100}%`)},{passive:true});
})();
