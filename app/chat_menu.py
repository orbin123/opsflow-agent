"""Inline v2 menu beside each native Workspace title button."""

HTML = """
<button id="more" type="button" aria-label="More actions" aria-haspopup="menu" aria-expanded="false">⋯</button>
<div id="menu" popover="auto" role="menu" aria-label="Chat actions">
  <button type="button" role="menuitem" data-action="rename">Rename</button>
  <button type="button" role="menuitem" data-action="delete">Delete</button>
</div>
"""
CSS = """
:host { font-family: 'IBM Plex Mono', monospace; color: var(--st-text-color, #17292E); }
button { font: inherit; font-size: 14px; border-radius: 0; cursor: pointer; }
#more { width: 44px; height: 48px; padding: 0; font-size: 24px;
  color: inherit; background: var(--of-surface, #FAFCFC); border: 1px solid #6B8087; }
#more:hover, [role=menuitem]:hover, [role=menuitem]:focus { background: #DDF6FB; }
button:focus-visible { outline: 2px solid #126479; outline-offset: 2px; }
button:disabled { color: #4F666D; background: #DFE6E8; cursor: default; }
#menu { position: fixed; inset: auto; margin: 0; width: 180px; padding: 4px;
  box-sizing: border-box; border: 1px solid #6B8087; border-radius: 0;
  background: var(--of-surface, #FAFCFC); color: inherit;
  box-shadow: 0 4px 12px #17292E1A; }
[role=menuitem] { display: block; width: 100%; min-height: 44px; padding: 8px 16px;
  text-align: left; color: inherit; background: transparent; border: 0; }
[data-action=delete] { color: #A23438; border-top: 1px solid #DFE6E8; }
"""
JS = """
export default function(component) {
  const {parentElement, data, setTriggerValue} = component;
  const more = parentElement.querySelector('#more');
  const menu = parentElement.querySelector('#menu');
  const items = [...menu.querySelectorAll('[role=menuitem]')];
  // Scope the native-title listener to this component's containing columns row.
  const row = parentElement.host.closest('[data-testid="stHorizontalBlock"]');
  let origin = more;
  more.disabled = data.disabled;
  more.setAttribute('aria-label', 'More actions for ' + data.title);
  function close(restore = false) {
    menu.hidePopover();
    more.setAttribute('aria-expanded', 'false');
    if (restore) origin.focus();
  }
  function open(x, y, target) {
    if (data.disabled) return;
    origin = target;
    menu.style.left = Math.max(8, Math.min(x, window.innerWidth - 188)) + 'px';
    menu.style.top = Math.max(8, Math.min(y, window.innerHeight - 108)) + 'px';
    menu.showPopover();
    more.setAttribute('aria-expanded', 'true');
    items[0].focus();
  }
  more.onclick = () => {
    if (menu.matches(':popover-open')) return close(true);
    const box = more.getBoundingClientRect();
    open(box.right - 180, box.bottom + 4, more);
  };
  const context = event => {
    event.preventDefault();
    const target = event.target.closest('button') || more;
    const box = target.getBoundingClientRect();
    open(event.clientX || box.left, event.clientY || box.bottom, target);
  };
  const keyboard = event => {
    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
      event.preventDefault();
      const box = event.target.getBoundingClientRect();
      open(box.left, box.bottom + 4, event.target);
    }
  };
  row?.addEventListener('contextmenu', context);
  row?.addEventListener('keydown', keyboard);
  menu.onkeydown = event => {
    const index = items.indexOf(parentElement.activeElement);
    if (event.key === 'Escape') { event.preventDefault(); close(true); }
    else if (event.key === 'Tab') { close(true); }
    else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
        : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[next].focus();
    }
  };
  menu.ontoggle = event => {
    more.setAttribute('aria-expanded', String(event.newState === 'open'));
  };
  for (const item of items) item.onclick = () => {
    close(true);
    if (!data.disabled) setTriggerValue('action', item.dataset.action);
  };
  return () => {
    row?.removeEventListener('contextmenu', context);
    row?.removeEventListener('keydown', keyboard);
  };
}
"""


def chat_menu(component, title: str, session_id: str, *, disabled: bool, on_action_change) -> None:
    component(data={"title": title, "disabled": disabled}, key="menu_" + session_id,
          height=52, width=48, on_action_change=on_action_change)
