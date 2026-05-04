import base64
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from db import migrate_to_head
from auth import require_auth
from api.routers import properties, apartments, tenants, contracts, payments

app = FastAPI(
    title="Landlord System API",
    description="REST API for the Hausverwaltung — powers the Streamlit UI and future frontends.",
    version="1.0.0",
)

# CORS — allow Streamlit (8501) and future Next.js (3000) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",   # Streamlit dev
        "http://localhost:3000",   # Next.js dev (future)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers — all /api/* endpoints require authentication
_auth = [Depends(require_auth)]
app.include_router(properties.router, prefix="/api", dependencies=_auth)
app.include_router(apartments.router, prefix="/api", dependencies=_auth)
app.include_router(tenants.router,    prefix="/api", dependencies=_auth)
app.include_router(contracts.router,  prefix="/api", dependencies=_auth)
app.include_router(payments.router,   prefix="/api", dependencies=_auth)


_SIGNATURE_PAD_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 4px; font-family: sans-serif; background: #fff;
         height: 100vh; overflow: hidden; }
  #wrap { display: flex; flex-direction: column; gap: 6px; height: 100%; }
  canvas {
    display: block; width: 100%; flex: 1; min-height: 60px;
    border: 1px solid #ccc; border-radius: 4px;
    background: #fff; cursor: crosshair; touch-action: none;
  }
  .btns { display: flex; gap: 8px; flex-wrap: wrap; flex-shrink: 0; }
  button { padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
  #btn-save  { background: #4CAF50; color: #fff; }
  #btn-undo  { background: #2196F3; color: #fff; }
  #btn-clear { background: #e0e0e0; color: #333; }
  #btn-undo:disabled, #btn-clear:disabled { opacity: 0.4; cursor: default; }
  #msg { font-size: 13px; min-height: 18px; flex-shrink: 0; }
</style>
</head>
<body>
<div id="wrap">
  <canvas id="sig" width="600" height="160"></canvas>
  <div class="btns">
    <button id="btn-save">Save Signature</button>
    <button id="btn-undo" disabled>Undo</button>
    <button id="btn-clear">Clear</button>
  </div>
  <div id="msg"></div>
</div>
<script>
const canvas = document.getElementById('sig');
const ctx    = canvas.getContext('2d');
ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.strokeStyle = '#000';

// ── History for undo ───────────────────────────────────────────────────────
const MAX_HIST = 30;
const history  = [];

function snapshot() {
  history.push(ctx.getImageData(0, 0, canvas.width, canvas.height));
  if (history.length > MAX_HIST) history.shift();
  document.getElementById('btn-undo').disabled = history.length <= 1;
}

function undo() {
  if (history.length <= 1) return;
  history.pop();
  ctx.putImageData(history[history.length - 1], 0, 0);
  document.getElementById('btn-undo').disabled = history.length <= 1;
}

// ── Initialise canvas with white background ────────────────────────────────
function fillWhite() {
  ctx.save();
  ctx.globalCompositeOperation = 'destination-over';
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}
fillWhite();
snapshot(); // blank state is the base of history

// ── Drawing ────────────────────────────────────────────────────────────────
let drawing = false;

function pos(e) {
  const r = canvas.getBoundingClientRect();
  const sx = canvas.width / r.width, sy = canvas.height / r.height;
  const src = e.touches ? e.touches[0] : e;
  return [(src.clientX - r.left) * sx, (src.clientY - r.top) * sy];
}

canvas.addEventListener('mousedown',  e => { drawing = true; ctx.beginPath(); ctx.moveTo(...pos(e)); });
canvas.addEventListener('mousemove',  e => { if (!drawing) return; ctx.lineTo(...pos(e)); ctx.stroke(); });
canvas.addEventListener('mouseup',    () => { if (drawing) { drawing = false; snapshot(); } });
canvas.addEventListener('mouseleave', () => { if (drawing) { drawing = false; snapshot(); } });
canvas.addEventListener('touchstart', e => { e.preventDefault(); drawing = true; ctx.beginPath(); ctx.moveTo(...pos(e)); }, {passive: false});
canvas.addEventListener('touchmove',  e => { e.preventDefault(); if (!drawing) return; ctx.lineTo(...pos(e)); ctx.stroke(); }, {passive: false});
canvas.addEventListener('touchend',   () => { if (drawing) { drawing = false; snapshot(); } });

document.getElementById('btn-undo').addEventListener('click', undo);

document.getElementById('btn-clear').addEventListener('click', () => {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  fillWhite();
  history.length = 0;
  snapshot(); // reset history to the fresh blank state
  document.getElementById('msg').textContent = '';
});

// ── Export: crop to content bounding box ──────────────────────────────────
function cropDataUrl() {
  const w = canvas.width, h = canvas.height;
  const d = ctx.getImageData(0, 0, w, h).data;
  let x0 = w, x1 = 0, y0 = h, y1 = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      if (d[i] < 245 || d[i+1] < 245 || d[i+2] < 245) {
        if (x < x0) x0 = x; if (x > x1) x1 = x;
        if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
  }
  if (x1 < x0) return canvas.toDataURL('image/png');
  const pad = 12;
  x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad);
  x1 = Math.min(w, x1 + pad); y1 = Math.min(h, y1 + pad);
  const tmp = document.createElement('canvas');
  tmp.width = x1 - x0; tmp.height = y1 - y0;
  const tc = tmp.getContext('2d');
  tc.fillStyle = '#fff'; tc.fillRect(0, 0, tmp.width, tmp.height);
  tc.drawImage(canvas, x0, y0, tmp.width, tmp.height, 0, 0, tmp.width, tmp.height);
  return tmp.toDataURL('image/png');
}

// ── Save ──────────────────────────────────────────────────────────────────
document.getElementById('btn-save').addEventListener('click', async () => {
  const msg = document.getElementById('msg');
  msg.style.color = '#333';
  msg.textContent = 'Saving…';
  try {
    const res = await fetch('/api/signature', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({data_url: cropDataUrl()}),
    });
    if (res.ok) {
      msg.style.color = 'green';
      msg.textContent = 'Saved!';
    } else {
      msg.style.color = 'red';
      msg.textContent = 'Error ' + res.status + ': ' + await res.text();
    }
  } catch (err) {
    msg.style.color = 'red';
    msg.textContent = 'Request failed: ' + err.message;
  }
});
</script>
</body>
</html>"""


@app.get("/api/signature", tags=["Files"])
def get_signature():
    """Return the current signature PNG file."""
    dest = Path("pdf/signature.png")
    if not dest.exists():
        raise HTTPException(status_code=404, detail="No signature on file")
    return FileResponse(dest, media_type="image/png")


@app.get("/api/signature-pad", tags=["Files"], response_class=HTMLResponse)
def signature_pad():
    """Serve the signature drawing pad (embedded as an iframe in Streamlit)."""
    return HTMLResponse(_SIGNATURE_PAD_HTML)


class SignaturePayload(BaseModel):
    data_url: str  # "data:image/png;base64,<b64>"


@app.post("/api/signature", tags=["Files"])
def save_signature(body: SignaturePayload):
    """Save a base64-encoded PNG as the landlord signature file."""
    _, _, b64 = body.data_url.partition(",")
    if not b64:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid data URL")
    dest = Path("pdf/signature.png")
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(base64.b64decode(b64))
    return {"status": "saved"}


@app.on_event("startup")
def startup():
    migrate_to_head()


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
