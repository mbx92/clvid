import {useId} from 'react';

export type VisualKind = 'none'|'coffee_compare'|'coffee_flat'|'coffee_pair'|'coffee_separate'|'coffee_peaberry'|'coffee_reveal'|'diagram'|'comparison'|'steps';
export type VisualIcon = 'bean'|'cup'|'leaf'|'water'|'sun'|'person'|'box'|'check'|'question';
export type StoryVisual = {kind: VisualKind; items: {icon: VisualIcon; label: string}[]; motion: 'gentle'|'still'; reveal_ms: number};
const clamp = (x: number) => Math.max(0, Math.min(1, x));
const ease = (x: number) => 1 - (1-clamp(x)) ** 3;
const ink = '#293D34', paper = '#F5EFE3';

function Bean({x, y, round=false, side=false, seed=false, angle=0, flip=false, scale=1}: {x:number; y:number; round?:boolean; side?:boolean; seed?:boolean; angle?:number; flip?:boolean; scale?:number}) {
  const fill = seed ? '#D9C58E' : '#784B30', light = seed ? '#F4E5B9' : '#AD7750', dark = seed ? '#A58D56' : '#40291E';
  return <g transform={`translate(${x} ${y}) rotate(${angle}) scale(${flip ? -scale : scale} ${scale})`}>
    {side ? <path d="M-52-83 L-52 83 C56 91 98 20 62-48 C39-78-5-91-52-83Z" fill={fill} stroke={dark} strokeWidth="5"/>
      : round ? <ellipse rx="77" ry="83" fill={fill} stroke={dark} strokeWidth="5"/>
      : <path d="M10-106 C-62-109-94-33-71 42 C-45 122 22 129 64 54 C111-31 69-102 10-106Z" fill={fill} stroke={dark} strokeWidth="5"/>}
    {side ? <path d="M-38-68 L-38 68" stroke={light} strokeWidth="8" fill="none" strokeLinecap="round"/>
      : <><path d={round ? 'M-5-65 C-38-20 27 7 7 64' : 'M7-88 C-36-31 33 9-7 89'} stroke={dark} strokeWidth="12" fill="none" strokeLinecap="round"/><path d={round ? 'M9-62 C-17-22 42 16 20 60' : 'M21-82 C-15-27 50 15 8 87'} stroke={light} strokeWidth="5" fill="none" strokeLinecap="round"/></>}
    <path d={side ? 'M-10-63 Q51-58 51-12' : 'M-39-55 Q-62-21-45 16'} stroke={light} strokeWidth="8" opacity=".55" fill="none" strokeLinecap="round"/>
  </g>;
}

function Caption({text,y=540}: {text:string;y?:number}) {return <text x="400" y={y} fill={ink} textAnchor="middle" fontSize="27" fontWeight="600">{text}</text>;}

