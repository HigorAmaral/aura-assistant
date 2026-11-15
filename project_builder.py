import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECTS_ROOT = Path.home() / "AURA-Projects"


def is_project_build_intent(text: str) -> bool:
    lower = text.lower()
    verbs = ("faça", "faca", "faz", "fazem", "crie", "criar", "construa", "desenvolva", "gere", "monte", "programar")
    nouns = ("sistema", "site", "app", "aplicativo", "projeto", "plataforma", "cafeteria", "loja", "pdv", "dashboard", "crud", "front e back", "banco de dados")
    return any(v in lower for v in verbs) and any(n in lower for n in nouns)


def _slugify(text: str) -> str:
    lower = text.lower()
    for kw, slug in (
        ("cafeteria", "sistema-cafeteria"),
        ("café", "sistema-cafeteria"),
        ("restaurante", "sistema-restaurante"),
        ("loja", "sistema-loja"),
        ("estoque", "sistema-estoque"),
        ("tarefa", "sistema-tarefas"),
        ("financeiro", "sistema-financeiro"),
        ("clinica", "sistema-clinica"),
        ("clínica", "sistema-clinica"),
    ):
        if kw in lower:
            return slug
    cleaned = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
    return (cleaned[:32] or "projeto-aura")


def _find_free_port(start: int = 8800, end: int = 8899) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return 8800


def _detect_domain(goal: str) -> Dict[str, Any]:
    lower = goal.lower()
    if any(k in lower for k in ("cafeteria", "café", "cafe", "coffee", "padaria")):
        return {
            "title": "Café & Companhia — Sistema de Cafeteria (PDV + Estoque)",
            "subtitle": "Cardápio, Pedidos em Tempo Real, Caixa e Banco SQLite Local",
            "item_label": "Produto do Cardápio",
            "seed_items": [
                ("Espresso Duplo", "Cafés", 8.50, 50),
                ("Cappuccino Italiano", "Cafés", 12.00, 40),
                ("Latte Caramelo", "Cafés", 14.50, 35),
                ("Pão de Queijo Artesanal", "Salgados", 7.00, 60),
                ("Croissant de Manteiga", "Salgados", 11.50, 25),
                ("Bolo de Chocolate Belga", "Doces", 13.00, 20),
                ("Cheesecake Frutas Vermelhas", "Doces", 16.00, 15),
                ("Suco Natural de Laranja", "Bebidas", 10.00, 30),
            ],
            "categories": ["Cafés", "Salgados", "Doces", "Bebidas"],
        }
    return {
        "title": f"Sistema Web Completo — {_slugify(goal).replace('-', ' ').title()}",
        "subtitle": "Frontend + Backend FastAPI + Banco de Dados SQLite Local",
        "item_label": "Item / Produto",
        "seed_items": [
            ("Item Principal A", "Geral", 29.90, 25),
            ("Item Principal B", "Geral", 49.90, 18),
            ("Serviço Premium", "Serviços", 99.00, 10),
            ("Pacote Completo", "Combos", 129.00, 12),
        ],
        "categories": ["Geral", "Serviços", "Combos"],
    }


def scaffold_database_layer(project_dir: Path, goal: str) -> Dict[str, Any]:
    domain = _detect_domain(goal)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "static").mkdir(exist_ok=True)

    db_code = f'''import sqlite3
from pathlib import Path
from typing import Any, Dict, List

DB_PATH = Path(__file__).parent / "app.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                items_json TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Em Preparo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            seed = {domain["seed_items"]!r}
            conn.executemany(
                "INSERT INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)",
                seed,
            )
'''
    (project_dir / "database.py").write_text(db_code, encoding="utf-8")
    return {"file": str(project_dir / "database.py"), "tables": ["products", "orders"], "seed_count": len(domain["seed_items"])}


