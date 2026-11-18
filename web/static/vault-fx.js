'use strict';
// Cinematic vault opening: pixel cube in CSS 3D, canvas particles, synthesized
// sounds. Self-contained; app.js calls VaultFX.play() and VaultFX.icon().
(()=>{
const reduce=matchMedia('(prefers-reduced-motion: reduce)');
const wait=ms=>new Promise(r=>setTimeout(r,ms));

// ---------- Pixel icons (10x10, own designs) ----------
const SHAPES={
gem:['...cccc...','..caaaac..','.caaaaaab.','caaacaaaab','caacaaaaab','.caaaaaab.','..caaaab..','...caab...','....bb....'],
block:['cccccccccb','caaaaaaaab','caddaadaab','caaaaaaaab','cadaaaddab','caaaaaaaab','caaddaaaab','caaaaadaab','caaaaaaaab','bbbbbbbbbb'],
apple:['....d.....','....dd....','..caaaa...','.caaaaab..','caacaaaab.','caaaaaaab.','caaaaaaab.','.caaaaab..','..baabb...'],
arrow:['.......cc.','......cac.','.....cab..','....cab...','...cab....','..cab.....','dda.......','ddd.......','.d........'],
swirl:['...cccc...','..c....c..','.c..aa..c.','.c.a..a.c.','.c.a.ca.c.','.c..aa..c.','..c....c..','...cccc...'],
bottle:['....bb....','....cc....','...caac...','..caaaab..','.caacaaab.','.caaaaaab.','.caaaaaab.','..bbbbbb..'],
book:['.bbbbbbbb.','bccccccccb','bcaaaaaacb','bcaddaaacb','bcaaaaaacb','bcaadddacb','bcaaaaaacb','bccccccccb','.bbbbbbbb.'],
axe:['..ccc.....','.caaab....','.caaab....','..cabd....','....d.....','.....d....','......d...','.......d..','........d.'],
chest:['.cc....cc.','caac..caab','caaaccaaab','.caaaaaab.','.caaaaaab.','.caaaaaab.','.caaaaaab.','..bbbbbb..'],
bow:['cc......cc','.ca....ac.','..ca..ac..','...caac...','....bb....','...d..d...','..d....d..','.d......d.'],
disc:['...bbbb...','..baaaab..','.baacaaab.','baacddaaab','baaddaaaab','.baaaaab..','..bbbbb...'],
banner:['bbbbbbbbbb','.caaaaaab.','.cadaadab.','.caaddaab.','.cadaadab.','.caaaaaab.','.caaaaaab.','..caaaab..','...bbbb...'],
template:['.cccccccc.','caaaaaaaab','cadddddaab','cadaaadaab','cadaaadaab','cadddddaab','caaaaaaaab','.bbbbbbbb.'],
core:['cccccccccb','cbbbbbbbbb','cbaaaaaabb','cbaddddabb','cbaddddabb','cbaddddabb','cbaaaaaabb','cbbbbbbbbb','bbbbbbbbbb'],
};
const ITEMS={
'minecraft:emerald':['gem','#41c46a','#1d7a3c','#9cf2b4'],'minecraft:diamond':['gem','#4fd6d0','#1f8784','#b7fbf6'],
'minecraft:emerald_block':['block','#3bb562','#1d7a3c','#8eeaa9','#2a8c4b'],'minecraft:iron_block':['block','#cfd4d9','#868d95','#f2f4f6','#a9b0b7'],
'minecraft:diamond_block':['block','#62dcd6','#2a9792','#c3fcf8','#3fb8b2'],'minecraft:golden_apple':['apple','#f2c73f','#b08514','#fff0a3','#6a8a2c'],
'minecraft:enchanted_golden_apple':['apple','#ffd447','#c0861a','#fff6c4','#c86bff'],'minecraft:tipped_arrow':['arrow','#8d97a6','#4a5260','#d7dde6','#6f8fd6'],
'minecraft:wind_charge':['swirl','#bfe3ff','#6fa0c8','#e8f6ff'],'minecraft:ominous_bottle':['bottle','#5e3a7a','#2c1a3d','#c48dea'],
'minecraft:book':['book','#7a4fd0','#3b2a5c','#c9b0ff','#ffd37a'],'minecraft:diamond_axe':['axe','#5fd8d2','#257f7b','#c3fcf8','#8a6a44'],
'minecraft:diamond_chestplate':['chest','#5fd8d2','#257f7b','#c3fcf8'],'minecraft:crossbow':['bow','#8a6a44','#4d3a24','#c8a77c','#d9d9d9'],
'minecraft:music_disc_creator':['disc','#2b2f3a','#14161c','#6b7486','#e0b34a'],'minecraft:flow_banner_pattern':['banner','#e7dcc4','#9c8f74','#fffaf0','#4fa3c9'],
'minecraft:flow_armor_trim_smithing_template':['template','#3f6f86','#203a47','#7fb6cf','#9fe0ff'],'minecraft:heavy_core':['core','#3a3f4a','#1a1d23','#6b7280','#d8b46a'],
};
function icon(id,cls=''){let [shape,a,b,c,d]=ITEMS[id]||['block','#8a929c','#4a5058','#c4c9cf','#6b7280'],rows=SHAPES[shape],pal={a,b,c,d:d||c},rects='';
rows.forEach((row,y)=>{let x=0;while(x<row.length){let ch=row[x],n=1;while(row[x+n]===ch)n++;if(pal[ch])rects+=`<rect x="${x}" y="${y}" width="${n}" height="1" fill="${pal[ch]}"/>`;x+=n;}});
return `<svg class="pixel-icon ${cls}" viewBox="0 0 10 10" shape-rendering="crispEdges" aria-hidden="true">${rects}</svg>`;}

// ---------- Vault cube faces (16x16) ----------
function face(kind){let px='';for(let y=0;y<16;y++)for(let x=0;x<16;x++){let edge=x===0||y===0||x===15||y===15,frame=x<2||y<2||x>13||y>13,fill;
if(edge)fill='#121418';else if(frame)fill=((x===1||x===14)&&(y===1||y===14))?'#9aa3ad':(y<2||x<2)?'#59616c':'#3b4149';
else if(kind!=='top'&&(y===7||y===8))fill=kind==='front'&&(x===7||x===8)?'#0b0c0f':'#4a515b';
else if(kind==='top'?(x===5||x===10||y===5||y===10):(x===4||x===7||x===8||x===11))fill='#1f2329';
else fill='var(--vfx-glow)';px+=`<rect x="${x}" y="${y}" width="1" height="1" style="fill:${fill}"/>`;}
return `<svg viewBox="0 0 16 16" shape-rendering="crispEdges">${px}</svg>`;}
const KEY='<svg viewBox="0 0 12 6" shape-rendering="crispEdges"><path fill="#3d2f4f" d="M0 1h4v4H0z"/><path fill="#9b6bd6" d="M1 2h2v2H1z"/><path fill="#6b4f8f" d="M4 2h8v2H4zM9 4h1v2H9zM11 4h1v1h-1z"/></svg>';

// ---------- Sound (Web Audio, synthesized) ----------
let ctx=null;const soundOn=()=>localStorage.getItem('werkbank-sound')!=='0';
function audio(){if(!soundOn())return null;try{ctx=ctx||new (window.AudioContext||window.webkitAudioContext)();if(ctx.state==='suspended')ctx.resume();return ctx;}catch{return null;}}
function tone(freq,dur,{type='square',vol=.06,to=null,delay=0}={}){let a=audio();if(!a)return;let t=a.currentTime+delay,o=a.createOscillator(),g=a.createGain();o.type=type;o.frequency.setValueAtTime(freq,t);if(to)o.frequency.exponentialRampToValueAtTime(to,t+dur);g.gain.setValueAtTime(vol,t);g.gain.exponentialRampToValueAtTime(.0001,t+dur);o.connect(g).connect(a.destination);o.start(t);o.stop(t+dur+.02);}
function noise(dur,{vol=.12,freq=900,delay=0}={}){let a=audio();if(!a)return;let t=a.currentTime+delay,b=a.createBuffer(1,a.sampleRate*dur,a.sampleRate),d=b.getChannelData(0);for(let i=0;i<d.length;i++)d[i]=(Math.random()*2-1)*(1-i/d.length);let s=a.createBufferSource(),f=a.createBiquadFilter(),g=a.createGain();f.type='lowpass';f.frequency.value=freq;g.gain.value=vol;s.buffer=b;s.connect(f).connect(g).connect(a.destination);s.start(t);}
function hum(dur,gold){let a=audio();if(!a)return()=>{};let t=a.currentTime,o=a.createOscillator(),o2=a.createOscillator(),f=a.createBiquadFilter(),g=a.createGain();o.type='sawtooth';o2.type='square';o.frequency.setValueAtTime(70,t);o.frequency.exponentialRampToValueAtTime(gold?330:220,t+dur);o2.frequency.setValueAtTime(105,t);o2.frequency.exponentialRampToValueAtTime(gold?495:330,t+dur);f.type='lowpass';f.frequency.setValueAtTime(300,t);f.frequency.exponentialRampToValueAtTime(2200,t+dur);g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.05,t+dur*.8);o.connect(f);o2.connect(f);f.connect(g).connect(a.destination);o.start(t);o2.start(t);
return()=>{let n=a.currentTime;g.gain.cancelScheduledValues(n);g.gain.setValueAtTime(g.gain.value,n);g.gain.exponentialRampToValueAtTime(.0001,n+.12);o.stop(n+.15);o2.stop(n+.15);};}
const sfx={clack(){noise(.08,{vol:.18,freq:2500});tone(180,.09,{vol:.05});},turn(){tone(420,.05,{vol:.04});tone(640,.05,{vol:.04,delay:.06});},
boom(){noise(.5,{vol:.25,freq:700});tone(130,.45,{type:'sine',vol:.2,to:38});},
pop(rare){tone(rare?780:520,.11,{type:'triangle',vol:.08,to:rare?1320:780});},
core(){[523,659,784,1047,1319].forEach((f,i)=>tone(f,.5,{type:'triangle',vol:.07,delay:i*.09}));tone(65,.9,{type:'sine',vol:.18,to:45});}};

// ---------- Particles ----------
let canvas,c2,parts=[],raf=0,ambient=0,origin={x:0,y:0};
function sizeCanvas(){let r=devicePixelRatio||1;canvas.width=innerWidth*r;canvas.height=innerHeight*r;c2.setTransform(r,0,0,r,0,0);}
function spawn(p){if(!reduce.matches&&parts.length<900)parts.push(Object.assign({vx:0,vy:0,g:0,drag:.98,life:0,max:60,size:3,color:'#ff7a4a',fade:true},p));}
function tick(){c2.clearRect(0,0,innerWidth,innerHeight);if(ambient&&Math.random()<ambient){let side=Math.random()<.5?-1:1;spawn({x:origin.x+side*(70+Math.random()*90),y:origin.y+40+Math.random()*40,vx:(Math.random()-.5)*.3,vy:-.4-Math.random()*.6,max:90+Math.random()*60,size:2+Math.random()*2,color:Math.random()<.5?'#ff8a4c':'#ffcf6a',drag:.995});}
parts=parts.filter(p=>{p.life++;if(p.pull){let dx=origin.x-p.x,dy=origin.y-p.y,d=Math.hypot(dx,dy)||1;p.vx+=dx/d*p.pull-dy/d*p.pull*.9;p.vy+=dy/d*p.pull+dx/d*p.pull*.9;if(d<14)return false;}
p.vx*=p.drag;p.vy=p.vy*p.drag+p.g;p.x+=p.vx;p.y+=p.vy;let k=1-p.life/p.max;if(k<=0)return false;c2.globalAlpha=p.fade?Math.min(1,k*1.6):1;c2.fillStyle=p.color;let s=p.size*(p.shrink?k:1);c2.fillRect(p.x-s/2,p.y-s/2,s,s);return true;});
c2.globalAlpha=1;raf=requestAnimationFrame(tick);}
function burst(x,y,n,colors,speed=6,g=.12){for(let i=0;i<n;i++){let a=Math.random()*Math.PI*2,v=speed*(.3+Math.random());spawn({x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v-1.5,g,max:50+Math.random()*50,size:2+Math.random()*4,color:colors[i%colors.length],shrink:true});}}
function swirlIn(n,colors){for(let i=0;i<n;i++){let a=Math.random()*Math.PI*2,r=140+Math.random()*120;spawn({x:origin.x+Math.cos(a)*r,y:origin.y+Math.sin(a)*r,pull:.35,drag:.9,max:120,size:2+Math.random()*3,color:colors[i%colors.length]});}}

// ---------- Scene ----------
let root=null,running=null,lastFocus=null;
function build(){root=document.createElement('div');root.className='vfx';root.setAttribute('role','dialog');root.setAttribute('aria-modal','true');root.setAttribute('aria-label','Schatzkammer wird geöffnet');
root.innerHTML=`<canvas class="vfx-canvas" aria-hidden="true"></canvas><div class="vfx-flash" aria-hidden="true"></div><div class="vfx-rays" aria-hidden="true"></div>
<div class="vfx-top"><span class="vfx-title">Unheilvolle Schatzkammer</span><button class="vfx-sound" type="button" aria-pressed="true"></button></div>
<div class="vfx-stage" aria-hidden="true"><div class="vfx-shadow"></div><div class="vfx-body"><div class="vfx-cube"><div class="vfx-face front">${face('front')}<div class="vfx-key">${KEY}</div></div><div class="vfx-face right">${face('side')}</div><div class="vfx-face top">${face('top')}</div></div></div><div class="vfx-shock"></div></div>
<div class="vfx-banner" aria-live="assertive"></div><div class="vfx-loot" aria-live="polite"></div><p class="vfx-summary"></p>
<div class="vfx-controls"><button class="button secondary vfx-skip" type="button">Überspringen</button><button class="button vfx-again" type="button" hidden>Nochmal öffnen</button><button class="button secondary vfx-close" type="button" hidden>Schließen</button></div>`;
document.body.appendChild(root);canvas=root.querySelector('canvas');c2=canvas.getContext('2d');sizeCanvas();addEventListener('resize',sizeCanvas);
let snd=root.querySelector('.vfx-sound'),paint=()=>{snd.textContent=soundOn()?'🔊 Ton an':'🔇 Ton aus';snd.setAttribute('aria-pressed',String(soundOn()));};paint();
snd.onclick=()=>{localStorage.setItem('werkbank-sound',soundOn()?'0':'1');paint();};
root.querySelector('.vfx-skip').onclick=()=>running&&(running.skip=true);
root.querySelector('.vfx-close').onclick=close;
root.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();running?running.skip=true:close();}else if(e.key==='Tab'){let f=[...root.querySelectorAll('button:not([hidden])')],i=f.indexOf(document.activeElement);if(e.shiftKey&&i<=0){e.preventDefault();f[f.length-1].focus();}else if(!e.shiftKey&&i===f.length-1){e.preventDefault();f[0].focus();}}});}
function close(){if(!root)return;cancelAnimationFrame(raf);raf=0;parts=[];ambient=0;removeEventListener('resize',sizeCanvas);root.classList.add('closing');let r=root;root=null;setTimeout(()=>r.remove(),250);document.documentElement.classList.remove('vfx-open');running=null;if(lastFocus?.isConnected)lastFocus.focus();onClose?.();}
let onClose=null,again=null;