function Coffee({visual, seconds, prefix}: {visual:StoryVisual;seconds:number;prefix:string}) {
  const moving = visual.motion !== 'still';
  const k = visual.kind;
  const reveal = k === 'coffee_reveal' && seconds * 1000 >= visual.reveal_ms;
  const drop = (delay:number) => moving ? -310 * (1 - ease((seconds-delay)/.65)) : 0;
  const turn = moving ? Math.sin(seconds * 1.5) * 7 : 0;
  if (k === 'coffee_compare' || k === 'coffee_reveal') return <>
    <ellipse cx="400" cy="330" rx="315" ry="175" fill="#D8CEBB" opacity=".6"/>
    <ellipse cx="400" cy="300" rx="320" ry="185" fill="#FFFDFA" stroke="#DED6C9" strokeWidth="5"/>
    <ellipse cx="400" cy="300" rx="270" ry="145" fill="none" stroke="#E8E1D7" strokeWidth="3"/>
    <g opacity={reveal ? .4 : 1}><ellipse cx="260" cy="350" rx="80" ry="23" fill="#BFB5A5" opacity=".5"/><Bean x={260} y={280+drop(0)} angle={-22}/></g>
    <ellipse cx="535" cy="349" rx="75" ry="21" fill="#BFB5A5" opacity=".5"/>
    {reveal && <ellipse cx="535" cy="283" rx="105" ry="110" fill="none" stroke="#63864C" strokeWidth="7" strokeDasharray="12 8"/>}
    <Bean x={535} y={285+drop(.2)} round angle={reveal ? turn : 15}/>
    <text x="260" y="455" textAnchor="middle" fill={ink} fontSize="36" fontWeight="700">A</text>
    <text x="535" y="455" textAnchor="middle" fill={ink} fontSize="36" fontWeight="700">B</text>
    <Caption text={reveal ? 'B · Peaberry' : 'A atau B?'}/>
  </>;
  if (k === 'coffee_flat') {
    const transition = moving ? ease((seconds-.6)/.8) : 1;
    return <><ellipse cx="400" cy="415" rx="170" ry="35" fill="#D8CEBB"/>
      <g opacity={1-transition}><Bean x={400} y={270} scale={1.5} angle={-20}/></g>
      <g opacity={transition}><Bean x={405} y={270} side angle={turn} scale={1.5}/>
        <path d="M180 270H300 M280 255L300 270 280 285" fill="none" stroke="#9B6340" strokeWidth="5" strokeLinecap="round"/>
        <text x="105" y="235" fill={ink} fontSize="24">Sisi rata</text></g>
      <Caption text="Biji biasa · tampak samping"/>
    </>;
  }
  const separate = k === 'coffee_separate';
  const one = k === 'coffee_peaberry';
  const separation = separate ? (moving ? ease((seconds-.4)/1.8) : 1) : 0;
  return <>
    <defs><linearGradient id={`${prefix}-fruit`} x1="0" y1="0" x2="1" y2="1"><stop stopColor="#CB5B47"/><stop offset="1" stopColor="#9C352F"/></linearGradient></defs>
    <g opacity={1-separation*.75}>
      <path d="M395 112Q388 66 418 54" stroke="#657846" strokeWidth="12" fill="none" strokeLinecap="round"/>
      <path d="M410 76Q490 20 515 79Q457 119 410 76Z" fill="#6F8950"/>
      <ellipse cx="400" cy="285" rx="210" ry="190" fill={`url(#${prefix}-fruit)`}/>
      <ellipse cx="400" cy="285" rx="178" ry="160" fill="#F3D7A9" stroke="#E9B988" strokeWidth="6"/>
      <ellipse cx="400" cy="285" rx="148" ry="136" fill="#FAEACB"/>
    </g>
    {one ? <Bean x={400} y={285} round seed scale={1.4} angle={turn}/>
      : <><Bean x={337-separation*110} y={285} side seed flip scale={1.28}/><Bean x={463+separation*110} y={285} side seed scale={1.28}/>
        <text x={337-separation*110} y="300" fill={ink} textAnchor="middle" fontSize="35" fontWeight="700">1</text>
        <text x={463+separation*110} y="300" fill={ink} textAnchor="middle" fontSize="35" fontWeight="700">2</text>
        {separate && <path d="M355 440L310 440M320 430L310 440 320 450 M445 440L490 440M480 430L490 440 480 450" stroke={ink} strokeWidth="4" fill="none"/>}</>}
    <Caption text={one ? 'Satu biji berkembang · Peaberry' : separate ? 'Sisi rata saling berhadapan' : 'Penampang buah · dua biji'}/>
  </>;
}

