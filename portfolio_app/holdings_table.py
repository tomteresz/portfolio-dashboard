"""Small CCv2 table: sortable, draggable columns with server-side persistence."""
import math

import pandas as pd
import streamlit as st

from portfolio_app.app_logging import configure_logs
from portfolio_app.auth import is_authenticated
from portfolio_app.i18n import language, tr
from portfolio_app.layout_store import COLUMNS, LABELS, columns_for, reorder_columns

CSS = """
.viewport {overflow:auto;border:1px solid #e4e8ed;border-radius:10px;background:white;max-width:100%;}
table {border-collapse:collapse;width:100%;font:14px/1.45 var(--st-font,sans-serif);color:var(--st-text-color,#202833);}
th,td {padding:11px 12px;white-space:nowrap;border-bottom:1px solid #e9edf1;}
th {background:#f5f7fa;text-align:left;position:relative;user-select:none;}
th.target-before {box-shadow:inset 3px 0 #d98b12;background:#fff4dd;}
th.target-after {box-shadow:inset -3px 0 #d98b12;background:#fff4dd;}
th.source {opacity:.5;} tr:last-child td {border-bottom:0;}
tbody tr:hover {background:#fafbfd;} td.numeric {text-align:right;font-variant-numeric:tabular-nums;}
td.up {color:#168047;font-weight:600;} td.down {color:#c33935;font-weight:600;}
button {color:inherit;font:inherit;background:transparent;border:0;border-radius:5px;}
button:focus-visible {outline:2px solid #d98b12;outline-offset:2px;}
.heading {display:flex;align-items:center;gap:5px;}
.sort {padding:2px 0;cursor:pointer;font-weight:600;text-align:left;white-space:nowrap;}
.grip {padding:4px;min-width:24px;cursor:grab;touch-action:none;color:#68717b;}
.dragging,.dragging .grip {cursor:grabbing;}
.sr {position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);}
@media(max-width:1100px) {.grip,.sort {min-height:44px;}}
@media(pointer:coarse) {.grip {min-width:44px;min-height:44px;} .sort {min-height:44px;}}
"""

JS = """
export default function(component) {
  const {parentElement, data, setTriggerValue} = component;
  const root = parentElement.querySelector('.portfolio-table');
  if (!root || !data) return;
  const state = parentElement.__portfolioTable || (parentElement.__portfolioTable = {sort:null, direction:1});
  state.pending = false;
  const columns = data.columns.map(c => ({...c}));
  let order = columns.map(c => c.id);
  const byId = new Map(columns.map(c => [c.id, c]));
  const viewportLeft = root.querySelector('.viewport')?.scrollLeft || 0;
  const base = [...order];
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const format = (value, col) => {
    if (value == null) return '—';
    if (col.kind === 'text') return String(value);
    const sign = col.signed && value >= 0 ? '+' : '';
    const digits = col.kind === 'weight' ? 1 : 2;
    const number = Number(value).toLocaleString('en-US', {minimumFractionDigits:digits,maximumFractionDigits:digits});
    if (col.kind === 'money') return sign + '$' + number;
    return sign + number + (col.kind === 'percent' || col.kind === 'weight' ? '%' : '');
  };
  const commit = (from, to) => {
    if (state.pending || from === to || from < 0 || to < 0 || to >= order.length) return;
    const scroll = {x:window.scrollX, y:window.scrollY};
    const moved = order.splice(from,1)[0]; order.splice(to,0,moved);
    state.pending = true;
    render();
    setTriggerValue('order_changed', {columns:[...order], base, scroll});
  };
  const render = () => {
    const left = root.querySelector('.viewport')?.scrollLeft ?? viewportLeft;
    root.replaceChildren();
    const viewport = el('div', null, 'viewport');
    viewport.tabIndex = 0; viewport.setAttribute('aria-label',data.label);
    const table = el('table');
    table.append(el('caption', data.label, 'sr'));
    const head = el('thead'), header = el('tr');
    for (const id of order) {
      const col = byId.get(id), th = el('th');
      th.dataset.column = id; th.scope = 'col';
      th.setAttribute('aria-sort', state.sort === id ? (state.direction===1?'ascending':'descending') : 'none');
      const wrap = el('div', null, 'heading');
      const grip = el('button','⠿','grip'); grip.type='button';
      grip.title = data.dragHelp; grip.setAttribute('aria-label',data.dragHelp + ': ' + col.label);
      grip.onkeydown = e => {
        if (e.altKey && (e.key==='ArrowLeft' || e.key==='ArrowRight')) {
          e.preventDefault(); const i=order.indexOf(id); commit(i,i+(e.key==='ArrowLeft'?-1:1));
        }
      };
      th.onpointerdown = e => {
        if (!e.isPrimary || e.button !== 0 || state.pending) return;
        // On touchscreens, keep label swipes available for native scrolling.
        if (e.pointerType === 'touch' && !e.target.closest('.grip')) return;
        // Capture on the original button so an ordinary label click still
        // reaches its sort handler instead of being redirected to the grip.
        const handle = e.target.closest('button') || grip;
        e.preventDefault(); handle.setPointerCapture(e.pointerId);
        const initialX=e.clientX;
        const source=order.indexOf(id);
        let active=false, destination=source;
        const updateTarget = clientX => {
          const cells=[...header.children];
          cells.forEach(cell=>{
            cell.classList.remove('target-before','target-after');
          });
          const sourceBounds=th.getBoundingClientRect();
          destination=source;
          if(clientX>=sourceBounds.left && clientX<=sourceBounds.left+sourceBounds.width) return;
          // Drop before/after the header under the pointer, independent of
          // the dragged column's width or the place where it was grabbed.
          let slot=cells.length;
          for(let index=0;index<cells.length;index++) {
            const cell=cells[index];
            const rect=cell.getBoundingClientRect();
            if(clientX<rect.left+rect.width/2) {slot=index;break;}
          }
          destination=slot>source?slot-1:slot;
          if(destination<source) cells[destination]?.classList.add('target-before');
          if(destination>source) cells[destination]?.classList.add('target-after');
        };
        handle.onpointermove = move => {
          if (!active && Math.abs(move.clientX-initialX)<6) return;
          active=true; root.classList.add('dragging'); th.classList.add('source');
          const viewportBounds=viewport.getBoundingClientRect();
          if(move.clientX<viewportBounds.left+30) viewport.scrollLeft-=15;
          if(move.clientX>viewportBounds.right-30) viewport.scrollLeft+=15;
          updateTarget(move.clientX);
        };
        const finish = event => {
          if(active && event.type==='pointerup') updateTarget(event.clientX);
          handle.onpointermove=null;handle.onpointerup=null;handle.onpointercancel=null;handle.onlostpointercapture=null;
          root.classList.remove('dragging');
          for(const cell of header.children) cell.classList.remove('source','target-before','target-after');
          if(handle.hasPointerCapture(e.pointerId)) handle.releasePointerCapture(e.pointerId);
          if(active && event.type==='pointerup') {
            state.ignoreClickUntil=Date.now()+200;
            commit(order.indexOf(id),destination);
          }
        };
        handle.onpointerup=finish; handle.onpointercancel=finish;
        handle.onlostpointercapture=finish;
      };
      const sort=el('button',col.label + (state.sort===id?(state.direction===1?' ↑':' ↓'):''),'sort');
      sort.type='button'; sort.title=data.sortHelp;
      sort.onclick=()=>{
        if(Date.now()<(state.ignoreClickUntil||0)) return;
        state.direction=state.sort===id?-state.direction:1;state.sort=id;render();
      };
      wrap.append(grip,sort);th.append(wrap);header.append(th);
    }
    head.append(header);table.append(head);
    const body=el('tbody');let rows=[...data.rows];
    if(state.sort && byId.has(state.sort)) rows.sort((a,b)=>{
      const x=a[state.sort],y=b[state.sort];
      if(x==null) return y==null?0:1;if(y==null)return -1;
      return (typeof x==='number' && typeof y==='number'?x-y:String(x).localeCompare(String(y)))*state.direction;
    });
    for(const row of rows) {
      const tr=el('tr');
      for(const id of order) {
        const col=byId.get(id),value=row[id],td=el('td',format(value,col));
        if(col.kind!=='text') td.classList.add('numeric');
        if(col.signed && value!=null) td.classList.add(value>=0?'up':'down');
        tr.append(td);
      }
      body.append(tr);
    }
    table.append(body);viewport.append(table);root.append(viewport);
    viewport.scrollLeft=left;
  };
  render();
  if(data.restoreScroll) requestAnimationFrame(()=>requestAnimationFrame(()=>{
    window.scrollTo({left:data.restoreScroll.x,top:data.restoreScroll.y,behavior:'instant'});
  }));
}
"""

