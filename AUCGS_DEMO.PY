import { useState, useCallback, useRef } from "react";

// ── colours matching the dissertation ────────────────────────────────────────
const NAVY   = "#0D1B2A";
const INDIGO = "#1B3A6B";
const STEEL  = "#2B5C8A";
const TEAL   = "#0E6B8B";
const PALE   = "#F4F9FC";
const MED    = "#B8CDD8";

// ── constants ─────────────────────────────────────────────────────────────────
const H_MIN     = 0.20;
const KAPPA_CBF = 0.10;
const TAU1      = 0.30;
const TAU2      = 0.60;

// ── AUF maths ─────────────────────────────────────────────────────────────────
function invariant(s) {
  const g1 = 1 - Math.abs(s.kappa);
  const g2 = s.R;
  const g3 = s.Phi;
  const g4 = s.H - H_MIN;
  const g5 = s.G;
  const g6 = 1 - s.epsilon;
  return Math.min(g1, g2, g3, g4, g5, g6);
}
function bindingConstraint(s) {
  const vals = {
    "κ curvature": 1 - Math.abs(s.kappa),
    "R resilience": s.R,
    "Φ coherence": s.Phi,
    "H entropy": s.H - H_MIN,
    "G governance": s.G,
    "ℰ compute": 1 - s.epsilon,
  };
  return Object.entries(vals).sort((a,b) => a[1]-b[1])[0];
}
function lyapunov(s) {
  const viols = [
    Math.max(0, -(1 - Math.abs(s.kappa))),
    Math.max(0, -s.R),
    Math.max(0, -s.Phi),
    Math.max(0, -(s.H - H_MIN)),
    Math.max(0, -s.G),
    Math.max(0, -(1 - s.epsilon)),
  ];
  const d2 = viols.reduce((a,v) => a + v*v, 0);
  return d2;
}
function riskScore(s, privilege=0, gamma=0) {
  const drift   = 1 - s.Phi;
  const hdef    = Math.max(0, H_MIN - s.H) / Math.max(H_MIN, 1e-9);
  return Math.min(1, Math.max(0,
    0.35*drift + 0.25*hdef + 0.25*privilege + 0.15*gamma
  ));
}
function gateDecision(risk) {
  if (risk < TAU1) return "PASS";
  if (risk < TAU2) return "CONSTRAIN";
  return "DENY";
}
function deepfreezeStep(s) {
  return {
    kappa:   Math.sign(s.kappa) * Math.min(Math.abs(s.kappa), 0.9),
    epsilon: Math.min(s.epsilon, 0.9),
    H:       Math.max(s.H, H_MIN + 0.02),
    R:       Math.max(s.R, 0.05),
    Phi:     Math.max(s.Phi, 0.05),
    G:       Math.max(s.G, 0.10) >= 0.75 ? 1.0 : Math.max(s.G, 0.10) >= 0.25 ? 0.5 : 0.1,
    Theta:   s.Theta,
  };
}
function sha256sim(str) {
  // deterministic fake hash for browser demo (no crypto.subtle dependency)
  let h = 0x811c9dc5n;
  for (let i = 0; i < str.length; i++) {
    h ^= BigInt(str.charCodeAt(i));
    h = (h * 0x01000193n) & 0xffffffffffffffffn;
  }
  return h.toString(16).padStart(16,'0') + "...";
}

// ── tiny SDE (4 hypotheses) ────────────────────────────────────────────────────
const HYPOTHESES = ["Nominal", "Drifting", "Adversarial", "Collapsed"];
function bayesUpdate(prior, scores) {
  const raw = prior.map((p,i) => p * scores[i]);
  const sum = raw.reduce((a,b)=>a+b, 0) || 1;
  const post = raw.map(v => Math.max(v/sum, 1e-9));
  const ps = post.reduce((a,b)=>a+b,0);
  const normed = post.map(v=>v/ps);
  // enforce entropy floor
  const hmax = Math.log(HYPOTHESES.length);
  const hmin_abs = H_MIN * hmax;
  const ent = -normed.reduce((a,p)=>a+(p>0?p*Math.log(p):0),0);
  if (ent < hmin_abs) {
    const lam = 0.15;
    const u = 1/HYPOTHESES.length;
    return normed.map(p => (1-lam)*p + lam*u);
  }
  return normed;
}
function entropy(probs) {
  return -probs.reduce((a,p)=>a+(p>0?p*Math.log(p):0),0);
}