function Icon({name}: {name:VisualIcon}) {
  if(name === 'bean') return <Bean x={0} y={0} scale={.48}/>;
  return <g fill="none" stroke={ink} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round">
    {name === 'cup' ? <><path d="M-45-25H35V18Q35 45-5 45T-45 18Z" fill="#FFFDFA"/><path d="M35-20Q78-22 65 15Q55 30 35 25 M-55 55H49 M-20-45Q-32-60-15-75 M10-45Q-2-60 15-75"/></>
      : name === 'leaf' ? <><path d="M-42 40Q-70-35 53-57Q77 48-42 40Z" fill="#AAC384"/><path d="M-53 55L28-25"/></>
      : name === 'water' ? <path d="M0-67Q-82 20-36 47Q0 78 36 47Q82 20 0-67Z" fill="#9DCBD0"/>
      : name === 'sun' ? <><circle r="31" fill="#F4D680"/>{Array.from({length:8},(_,i)=><path key={i} d="M0-48V-64" transform={`rotate(${i*45})`}/>)}</>
      : name === 'person' ? <><circle cy="-32" r="23" fill="#E7BA94"/><path d="M-48 60V35Q-48 0 0 0T48 35V60Z" fill="#AEC4B7"/></>
      : name === 'check' ? <><circle r="59" fill="#C8D9AE"/><path d="M-30 0L-7 25 32-25"/></>
      : name === 'question' ? <><circle r="59" fill="#ECD9AB"/><path d="M-20-22Q-20-45 5-42Q40-36 15-8L0 5V15"/><circle cy="34" r="3" fill={ink}/></>
      : <><path d="M-53-32L0-57 53-32V37L0 62-53 37Z" fill="#DCC6A2"/><path d="M-53-32L0-7 53-32 M0-7V62 M-28-45L25-20"/></>}
  </g>;
}

function labelLines(label:string, limit:number) {
  const lines:string[] = [''];
  const words = label.split(/\s+/).flatMap(word => {
    const chars = Array.from(word), parts:string[] = [];
    for (let i=0;i<chars.length;i+=limit) parts.push(chars.slice(i,i+limit).join(''));
    return parts;
  });
  for (const word of words) {
    if (Array.from(lines[lines.length-1]).length + Array.from(word).length + 1 > limit && lines[lines.length-1]) lines.push(word);
    else lines[lines.length-1] = `${lines[lines.length-1]} ${word}`.trim();
  }
  return lines;
}

export function StoryIllustration({visual, frame, fps, accent}: {visual:StoryVisual;frame:number;fps:number;accent:string}) {
  const prefix = useId().replace(/:/g,'_');
  const seconds = frame/fps;
  const items = visual.items.length ? visual.items : [{icon:'question' as const,label:'Visual adegan'}];
  const n = items.length;
  return <svg data-story-visual={visual.kind} viewBox="0 0 800 600" role="img" aria-label={`Ilustrasi ${visual.kind}`} style={{width:'100%',height:'100%',fontFamily:'Clipper Noto Sans'}}>
    <rect x="8" y="8" width="784" height="584" rx="42" fill={paper}/>
    {visual.kind.startsWith('coffee_') ? <Coffee visual={visual} seconds={seconds} prefix={prefix}/>
      : <>{visual.kind === 'steps' && n > 1 && <path d="M110 270H690" stroke="#B5C2AD" strokeWidth="5" strokeDasharray="10 10"/>}
        {items.map((item,i) => {
          const margin = n === 2 ? 210 : n === 3 ? 150 : 110;
          const x = n === 1 ? 400 : margin + i * (800-margin*2)/(n-1);
          const size = n === 1 ? 1.7 : n === 2 ? 1.2 : .85;
          const appear = visual.motion === 'still' ? 1 : ease((seconds-i*.18)/.65);
          return <g key={i} transform={`translate(${x} ${270+(1-appear)*25})`} opacity={appear}>
            <circle r={n===1?145:90} fill="#FFFDFA" stroke="#DFD9CC" strokeWidth="2"/>
            <circle r={n===1?162:95} fill="none" stroke={accent} strokeWidth="6"/>
            <g transform={`scale(${size})`}><Icon name={item.icon}/></g>
            {visual.kind === 'steps' && <g transform="translate(0 -135)"><circle r="22" fill={ink}/><text y="8" textAnchor="middle" fill="white" fontSize="22">{i+1}</text></g>}
            {labelLines(item.label,n>2?12:18).map((line,j)=><text key={j} y={(n===1?220:145)+j*29} textAnchor="middle" fill={ink} fontWeight="600" fontSize={n>2?22:27}>{line}</text>)}
          </g>;
        })}
      </>}
  </svg>;
}