def scaffold_backend_layer(project_dir: Path, goal: str) -> Dict[str, Any]:
    domain = _detect_domain(goal)
    app_code = f'''import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import get_conn, init_db

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title={domain["title"]!r}, lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / "static"


class ProductIn(BaseModel):
    name: str
    category: str = "Geral"
    price: float
    stock: int = 10


class OrderItemIn(BaseModel):
    product_id: int
    qty: int = 1


class OrderIn(BaseModel):
    customer_name: str = "Cliente Balcão"
    items: List[OrderItemIn]


@app.get("/")
def home():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/products")
def list_products():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM products ORDER BY category, name").fetchall()
        return {{"products": [dict(r) for r in rows]}}


@app.post("/api/products")
def create_product(req: ProductIn):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)",
            (req.name.strip(), req.category.strip(), float(req.price), int(req.stock)),
        )
        return {{"ok": True, "id": cur.lastrowid}}


@app.delete("/api/products/{{prod_id}}")
def delete_product(prod_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (prod_id,))
        return {{"ok": True}}


@app.get("/api/orders")
def list_orders():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 30").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["items"] = json.loads(d.pop("items_json", "[]"))
            result.append(d)
        return {{"orders": result}}


@app.post("/api/orders")
def create_order(req: OrderIn):
    if not req.items:
        raise HTTPException(status_code=400, detail="Adicione ao menos 1 item ao pedido.")
    with get_conn() as conn:
        total = 0.0
        resolved_items = []
        for item in req.items:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (item.product_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Produto {{item.product_id}} não encontrado.")
            qty = max(1, int(item.qty))
            subtotal = round(float(row["price"]) * qty, 2)
            total += subtotal
            resolved_items.append({{"id": row["id"], "name": row["name"], "qty": qty, "price": row["price"], "subtotal": subtotal}})
            conn.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?", (qty, row["id"]))

        cur = conn.execute(
            "INSERT INTO orders (customer_name, items_json, total, status) VALUES (?, ?, ?, ?)",
            (req.customer_name.strip() or "Cliente Balcão", json.dumps(resolved_items, ensure_ascii=False), round(total, 2), "Em Preparo"),
        )
        return {{"ok": True, "id": cur.lastrowid, "total": round(total, 2)}}


@app.post("/api/orders/{{order_id}}/status")
def advance_order(order_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pedido não encontrado.")
        next_status = "Pronto" if row["status"] == "Em Preparo" else "Entregue"
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (next_status, order_id))
        return {{"ok": True, "status": next_status}}


@app.get("/api/stats")
def stats():
    with get_conn() as conn:
        total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        revenue = conn.execute("SELECT COALESCE(SUM(total), 0) FROM orders").fetchone()[0]
        return {{"total_products": total_products, "total_orders": total_orders, "revenue": round(float(revenue), 2)}}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8800"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None, use_colors=False)
'''
    (project_dir / "app.py").write_text(app_code, encoding="utf-8")
    return {"file": str(project_dir / "app.py"), "endpoints": ["/api/products", "/api/orders", "/api/stats"]}