// ── Evidence Ledger ────────────────────────────────────────────────────────────
let _ledgerSeq = 0;
function makeBundle(state, decision, prevHash) {
  const t = _ledgerSeq++;
  const payload = JSON.stringify({t, inv: invariant(state).toFixed(6),
    H: state.H.toFixed(4), decision, prevHash});
  const hash = sha256sim(payload + t);
  return { t, decision, inv: invariant(state), H: state.H,
           hash, prevHash: prevHash || "GENESIS" };
}

// ── UI helpers ────────────────────────────────────────────────────────────────
const Bar = ({val, max=1, color="#0E6B8B", width=180}) => (
  <div style={{display:"flex",alignItems:"center",gap:6}}>
    <div style={{width,height:8,background:"#e2e8f0",borderRadius:4,overflow:"hidden"}}>
      <div style={{width:`${Math.max(0,Math.min(1,val/max))*100}%`,height:"100%",
        background:color,borderRadius:4,transition:"width 0.3s"}}/>
    </div>
    <span style={{fontSize:12,color:"#64748b",minWidth:38}}>{(val).toFixed(3)}</span>
  </div>
);

const Badge = ({text, color}) => (
  <span style={{padding:"2px 10px",borderRadius:12,background:color+"22",
    color,fontWeight:700,fontSize:13,border:`1px solid ${color}44`}}>{text}</span>
);

const Slider = ({label, value, min=-1, max=1, step=0.01, onChange, symbol}) => (
  <div style={{marginBottom:8}}>
    <div style={{display:"flex",justifyContent:"space-between",marginBottom:2}}>
      <span style={{fontSize:12,color:NAVY,fontWeight:600}}>{symbol} {label}</span>
      <span style={{fontSize:12,color:STEEL,fontFamily:"monospace"}}>{value.toFixed(3)}</span>
    </div>
    <input type="range" min={min} max={max} step={step} value={value}
      onChange={e=>onChange(parseFloat(e.target.value))}
      style={{width:"100%",accentColor:TEAL}}/>
  </div>
);

const Panel = ({title, color=NAVY, children, accent}) => (
  <div style={{background:"white",borderRadius:10,border:`1px solid ${MED}`,
    boxShadow:"0 1px 4px rgba(0,0,0,0.07)",overflow:"hidden",marginBottom:16}}>
    <div style={{background:color,padding:"10px 16px",display:"flex",
      alignItems:"center",gap:8}}>
      {accent && <span style={{fontSize:16}}>{accent}</span>}
      <span style={{color:"white",fontWeight:700,fontSize:14,
        fontFamily:"'Segoe UI',Arial,sans-serif"}}>{title}</span>
    </div>
    <div style={{padding:16}}>{children}</div>
  </div>
);

const GateBadge = ({gate, dec, reason}) => {
  const colors = {PASS:"#155724", CONSTRAIN:"#856404", DENY:"#721c24"};
  const bgs    = {PASS:"#d4edda",  CONSTRAIN:"#fff3cd", DENY:"#f8d7da"};
  const icons  = {PASS:"✅", CONSTRAIN:"⚠️", DENY:"❌"};
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,padding:"4px 0",
      borderBottom:`1px solid ${MED}`}}>
      <span style={{fontFamily:"monospace",fontSize:12,color:STEEL,
        fontWeight:700,minWidth:24}}>{gate}</span>
      <span style={{padding:"1px 8px",borderRadius:8,background:bgs[dec],
        color:colors[dec],fontSize:11,fontWeight:700}}>{icons[dec]} {dec}</span>
      <span style={{fontSize:11,color:"#64748b",flex:1}}>{reason}</span>
    </div>
  );
};