_TABLE = st.components.v2.component("portfolio_holdings", html='<div class="portfolio-table"></div>',
                                     css=CSS, js=JS)


def column_metadata(column):
    kind = ("text" if column in ("Spółka", "Ticker") else "shares" if column == "Akcje"
            else "weight" if column == "Udział %" else "percent" if "%" in column else "money")
    return {"id": column, "label": tr(LABELS.get(column, column)), "kind": kind,
            "signed": column in ("Zmiana dzienna %", "Zmiana dzienna USD", "Zwrot USD", "Zwrot %", "Pre-market %", "After-hours %")}


def _save_drag(name, event):
    if not isinstance(event, dict):
        raise ValueError("Nieprawidłowy wybór kolumn.")
    reorder_columns(name, event.get("columns"), event.get("base"))


def render_table(part, visible_columns, name, display_name=None):
    key = f"holdings-table-{name}"
    def changed():
        if not is_authenticated():
            return
        event = st.session_state.get(key, {}).get("order_changed")
        try:
            _save_drag(name, event)
            st.session_state.pop(f"layout-error-{name}", None)
            scroll = event.get("scroll")
            if isinstance(scroll, dict) and all(isinstance(scroll.get(k), (int, float)) and
                math.isfinite(scroll[k]) and 0 <= scroll[k] <= 1000000 for k in ("x", "y")):
                st.session_state[f"table-scroll-{name}"] = scroll
        except (ValueError, OSError):
            configure_logs()[1].exception("Could not save dragged column order")
            try:
                saved = columns_for(name)
            except (ValueError, OSError):
                saved = list(COLUMNS)
            st.session_state[f"visible-columns-{name}-{language()}"] = [c for c in COLUMNS if c in saved]
            st.session_state[f"layout-error-{name}"] = tr("Nie zapisano kolejności. Spróbuj ponownie.")
    rows = []
    for row in part[visible_columns].itertuples(index=False, name=None):
        values = {}
        for column, value in zip(visible_columns, row):
            if pd.isna(value):
                values[column] = None
            elif isinstance(value, str):
                values[column] = value
            else:
                number = float(value)
                values[column] = number if math.isfinite(number) else None
        rows.append(values)
    return _TABLE(key=key, width="stretch", on_order_changed_change=changed,
                  data={"columns": [column_metadata(c) for c in visible_columns], "rows": rows,
                        "label": tr("Posiadane akcje") + " — " + (display_name or name),
                        "dragHelp": tr("Przeciągnij, aby zmienić kolejność. Klawiatura: Alt + strzałka."),
                        "sortHelp": tr("Kliknij, aby posortować"),
                        "restoreScroll": st.session_state.pop(f"table-scroll-{name}", None)})