def scaffold_frontend_layer(project_dir: Path, goal: str) -> Dict[str, Any]:
    domain = _detect_domain(goal)
    cat_options = "\n".join([f'<option value="{c}">{c}</option>' for c in domain["categories"]])
    html_code = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{domain["title"]}</title>
  <style>
    :root {{ --bg:#0b0f19; --card:#131a2a; --border:rgba(148,163,184,0.18); --accent:#f59e0b; --green:#10b981; --text:#f8fafc; --muted:#94a3b8; }}
    * {{ box-sizing:border-box; margin:0; padding:0; font-family:Inter, system-ui, sans-serif; }}
    body {{ background:var(--bg); color:var(--text); min-height:100vh; padding:20px; }}
    header {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; padding:16px 20px; background:var(--card); border:1px solid var(--border); border-radius:14px; margin-bottom:18px; }}
    h1 {{ font-size:20px; color:var(--accent); }}
    .subtitle {{ font-size:12px; color:var(--muted); margin-top:3px; }}
    .stats {{ display:flex; gap:12px; }}
    .stat-box {{ background:#0f1523; border:1px solid var(--border); padding:8px 14px; border-radius:10px; font-size:12px; }}
    .stat-box strong {{ display:block; font-size:16px; color:var(--green); }}
    .grid {{ display:grid; grid-template-columns:1.3fr 1fr; gap:16px; }}
    @media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px; }}
    .card h2 {{ font-size:15px; margin-bottom:12px; color:#e2e8f0; }}
    .menu-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(185px, 1fr)); gap:10px; }}
    .prod-card {{ background:#0f1523; border:1px solid var(--border); border-radius:10px; padding:12px; display:flex; flex-direction:column; gap:6px; }}
    .prod-cat {{ font-size:10px; color:var(--accent); text-transform:uppercase; font-weight:700; }}
    .prod-price {{ font-size:15px; font-weight:700; color:var(--green); }}
    button {{ cursor:pointer; border:none; border-radius:8px; padding:8px 12px; font-weight:600; font-size:12px; background:var(--accent); color:#111827; }}
    button.sec {{ background:#1e293b; color:#e2e8f0; border:1px solid var(--border); }}
    button.ok {{ background:var(--green); color:#052e16; }}
    input, select {{ background:#0f1523; border:1px solid var(--border); color:var(--text); padding:8px 10px; border-radius:8px; font-size:12.5px; }}
    .row {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }}
    .order-item {{ display:flex; justify-content:space-between; align-items:center; padding:8px 10px; background:#0f1523; border-radius:8px; margin-bottom:6px; font-size:12.5px; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>{domain["title"]}</h1>
      <div class="subtitle">{domain["subtitle"]} • Gerado pelo Modo Maestro AURA</div>
    </div>
    <div class="stats">
      <div class="stat-box"><span>Produtos</span><strong id="stProds">0</strong></div>
      <div class="stat-box"><span>Pedidos</span><strong id="stOrders">0</strong></div>
      <div class="stat-box"><span>Faturamento</span><strong id="stRev">R$ 0,00</strong></div>
    </div>
  </header>

  <div class="grid">
    <div class="card">
      <h2>Cardápio / Catálogo (SQLite)</h2>
      <div class="row">
        <input id="pName" placeholder="Nome do produto" style="flex:1;" />
        <select id="pCat">{cat_options}</select>
        <input id="pPrice" type="number" step="0.50" placeholder="Preço" style="width:90px;" />
        <input id="pStock" type="number" value="20" placeholder="Estoque" style="width:80px;" />
        <button onclick="addProduct()">+ Adicionar</button>
      </div>
      <div class="menu-grid" id="menuGrid"></div>
    </div>

    <div style="display:flex; flex-direction:column; gap:16px;">
      <div class="card">
        <h2>Novo Pedido (PDV)</h2>
        <div class="row">
          <input id="custName" placeholder="Nome do cliente / Mesa" value="Cliente Balcão" style="flex:1;" />
        </div>
        <div id="cartList" style="margin-bottom:10px; font-size:12.5px; color:var(--muted);">Clique em "+ Pedido" em qualquer item.</div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong style="font-size:15px;">Total: <span id="cartTotal" style="color:var(--green);">R$ 0,00</span></strong>
          <button class="ok" onclick="submitOrder()">Finalizar Pedido</button>
        </div>
      </div>

      <div class="card">
        <h2>Pedidos Recentes</h2>
        <div id="ordersList"></div>
      </div>
    </div>
  </div>

  <script>
    let products = [];
    let cart = {{}};

    function brl(v) {{ return 'R$ ' + Number(v || 0).toFixed(2).replace('.', ','); }}

    async function refreshAll() {{
      const [pRes, oRes, sRes] = await Promise.all([
        fetch('/api/products').then(r => r.json()),
        fetch('/api/orders').then(r => r.json()),
        fetch('/api/stats').then(r => r.json()),
      ]);
      products = pRes.products || [];
      document.getElementById('stProds').textContent = sRes.total_products;
      document.getElementById('stOrders').textContent = sRes.total_orders;
      document.getElementById('stRev').textContent = brl(sRes.revenue);

      document.getElementById('menuGrid').innerHTML = products.map(p => `
        <div class="prod-card">
          <span class="prod-cat">${{p.category}} • Estoque: ${{p.stock}}</span>
          <strong>${{p.name}}</strong>
          <span class="prod-price">${{brl(p.price)}}</span>
          <div style="display:flex; gap:6px; margin-top:auto;">
            <button style="flex:1;" onclick="addToCart(${{p.id}})">+ Pedido</button>
            <button class="sec" onclick="delProduct(${{p.id}})">x</button>
          </div>
        </div>
      `).join('');

      document.getElementById('ordersList').innerHTML = (oRes.orders || []).map(o => `
        <div class="order-item">
          <div>
            <strong>#${{o.id}} ${{o.customer_name}}</strong> — ${{brl(o.total)}}<br/>
            <span style="color:var(--muted); font-size:11px;">${{(o.items || []).map(i => i.qty + 'x ' + i.name).join(', ')}}</span>
          </div>
          <button class="sec" onclick="advanceOrder(${{o.id}})">${{o.status}}</button>
        </div>
      `).join('') || '<div style="color:var(--muted); font-size:12px;">Nenhum pedido ainda.</div>';
    }}

    function addToCart(id) {{
      cart[id] = (cart[id] || 0) + 1;
      renderCart();
    }}

    function renderCart() {{
      const entries = Object.entries(cart).filter(([, q]) => q > 0);
      if (!entries.length) {{
        document.getElementById('cartList').textContent = 'Clique em "+ Pedido" em qualquer item.';
        document.getElementById('cartTotal').textContent = 'R$ 0,00';
        return;
      }}
      let total = 0;
      document.getElementById('cartList').innerHTML = entries.map(([id, qty]) => {{
        const p = products.find(x => x.id === Number(id));
        if (!p) return '';
        total += p.price * qty;
        return `<div class="order-item"><span>${{qty}}x ${{p.name}}</span><strong>${{brl(p.price * qty)}}</strong></div>`;
      }}).join('');
      document.getElementById('cartTotal').textContent = brl(total);
    }}

    async function submitOrder() {{
      const items = Object.entries(cart).filter(([, q]) => q > 0).map(([id, qty]) => ({{ product_id: Number(id), qty }}));
      if (!items.length) return alert('Adicione itens ao pedido primeiro.');
      const res = await fetch('/api/orders', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ customer_name: document.getElementById('custName').value, items }})
      }});
      if (res.ok) {{ cart = {{}}; renderCart(); refreshAll(); }}
    }}

    async function addProduct() {{
      const name = document.getElementById('pName').value.trim();
      const category = document.getElementById('pCat').value;
      const price = parseFloat(document.getElementById('pPrice').value);
      const stock = parseInt(document.getElementById('pStock').value || '20', 10);
      if (!name || isNaN(price)) return alert('Preencha nome e preço.');
      await fetch('/api/products', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ name, category, price, stock }})
      }});
      document.getElementById('pName').value = '';
      document.getElementById('pPrice').value = '';
      refreshAll();
    }}

    async function delProduct(id) {{
      await fetch('/api/products/' + id, {{ method: 'DELETE' }});
      refreshAll();
    }}

    async function advanceOrder(id) {{
      await fetch('/api/orders/' + id + '/status', {{ method: 'POST' }});
      refreshAll();
    }}

    refreshAll();
  </script>
</body>
</html>
'''
    (project_dir / "static" / "index.html").write_text(html_code, encoding="utf-8")
    return {"file": str(project_dir / "static" / "index.html")}


def launch_generated_project(project_dir: Path) -> Dict[str, Any]:
    port = _find_free_port(8800, 8899)
    env = dict(os.environ)
    env["PORT"] = str(port)
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0
    proc = subprocess.Popen(
        [sys.executable, str(project_dir / "app.py")],
        cwd=str(project_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    url = f"http://127.0.0.1:{port}"
    healthy = False
    for _ in range(20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                healthy = True
                break
        time.sleep(0.2)

    return {"ok": healthy, "pid": proc.pid, "port": port, "url": url}