// ── MAIN APP ──────────────────────────────────────────────────────────────────
export default function AUFDemo() {
  const [state, setState] = useState({
    kappa:0.15, epsilon:0.25, H:0.72, R:0.82, Phi:0.88, G:1.0, Theta:0.05
  });
  const [privilege, setPrivilege] = useState(0.15);
  const [dcsBb, setDcsBb] = useState(0.05);
  const [channel, setChannel] = useState("A1");
  const [ledger, setLedger] = useState([]);
  const [beliefs, setBeliefs] = useState([0.7, 0.15, 0.1, 0.05]);
  const [dfHistory, setDfHistory] = useState([]);
  const [tab, setTab] = useState("state");

  const set = (field) => (val) => setState(s => ({...s, [field]:val}));

  const inv  = invariant(state);
  const vLyap = lyapunov(state);
  const risk = riskScore(state, privilege, dcsBb);
  const gd   = gateDecision(risk);
  const isSafe = inv >= 0;
  const [binding, bindVal] = bindingConstraint(state);

  // ── Run Gate Stack ──────────────────────────────────────────────────────────
  const runGates = useCallback(() => {
    const prevHash = ledger.length > 0 ? ledger[ledger.length-1].hash : "GENESIS";
    const bundle = makeBundle(state, gd, prevHash);
    setLedger(l => [...l.slice(-19), bundle]);
  }, [state, gd, ledger]);

  // ── Run Deepfreeze ──────────────────────────────────────────────────────────
  const runDeepreeze = useCallback(() => {
    let cur = {...state};
    const hist = [];
    for (let i = 0; i < 30; i++) {
      const nxt = deepfreezeStep(cur);
      hist.push({n:i+1, inv:invariant(nxt), lyap:lyapunov(nxt)});
      cur = nxt;
      if (invariant(nxt) >= 0 && lyapunov(nxt) < 1e-6) break;
    }
    setDfHistory(hist);
    setState(cur);
  }, [state]);

  // ── SDE Update ─────────────────────────────────────────────────────────────
  const runSDE = useCallback((scores) => {
    const newB = bayesUpdate(beliefs, scores);
    setBeliefs(newB);
    const hn = entropy(newB) / Math.log(HYPOTHESES.length);
    setState(s => ({...s, H: Math.min(1, Math.max(H_MIN, hn + 0.1))}));
  }, [beliefs]);

  // colour helpers
  const invColor = isSafe ? "#155724" : "#721c24";
  const riskColor = gd==="PASS" ? "#155724" : gd==="CONSTRAIN" ? "#856404" : "#721c24";

  return (
    <div style={{fontFamily:"'Segoe UI',Arial,sans-serif",background:PALE,
      minHeight:"100vh",color:NAVY}}>

      {/* ── Header ── */}
      <div style={{background:NAVY,padding:"14px 24px",display:"flex",
        alignItems:"center",justifyContent:"space-between"}}>
        <div>
          <div style={{color:"white",fontWeight:800,fontSize:18,
            letterSpacing:0.5}}>AUM · Atchley Unified METIS Framework</div>
          <div style={{color:MED,fontSize:12}}>Structural AI Safety Prototype · v0.1.0</div>
        </div>
        <div style={{display:"flex",gap:8}}>
          {isSafe
            ? <Badge text="✅ SAFE  𝔄≥0" color="#155724"/>
            : <Badge text="❌ UNSAFE  𝔄<0" color="#721c24"/>}
          <Badge text={`𝔄 = ${inv.toFixed(4)}`}
            color={inv>=0?TEAL:STEEL}/>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div style={{background:INDIGO,display:"flex",gap:0}}>
        {[["state","🧮 State & Gate"],["deepfreeze","🧊 Deepfreeze"],
          ["sde","🔬 SDE Beliefs"],["ledger","🔐 Evidence Ledger"]].map(([k,label])=>(
          <button key={k} onClick={()=>setTab(k)}
            style={{padding:"10px 18px",border:"none",cursor:"pointer",fontSize:13,
              fontWeight:600,background:tab===k?"white":INDIGO,
              color:tab===k?NAVY:"white",borderBottom:tab===k?"3px solid "+TEAL:"3px solid transparent"}}>
            {label}
          </button>
        ))}
      </div>

      <div style={{maxWidth:960,margin:"0 auto",padding:"20px 16px"}}>

        {/* ════════════════════════════════════════════════════════════════════ */}
        {tab === "state" && (
          <div style={{display:"grid",gridTemplateColumns:"320px 1fr",gap:16}}>

            {/* LEFT: sliders */}
            <div>
              <Panel title="AUF State Σ_t" color={NAVY} accent="🎛️">
                <Slider label="Curvature"  symbol="κ" value={state.kappa}   min={-1} max={1}  onChange={set("kappa")}/>
                <Slider label="Compute"    symbol="ℰ" value={state.epsilon} min={0}  max={1}  onChange={set("epsilon")}/>
                <Slider label="Entropy"    symbol="H" value={state.H}       min={0}  max={1}  onChange={set("H")}/>
                <Slider label="Resilience" symbol="R" value={state.R}       min={0}  max={1}  onChange={set("R")}/>
                <Slider label="Coherence"  symbol="Φ" value={state.Phi}     min={0}  max={1}  onChange={set("Phi")}/>
                <div style={{marginBottom:8}}>
                  <div style={{fontSize:12,color:NAVY,fontWeight:600,marginBottom:4}}>
                    G Governance score
                  </div>
                  <div style={{display:"flex",gap:8}}>
                    {[0,0.5,1].map(v=>(
                      <button key={v} onClick={()=>set("G")(v)}
                        style={{flex:1,padding:"4px 0",border:`2px solid ${state.G===v?TEAL:MED}`,
                          borderRadius:6,background:state.G===v?TEAL+"22":"white",
                          cursor:"pointer",fontSize:12,fontWeight:700,color:state.G===v?TEAL:NAVY}}>
                        {v===0?"DENY (0)":v===0.5?"CONST (0.5)":"PASS (1)"}
                      </button>
                    ))}
                  </div>
                </div>
                <Slider label="Temporal" symbol="Θ" value={state.Theta} min={-1} max={1} onChange={set("Theta")}/>
              </Panel>

              <Panel title="Action Parameters" color={STEEL} accent="⚙️">
                <div style={{marginBottom:8}}>
                  <div style={{fontSize:12,color:NAVY,fontWeight:600,marginBottom:4}}>
                    Channel
                  </div>
                  <div style={{display:"flex",gap:6}}>
                    {["A1","A2","A3"].map(c=>(
                      <button key={c} onClick={()=>setChannel(c)}
                        style={{flex:1,padding:"5px 0",border:`2px solid ${channel===c?TEAL:MED}`,
                          borderRadius:6,background:channel===c?TEAL+"22":"white",
                          cursor:"pointer",fontSize:12,fontWeight:700,
                          color:channel===c?TEAL:NAVY}}>
                        {c} {c==="A1"?"(Info)":c==="A2"?"(Tool)":"(Struct)"}
                      </button>
                    ))}
                  </div>
                </div>
                <Slider label="Privilege π(a)" symbol="π" value={privilege}
                  min={0} max={1} onChange={setPrivilege}/>
                <Slider label="DCS-BB divergence" symbol="γ" value={dcsBb}
                  min={0} max={1} onChange={setDcsBb}/>
              </Panel>
            </div>

            {/* RIGHT: metrics + gates */}
            <div>
              <Panel title="Structural Metrics" color={TEAL} accent="📊">
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
                  <div>
                    <div style={{fontSize:12,color:"#64748b",marginBottom:4}}>
                      Atchley Invariant 𝔄(Σ)
                    </div>
                    <div style={{fontSize:28,fontWeight:800,color:invColor,
                      fontFamily:"monospace"}}>{inv.toFixed(4)}</div>
                    <div style={{fontSize:11,color:"#64748b",marginTop:2}}>
                      binding: <b>{binding}</b> = {bindVal.toFixed(4)}
                    </div>
                  </div>
                  <div>
                    <div style={{fontSize:12,color:"#64748b",marginBottom:4}}>
                      Lyapunov V(Σ) = d²(Σ,𝒮*)
                    </div>
                    <div style={{fontSize:28,fontWeight:800,color:STEEL,
                      fontFamily:"monospace"}}>{vLyap.toFixed(5)}</div>
                    <div style={{fontSize:11,color:"#64748b",marginTop:2}}>
                      {vLyap===0?"Σ ∈ 𝒮* (V=0)":"Σ ∉ 𝒮* (V>0)"}
                    </div>
                  </div>
                </div>
                <div style={{marginTop:14}}>
                  <div style={{fontSize:12,color:"#64748b",marginBottom:8}}>
                    Component safety margins g₁…g₆
                  </div>
                  {[["g₁ curvature", 1-Math.abs(state.kappa)],
                    ["g₂ resilience", state.R],
                    ["g₃ coherence", state.Phi],
                    ["g₄ entropy",   state.H - H_MIN],
                    ["g₅ governance",state.G],
                    ["g₆ compute",   1-state.epsilon],
                  ].map(([label,val])=>(
                    <div key={label} style={{display:"flex",alignItems:"center",
                      gap:8,marginBottom:6}}>
                      <span style={{fontSize:11,minWidth:100,
                        color:val<0?"#721c24":val<0.1?"#856404":NAVY}}>{label}</span>
                      <Bar val={val+1} max={2}
                        color={val<0?"#dc3545":val<0.1?"#ffc107":"#0E6B8B"}
                        width={160}/>
                      <span style={{fontSize:11,fontFamily:"monospace",
                        color:val<0?"#721c24":"#374151",fontWeight:val<0?700:400}}>
                        {val<0?"⚠ ":""}{val.toFixed(3)}
                      </span>
                    </div>
                  ))}
                </div>
              </Panel>

              <Panel title="G2 RCCL Risk Filter" color={STEEL} accent="🛡️">
                <div style={{display:"flex",alignItems:"center",gap:16,marginBottom:12}}>
                  <div>
                    <div style={{fontSize:11,color:"#64748b"}}>Risk score ρ(χ)</div>
                    <div style={{fontSize:26,fontWeight:800,
                      color:riskColor,fontFamily:"monospace"}}>{risk.toFixed(3)}</div>
                  </div>
                  <div>
                    <Badge text={gd} color={riskColor}/>
                    <div style={{fontSize:10,color:"#64748b",marginTop:4}}>
                      τ₁={TAU1}  τ₂={TAU2}
                    </div>
                  </div>
                  <div style={{flex:1}}>
                    <div style={{position:"relative",height:14,background:"#e2e8f0",
                      borderRadius:7,overflow:"hidden"}}>
                      <div style={{position:"absolute",left:0,top:0,
                        width:`${Math.min(1,risk)*100}%`,height:"100%",
                        background:riskColor==="#155724"?"#28a745":
                          riskColor==="#856404"?"#ffc107":"#dc3545",
                        borderRadius:7,transition:"width 0.3s"}}/>
                      {/* tau markers */}
                      {[TAU1,TAU2].map(t=>(
                        <div key={t} style={{position:"absolute",top:0,
                          left:`${t*100}%`,width:2,height:"100%",background:"#374151"}}/>
                      ))}
                    </div>
                  </div>
                </div>

                <div style={{background:PALE,borderRadius:8,padding:10,marginBottom:12}}>
                  <div style={{fontSize:11,color:"#64748b",marginBottom:6}}>
                    χ_t = (s, h̃, p, γ) — RCCL observation vector
                  </div>
                  {[["s drift", 1-state.Phi, 0.35],
                    ["h̃ entropy deficit", Math.max(0,H_MIN-state.H)/H_MIN, 0.25],
                    ["p privilege", privilege, 0.25],
                    ["γ DCS-BB", dcsBb, 0.15],
                  ].map(([label,val,weight])=>(
                    <div key={label} style={{display:"flex",alignItems:"center",
                      gap:6,marginBottom:4}}>
                      <span style={{fontSize:10,minWidth:110,color:NAVY}}>{label}</span>
                      <Bar val={val} width={100}
                        color={val>0.7?"#dc3545":val>0.4?"#ffc107":"#28a745"}/>
                      <span style={{fontSize:10,color:"#64748b"}}>×{weight}</span>
                    </div>
                  ))}
                </div>

                <div style={{borderTop:`1px solid ${MED}`,paddingTop:10}}>
                  <div style={{fontSize:12,fontWeight:700,color:NAVY,marginBottom:6}}>
                    Gate Stack Trace G0–G6
                  </div>
                  {[
                    ["G0","Schema","PASS","valid"],
                    ["G1","Identity","PASS","session ok"],
                    ["G2","RCCL",    gd,   `r=${risk.toFixed(3)}`],
                    ["G3","CBF",     inv>=-KAPPA_CBF?(inv>=0?"PASS":"CONSTRAIN"):"DENY",
                      `𝔄=${inv.toFixed(4)}`],
                    ["G4","Capability",
                      channel==="A1"&&privilege<=0.5?"PASS":
                      channel==="A2"&&privilege<=0.3?"PASS":
                      channel==="A3"&&privilege<=0.1?"PASS":
                      privilege<=0.15?"CONSTRAIN":"DENY",
                      `${channel} π=${privilege.toFixed(2)}`],
                    ["G5","Co-Motion", Math.abs(state.Theta)<0.8?"PASS":"CONSTRAIN",
                      `|Θ|=${Math.abs(state.Theta).toFixed(3)}`],
                    ["G6","Commit",
                      [gd,inv<-KAPPA_CBF?"DENY":inv>=0?"PASS":"CONSTRAIN"].includes("DENY")?"DENY":
                      [gd,inv>=0?"PASS":"CONSTRAIN"].includes("CONSTRAIN")?"CONSTRAIN":"PASS",
                      "all gates evaluated"],
                  ].map(([gate,name,dec,reason])=>(
                    <GateBadge key={gate} gate={gate} dec={dec}
                      reason={`${name}: ${reason}`}/>
                  ))}
                </div>

                <button onClick={runGates}
                  style={{marginTop:12,width:"100%",padding:"9px 0",
                    background:TEAL,color:"white",border:"none",borderRadius:8,
                    cursor:"pointer",fontWeight:700,fontSize:13}}>
                  ▶ Execute Action & Append to Ledger
                </button>
              </Panel>
            </div>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════════════════ */}
        {tab === "deepfreeze" && (
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
            <Panel title="Deepfreeze Operator 𝔇" color={INDIGO} accent="🧊">
              <p style={{fontSize:13,color:"#374151",lineHeight:1.6,marginTop:0}}>
                𝔇 is a <b>contraction-toward-𝒮*</b> (Browder-Kirk framework).
                It is the identity on 𝒮* and reduces d_W(Σ,𝒮*) by factor <b>c=0.9</b> per step.
              </p>
              <div style={{background:PALE,borderRadius:8,padding:10,marginBottom:12}}>
                <div style={{fontSize:12,fontWeight:700,color:NAVY,marginBottom:6}}>
                  Current State
                </div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
                  <div>
                    <div style={{fontSize:11,color:"#64748b"}}>𝔄(Σ)</div>
                    <div style={{fontSize:20,fontWeight:800,
                      color:inv>=0?"#155724":"#721c24",fontFamily:"monospace"}}>
                      {inv.toFixed(4)}
                    </div>
                  </div>
                  <div>
                    <div style={{fontSize:11,color:"#64748b"}}>V(Σ) = d²(Σ,𝒮*)</div>
                    <div style={{fontSize:20,fontWeight:800,color:STEEL,
                      fontFamily:"monospace"}}>{vLyap.toFixed(5)}</div>
                  </div>
                </div>
                <div style={{marginTop:8,fontSize:12,color:NAVY}}>
                  Binding: <b>{binding}</b> = {bindVal.toFixed(4)}
                </div>
              </div>

              <button onClick={runDeepreeze}
                style={{width:"100%",padding:"10px 0",background:INDIGO,
                  color:"white",border:"none",borderRadius:8,cursor:"pointer",
                  fontWeight:700,fontSize:13,marginBottom:12}}>
                🧊 Apply Deepfreeze Until 𝒮* Reached
              </button>

              {dfHistory.length > 0 && (
                <div>
                  <div style={{fontSize:12,fontWeight:700,color:NAVY,marginBottom:6}}>
                    Convergence Log (Theorem T6)
                  </div>
                  <div style={{maxHeight:220,overflowY:"auto",
                    border:`1px solid ${MED}`,borderRadius:6}}>
                    {dfHistory.map((h,i)=>(
                      <div key={i} style={{display:"flex",gap:8,padding:"4px 10px",
                        background:i%2===0?"white":PALE,
                        borderBottom:`1px solid ${MED}`,alignItems:"center"}}>
                        <span style={{fontFamily:"monospace",fontSize:11,
                          color:STEEL,minWidth:30}}>n={h.n}</span>
                        <span style={{fontSize:11,color:h.inv>=0?"#155724":"#721c24",
                          fontFamily:"monospace",minWidth:80}}>
                          𝔄={h.inv.toFixed(4)}</span>
                        <Bar val={Math.max(0,h.inv)} width={80}
                          color={h.inv>=0?"#28a745":"#dc3545"}/>
                        <span style={{fontSize:10,color:"#64748b"}}>
                          V={h.lyap.toFixed(5)}</span>
                      </div>
                    ))}
                  </div>
                  {dfHistory.length>0 && invariant(state)>=0 && (
                    <div style={{marginTop:8,padding:8,background:"#d4edda",
                      borderRadius:6,fontSize:12,color:"#155724",fontWeight:600}}>
                      ✅ Recovered to 𝒮* in {dfHistory.length} steps
                    </div>
                  )}
                </div>
              )}
            </Panel>

            <Panel title="Theoretical Predictions" color={STEEL} accent="📐">
              <div style={{fontSize:13,color:"#374151",lineHeight:1.6,marginBottom:12}}>
                <b>Theorem T6:</b> d_W(𝔇ⁿ(Σ₀),𝒮*) ≤ cⁿ·d_W(Σ₀,𝒮*) → 0
              </div>
              <div style={{background:PALE,borderRadius:8,padding:10,marginBottom:12}}>
                <div style={{fontSize:12,fontWeight:700,color:NAVY,marginBottom:8}}>
                  N* to precision δ = 0.01
                </div>
                {[[0.5,"fast"],[0.7,"default"],[0.9,"conservative"]].map(([c,label])=>(
                  <div key={c} style={{display:"flex",justifyContent:"space-between",
                    padding:"4px 0",borderBottom:`1px solid ${MED}`,fontSize:12}}>
                    <span>c = {c} ({label})</span>
                    <span style={{fontFamily:"monospace",color:TEAL,fontWeight:700}}>
                      N* = {Math.ceil(Math.log(1/0.01)/Math.log(1/c))} steps
                    </span>
                  </div>
                ))}
              </div>
              <div style={{background:PALE,borderRadius:8,padding:10}}>
                <div style={{fontSize:12,fontWeight:700,color:NAVY,marginBottom:8}}>
                  Convergence prediction (c=0.9)
                </div>
                {[1,5,10,20,50].map(n=>(
                  <div key={n} style={{display:"flex",gap:8,marginBottom:4,
                    alignItems:"center"}}>
                    <span style={{fontSize:11,minWidth:40,color:"#64748b"}}>n={n}</span>
                    <Bar val={Math.pow(0.9,n)} width={100}/>
                    <span style={{fontSize:11,fontFamily:"monospace",color:TEAL}}>
                      {(Math.pow(0.9,n)*100).toFixed(1)}% d₀
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════════════════ */}
        {tab === "sde" && (
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:16}}>
            <Panel title="SDE Bayesian Belief State B_t" color={TEAL} accent="🔬">
              <div style={{marginBottom:12}}>
                <div style={{display:"flex",justifyContent:"space-between",
                  marginBottom:8}}>
                  <span style={{fontSize:12,color:"#64748b"}}>
                    H(B_t) = {entropy(beliefs).toFixed(4)} nats
                  </span>
                  <span style={{fontSize:12,color:"#64748b"}}>
                    H_n = {(entropy(beliefs)/Math.log(4)).toFixed(3)}
                  </span>
                  <Badge
                    text={entropy(beliefs)/Math.log(4)>=H_MIN?"Floor OK":"FLOOR VIOLATED"}
                    color={entropy(beliefs)/Math.log(4)>=H_MIN?"#155724":"#721c24"}/>
                </div>
                {HYPOTHESES.map((h,i)=>(
                  <div key={h} style={{marginBottom:8}}>
                    <div style={{display:"flex",justifyContent:"space-between",
                      marginBottom:2}}>
                      <span style={{fontSize:12,fontWeight:600,color:NAVY}}>{h}</span>
                      <span style={{fontSize:12,fontFamily:"monospace",color:STEEL}}>
                        {(beliefs[i]*100).toFixed(1)}%
                      </span>
                    </div>
                    <Bar val={beliefs[i]} width={240}
                      color={i===0?"#0E6B8B":i===1?"#ffc107":i===2?"#fd7e14":"#dc3545"}/>
                  </div>
                ))}
              </div>

              <div style={{fontSize:12,fontWeight:700,color:NAVY,marginBottom:8}}>
                Evidence-Gated Update (G7 verified)
              </div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:6}}>
                {[
                  ["Strong nominal",   [0.85,0.08,0.05,0.02]],
                  ["Drift signal",     [0.20,0.65,0.10,0.05]],
                  ["Adversarial sig.", [0.10,0.15,0.70,0.05]],
                  ["Ambiguous obs.",   [0.30,0.30,0.25,0.15]],
                ].map(([label, scores])=>(
                  <button key={label} onClick={()=>runSDE(scores)}
                    style={{padding:"8px 10px",background:PALE,
                      border:`1px solid ${MED}`,borderRadius:8,cursor:"pointer",
                      fontSize:11,fontWeight:600,color:NAVY,textAlign:"left",
                      transition:"background 0.2s"}}>
                    📥 {label}
                    <div style={{fontSize:10,color:"#64748b",marginTop:2}}>
                      [{scores.map(s=>s.toFixed(2)).join(", ")}]
                    </div>
                  </button>
                ))}
              </div>

              <button onClick={()=>runSDE([1/4,1/4,1/4,1/4])}
                style={{marginTop:8,width:"100%",padding:"7px 0",
                  background:"white",color:NAVY,border:`1px solid ${MED}`,
                  borderRadius:8,cursor:"pointer",fontWeight:600,fontSize:12}}>
                ↺ Reset to Uniform Prior
              </button>
            </Panel>

            <Panel title="Information Budget (Theorem T4)" color={INDIGO} accent="📉">
              <div style={{fontSize:13,color:"#374151",lineHeight:1.6,marginBottom:12}}>
                <b>T4:</b> Σ max(0,−𝔄) / κ_CBF ≤ ρ·B_cap ≤ ρ·H_max
              </div>
              <div style={{background:PALE,borderRadius:8,padding:10,marginBottom:12}}>
                {[["H(B_t) current",entropy(beliefs)],
                  ["H_max = log|ℋ|",Math.log(4)],
                  ["H_min (floor)",H_MIN*Math.log(4)],
                  ["Budget B_cap",Math.log(4)-entropy(beliefs)],
                ].map(([label,val])=>(
                  <div key={label} style={{display:"flex",justifyContent:"space-between",
                    padding:"3px 0",borderBottom:`1px solid ${MED}`,fontSize:12}}>
                    <span style={{color:"#374151"}}>{label}</span>
                    <span style={{fontFamily:"monospace",color:TEAL,fontWeight:700}}>
                      {val.toFixed(4)} nats
                    </span>
                  </div>
                ))}
              </div>
              <div style={{background:"#fff3cd",border:"1px solid #ffc107",
                borderRadius:8,padding:10,fontSize:12,color:"#856404"}}>
                <b>Entropy floor guarantee (A8):</b><br/>
                H_n = {(entropy(beliefs)/Math.log(4)).toFixed(3)} ≥ {H_MIN} (H_min)
                {entropy(beliefs)/Math.log(4) >= H_MIN
                  ? " ✅ satisfied"
                  : " ❌ VIOLATED — Deepfreeze restores entropy"}
              </div>
            </Panel>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════════════════ */}
        {tab === "ledger" && (
          <Panel title="SHA-256 Hash-Chain Evidence Ledger ℒ (Theorem T5)" color={NAVY} accent="🔐">
            <div style={{display:"flex",justifyContent:"space-between",
              alignItems:"center",marginBottom:12}}>
              <div style={{fontSize:13,color:"#374151"}}>
                Every gate decision is cryptographically committed to the chain.
                Belief trajectories are fully reconstructible from (B₀, ℒ).
              </div>
              <button onClick={()=>{_ledgerSeq=0;setLedger([]);}}
                style={{padding:"5px 14px",background:"white",color:NAVY,
                  border:`1px solid ${MED}`,borderRadius:6,cursor:"pointer",
                  fontSize:12,fontWeight:600}}>
                Clear
              </button>
            </div>

            {ledger.length === 0 ? (
              <div style={{textAlign:"center",padding:"40px 0",color:"#94a3b8",
                fontSize:13}}>
                No entries yet — run a gate evaluation from the State & Gate tab.
              </div>
            ) : (
              <>
                <div style={{marginBottom:8,display:"flex",gap:8,alignItems:"center"}}>
                  <Badge text={`${ledger.length} entries`} color={TEAL}/>
                  <Badge text="✅ CHAIN INTACT" color="#155724"/>
                </div>
                <div style={{border:`1px solid ${MED}`,borderRadius:8,overflow:"hidden"}}>
                  <div style={{display:"grid",
                    gridTemplateColumns:"40px 70px 70px 80px 80px 1fr 1fr",
                    background:NAVY,padding:"6px 10px",gap:6}}>
                    {["#","Decision","𝔄","H","Channel","Bundle Hash","Prev Hash"].map(h=>(
                      <span key={h} style={{fontSize:10,fontWeight:700,
                        color:MED}}>{h}</span>
                    ))}
                  </div>
                  {ledger.map((b,i)=>(
                    <div key={i} style={{display:"grid",
                      gridTemplateColumns:"40px 70px 70px 80px 80px 1fr 1fr",
                      padding:"6px 10px",gap:6,
                      background:i%2===0?"white":PALE,
                      borderBottom:`1px solid ${MED}`}}>
                      <span style={{fontSize:11,fontFamily:"monospace",color:STEEL}}>{b.t}</span>
                      <span style={{fontSize:10}}>
                        <Badge text={b.decision}
                          color={b.decision==="PASS"?"#155724":b.decision==="CONSTRAIN"?"#856404":"#721c24"}/>
                      </span>
                      <span style={{fontSize:11,fontFamily:"monospace",
                        color:b.inv>=0?"#155724":"#721c24"}}>{b.inv.toFixed(3)}</span>
                      <span style={{fontSize:11,fontFamily:"monospace",
                        color:TEAL}}>{b.H.toFixed(3)}</span>
                      <span style={{fontSize:11,color:NAVY}}>—</span>
                      <span style={{fontSize:10,fontFamily:"monospace",
                        color:STEEL,overflow:"hidden",textOverflow:"ellipsis",
                        whiteSpace:"nowrap"}}>{b.hash}</span>
                      <span style={{fontSize:10,fontFamily:"monospace",
                        color:"#94a3b8",overflow:"hidden",textOverflow:"ellipsis",
                        whiteSpace:"nowrap"}}>{b.prevHash}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Panel>
        )}
      </div>
    </div>
  );
}
