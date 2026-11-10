(function(){
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- floating embers (canvas) ---- */
  const cv = document.getElementById("embers");
  if (cv && !reduce) {
    const ctx = cv.getContext("2d");
    let W, H, parts = [];
    const resize = () => { W = cv.width = innerWidth; H = cv.height = innerHeight; };
    resize(); addEventListener("resize", resize);
    const make = (fresh) => ({
      x: Math.random()*W, y: fresh ? H + 10 : Math.random()*H,
      r: Math.random()*2.2 + .6, vy: Math.random()*.9 + .3, vx: (Math.random()-.5)*.4,
      a: Math.random()*.7 + .3, t: Math.random()*6
    });
    for (let i = 0; i < 70; i++) parts.push(make(false));
    (function loop(){
      ctx.clearRect(0,0,W,H);
      parts.forEach((p,i) => {
        p.y -= p.vy; p.t += .03; p.x += p.vx + Math.sin(p.t)*.4; p.a -= .0008;
        if (p.y < -10 || p.a <= 0) parts[i] = make(true);
        const g = ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,p.r*5);
        g.addColorStop(0, `rgba(255,170,70,${p.a})`); g.addColorStop(.4, `rgba(224,42,42,${p.a*.5})`); g.addColorStop(1, "rgba(224,42,42,0)");
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x,p.y,p.r*5,0,6.283); ctx.fill();
      });
      requestAnimationFrame(loop);
    })();
  }

  /* ---- 3D tilt on cards ---- */
  if (!reduce) {
    document.querySelectorAll(".tilt").forEach(el => {
      el.addEventListener("mousemove", e => {
        const r = el.getBoundingClientRect();
        const x = (e.clientX - r.left)/r.width - .5, y = (e.clientY - r.top)/r.height - .5;
        el.style.setProperty("--ry", (x*5).toFixed(2) + "deg");
        el.style.setProperty("--rx", (-y*4).toFixed(2) + "deg");
      });
      el.addEventListener("mouseleave", () => { el.style.setProperty("--rx","0deg"); el.style.setProperty("--ry","0deg"); });
    });
  }

  /* ---- file picker: show chosen name, drag & drop, size check ---- */
  const input = document.getElementById("fileInput"), drop = document.getElementById("dropzone"), label = document.getElementById("fileLabel");
  if (input) {
    const show = () => {
      const f = input.files[0];
      if (!f) return;
      if (f.size > 40*1024*1024) { alert("File is larger than 40 MB."); input.value = ""; label.textContent = "Choose or drop a file"; return; }
      label.textContent = f.name + " (" + (f.size/1048576).toFixed(2) + " MB)";
    };
    input.addEventListener("change", show);
    ["dragenter","dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("drag"); }));
    ["dragleave","drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("drag"); }));
    drop.addEventListener("drop", e => { if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; show(); } });
  }
})();