function cubeCenter(){let r=root.querySelector('.vfx-cube').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};}
async function scene(result){let run={skip:false};running=run;let gold=result.cores>0,multi=result.times>1,stage=root,loot=root.querySelector('.vfx-loot'),banner=root.querySelector('.vfx-banner');
stage.className='vfx';stage.classList.toggle('gold',gold);loot.innerHTML='';banner.textContent='';banner.className='vfx-banner';root.querySelector('.vfx-summary').textContent='';
['.vfx-again','.vfx-close'].forEach(s=>root.querySelector(s).hidden=true);let skip=root.querySelector('.vfx-skip');skip.hidden=false;skip.focus({preventScroll:true});
let items=[...result.items].sort((a,b)=>(a.item==='minecraft:heavy_core')-(b.item==='minecraft:heavy_core')||b.chance-a.chance);
const step=async ms=>{if(!run.skip&&!reduce.matches)await wait(ms);};
origin=cubeCenter();ambient=.25;
stage.classList.add('intro');await step(450);
stage.classList.add('insert');await step(180);sfx.clack();await step(380);
stage.classList.add('turn');sfx.turn();await step(220);
let stopHum=run.skip?()=>{}:hum((multi?.9:gold?2.1:1.4),gold);stage.classList.add('charge');
let chargeMs=multi?900:gold?2100:1400,t0=performance.now();
while(!run.skip&&!reduce.matches&&performance.now()-t0<chargeMs){origin=cubeCenter();let k=(performance.now()-t0)/chargeMs;swirlIn(2+Math.floor(k*5),gold&&k>.5?['#ffe08a','#ffb547','#fff4c8']:['#ff7a4a','#ff4d3a','#ffc06a']);
if(gold&&k>.5)stage.classList.add('goldshift');await wait(50);}
stopHum();stage.classList.remove('charge','insert','turn');stage.classList.add('open');origin=cubeCenter();
if(!run.skip){sfx.boom();burst(origin.x,origin.y,reduce.matches?0:90,gold?['#fff4c8','#ffd36a','#ffb547']:['#ffd0a0','#ff8a4c','#ffffff'],7);}
stage.classList.add('flash');setTimeout(()=>stage.classList.remove('flash'),350);await step(380);
let gap=multi?Math.max(60,900/items.length):Math.max(260,1600/items.length);
for(const it of items){let core=it.item==='minecraft:heavy_core',rare=core||it.chance<.1;
if(core&&!run.skip){await step(multi?250:650);stage.classList.add('shake');sfx.core();setTimeout(()=>stage.classList.remove('shake'),700);stage.classList.add('rays');}
let el=document.createElement('div');el.className='vfx-item'+(core?' core':rare?' rare':'');el.innerHTML=`${icon(it.item)}<strong>${esc(it.name)}</strong>${it.detail?`<small>${esc(it.detail)}</small>`:''}<b>× ${it.count.toLocaleString('de-DE')}</b>`;loot.appendChild(el);
if(!run.skip&&!reduce.matches){let r=el.getBoundingClientRect(),c=cubeCenter(),dx=c.x-(r.left+r.width/2),dy=c.y-(r.top+r.height/2);
el.animate([{transform:`translate(${dx}px,${dy}px) scale(.2) rotate(-25deg)`,opacity:0},{transform:`translate(${dx*.45}px,${dy*.55-90}px) scale(.8) rotate(8deg)`,opacity:1,offset:.55},{transform:'none',opacity:1}],{duration:core?900:520,easing:'cubic-bezier(.2,.8,.3,1)'});
sfx.pop(rare);setTimeout(()=>{if(!root)return;let r2=el.getBoundingClientRect();burst(r2.left+r2.width/2,r2.top+r2.height/2,core?140:rare?28:8,core?['#ffe08a','#ffb547','#fff4c8','#d8b46a']:rare?['#9fffd9','#81d8bd','#ffffff']:['#ffd0a0','#ffffff'],core?8:3.5,core?.15:.08);},core?880:500);}
if(core){banner.textContent=result.cores>1?`${result.cores}× HEAVY CORE!`:'HEAVY CORE!';banner.classList.add('show');}
await step(gap);}
ambient=.12;stage.classList.add('done');skip.hidden=true;let sum=root.querySelector('.vfx-summary');
sum.textContent=multi?`${result.times} Öffnungen · ${result.cores?result.cores+'× Heavy Core':'kein Heavy Core'}`:result.cores?`Glückwunsch! Das passiert nur in ${(result.chance*100).toLocaleString('de-DE',{maximumFractionDigits:1})} % der Öffnungen.`:'Kein Heavy Core dieses Mal.';
let ag=root.querySelector('.vfx-again');ag.hidden=!again;root.querySelector('.vfx-close').hidden=false;(again?ag:root.querySelector('.vfx-close')).focus({preventScroll:true});running=null;}
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function play(result,opts={}){onClose=opts.onClose||null;again=opts.again||null;lastFocus=document.activeElement;
if(!root){build();document.documentElement.classList.add('vfx-open');raf=requestAnimationFrame(tick);}
root.querySelector('.vfx-again').onclick=()=>{let next=again&&again();if(next)scene(next);};
await scene(result);}
window.VaultFX={play,icon,active:()=>!!root};
})();
